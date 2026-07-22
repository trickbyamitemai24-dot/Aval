"""Proxy manager — add, validate, rotate, clean, clear proxies per user.

Validation: proxies are tested against real Shopify stores (not httpbin).
A proxy is "live" if it successfully fetches /products.json from a Shopify store.
Uses 30 concurrent workers for parallel validation.

Supports formats:
  - ip:port
  - ip:port:user:pass
  - user:pass@ip:port
  - socks5://ip:port
  - http://ip:port
  - socks5://user:pass@ip:port
"""

import re
import asyncio
import logging
import sqlite3
import random
from collections import deque
from pathlib import Path
from typing import Optional
from datetime import datetime

import aiohttp
from aiohttp.resolver import ThreadedResolver

logger = logging.getLogger(__name__)

# Proxy format validation
PROXY_PATTERN = re.compile(
    r"^(?:(?:https?|socks[45])://)?"
    r"(?:(\S+):(\S+)@)?"
    r"([a-zA-Z0-9][a-zA-Z0-9.\-]*"
    r"(?:\.[a-zA-Z]{2,})*)"
    r":(\d{2,5})"
    r"(?::(\S+):(\S+))?$"
)

SIMPLE_PATTERN = re.compile(
    r"^(?:(?:https?|socks[45])://)?"
    r"(?:(\S+):(\S+)@)?"
    r"([^:]+)"
    r":(\d{2,5})"
    r"(?::(\S+):(\S+))?$"
)

MAX_PROXIES_PER_USER = 100
VALIDATION_WORKERS = 30

# Shopify test stores for proxy validation (mix of known-good stores)
SHOPIFY_TEST_STORES = [
    "https://madebycleo.myshopify.com/products.json?limit=1",
    "https://allbirds.myshopify.com/products.json?limit=1",
    "https://kith.myshopify.com/products.json?limit=1",
    "https://gymshark.myshopify.com/products.json?limit=1",
    "https://colourpop.myshopify.com/products.json?limit=1",
    "https://bombas.myshopify.com/products.json?limit=1",
    "https://tesla.myshopify.com/products.json?limit=1",
    "https://buckmason.myshopify.com/products.json?limit=1",
]


def normalize_proxy(raw: str) -> Optional[str]:
    """Normalize a proxy string. Returns None if invalid."""
    raw = raw.strip()
    if not raw:
        return None

    match = PROXY_PATTERN.match(raw) or SIMPLE_PATTERN.match(raw)
    if not match:
        return None

    user1, pass1, ip, port, user2, pass2 = match.groups()
    user = user1 or user2
    pw = pass1 or pass2

    scheme = "http"
    rl = raw.lower()
    if rl.startswith("socks5://"):
        scheme = "socks5"
    elif rl.startswith("socks4://"):
        scheme = "socks4"
    elif rl.startswith("https://"):
        scheme = "https"
    elif rl.startswith("http://"):
        scheme = "http"

    if user and pw:
        return f"{scheme}://{user}:{pw}@{ip}:{port}"
    return f"{scheme}://{ip}:{port}"


async def _test_proxy_on_shopify(proxy: str, timeout: int = 12, shared_session: aiohttp.ClientSession = None) -> bool:
    """Test a proxy against a real Shopify store.

    A proxy is "live" if it can fetch /products.json from any test store
    and get a 200 response with valid JSON containing products.
    """
    test_url = random.choice(SHOPIFY_TEST_STORES)
    try:
        if shared_session:
            async with shared_session.get(
                test_url,
                proxy=proxy,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
            ) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        if data.get("products") is not None:
                            return True
                    except Exception:
                        pass
                if resp.status in (301, 302, 307, 308):
                    return True
                return False
        else:
            connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as session:
                async with session.get(
                    test_url,
                    proxy=proxy,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                    },
                ) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if data.get("products") is not None:
                                return True
                        except Exception:
                            pass
                    if resp.status in (301, 302, 307, 308):
                        return True
                    return False
    except Exception as e:
        logger.debug("Proxy test failed for %s on %s: %s", proxy, test_url, e)
        return False


async def _test_proxy_multi_store(proxy: str, timeout: int = 12, max_attempts: int = 3, shared_session=None) -> bool:
    """Test a proxy against multiple Shopify stores. Returns True if any succeeds."""
    for attempt in range(max_attempts):
        if await _test_proxy_on_shopify(proxy, timeout, shared_session=shared_session):
            return True
    return False


async def _validate_batch_concurrent(
    proxies: list[str], workers: int = VALIDATION_WORKERS, timeout: int = 12,
    progress_callback=None,
) -> dict:
    """Validate a batch of proxies concurrently with 30 workers.

    Uses a shared session for all proxy tests.
    """
    semaphore = asyncio.Semaphore(workers)
    live = []
    dead = []
    checked = {"count": 0}
    total = len(proxies)

    # Shared session for all proxy tests
    shared_connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    shared_session = aiohttp.ClientSession(
        connector=shared_connector,
        timeout=aiohttp.ClientTimeout(total=timeout),
    )

    try:
        async def check_one(proxy: str):
            async with semaphore:
                is_live = await _test_proxy_multi_store(proxy, timeout, shared_session=shared_session)
                checked["count"] += 1

                if is_live:
                    live.append(proxy)
                else:
                    dead.append(proxy)

                if progress_callback and (checked["count"] % 10 == 0 or checked["count"] == total):
                    try:
                        await progress_callback(checked["count"], total, len(live))
                    except Exception:
                        pass

        tasks = [check_one(p) for p in proxies]
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await shared_session.close()

    return {"live": live, "dead": dead}


class ProxyManager:
    """Per-user proxy pool with rotation, validation, cleanup.

    Validates proxies against real Shopify stores (not httpbin).
    Falls back to default proxies from proxy.txt if user has none.
    """

    DEFAULT_PROXY_FILE = "proxy.txt"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._pools: dict[int, deque] = {}
        self._default_pool: deque | None = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._load_defaults()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver()),
                timeout=aiohttp.ClientTimeout(total=12),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _load_defaults(self):
        """Load default proxies from proxy.txt (bot-level fallback)."""
        path = Path(self.DEFAULT_PROXY_FILE)
        if not path.exists():
            logger.info("No default proxy.txt found — users use direct connection")
            self._default_pool = None
            return

        proxies = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                norm = normalize_proxy(line)
                if norm:
                    proxies.append(norm)

        if proxies:
            self._default_pool = deque(proxies)
            logger.info("Loaded %d default proxies from %s", len(proxies), self.DEFAULT_PROXY_FILE)
        else:
            self._default_pool = None

    def _load_pool(self, user_id: int):
        """Load a user's live proxies from DB into memory deque."""
        rows = self.conn.execute(
            "SELECT proxy FROM user_proxies WHERE user_id = ? AND status = 'live' ORDER BY id",
            (user_id,),
        ).fetchall()
        self._pools[user_id] = deque([r["proxy"] for r in rows])

    async def validate_proxy(self, proxy: str, timeout: int = 12) -> bool:
        """Test if a proxy works against a real Shopify store."""
        norm = normalize_proxy(proxy)
        if not norm:
            return False
        return await _test_proxy_multi_store(norm, timeout)

    async def add_proxies(
        self,
        user_id: int,
        proxies: list[str],
        progress_callback=None,
    ) -> dict:
        """Validate and add proxies for a user using 30 concurrent workers.

        Tests each proxy against real Shopify stores.
        Only proxies that successfully connect to a Shopify store are added.
        Returns {live, dead, skipped, slots, total_tested}.
        """
        live = []
        dead = []
        skipped = 0

        current = self.conn.execute(
            "SELECT COUNT(*) FROM user_proxies WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        slots = MAX_PROXIES_PER_USER - current

        if slots <= 0:
            return {"live": [], "dead": [], "skipped": len(proxies), "slots": 0, "total_tested": 0}

        # Normalize and filter valid format proxies
        to_test = []
        format_invalid = []
        for raw in proxies[:slots]:
            norm = normalize_proxy(raw)
            if norm:
                to_test.append(norm)
            else:
                format_invalid.append(raw)

        if not to_test:
            return {
                "live": [], "dead": format_invalid, "skipped": max(0, len(proxies) - slots),
                "slots": slots, "total_tested": 0,
            }

        # Validate concurrently with 30 workers against Shopify stores
        result = await _validate_batch_concurrent(
            to_test, workers=VALIDATION_WORKERS, timeout=12,
            progress_callback=progress_callback,
        )

        # Save live proxies to DB
        for norm in result["live"]:
            self.conn.execute(
                "INSERT INTO user_proxies (user_id, proxy, status, last_checked) VALUES (?, ?, 'live', ?)",
                (user_id, norm, datetime.utcnow().isoformat()),
            )
            live.append(norm)

        dead = result["dead"] + format_invalid

        if len(proxies) > slots:
            skipped = len(proxies) - slots

        self.conn.commit()
        self._load_pool(user_id)
        logger.info(
            "User %d: added %d live, %d dead, %d skipped proxies (tested %d with %d workers)",
            user_id, len(live), len(dead), skipped, len(to_test), VALIDATION_WORKERS,
        )
        return {
            "live": live, "dead": dead, "skipped": skipped,
            "slots": max(0, slots - len(to_test)), "total_tested": len(to_test),
        }

    async def clean_proxies(
        self,
        user_id: int,
        progress_callback=None,
    ) -> dict:
        """Re-validate all proxies against Shopify stores, remove dead ones.

        Uses 30 concurrent workers.
        Returns {live, dead}.
        """
        rows = self.conn.execute(
            "SELECT id, proxy FROM user_proxies WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        if not rows:
            return {"live": 0, "dead": 0}

        proxies_to_test = [row["proxy"] for row in rows]
        proxy_ids = {row["proxy"]: row["id"] for row in rows}

        # Validate concurrently
        result = await _validate_batch_concurrent(
            proxies_to_test, workers=VALIDATION_WORKERS, timeout=12,
            progress_callback=progress_callback,
        )

        # Update DB
        live_count = 0
        dead_ids = []
        for norm in result["live"]:
            pid = proxy_ids.get(norm)
            if pid:
                self.conn.execute(
                    "UPDATE user_proxies SET status = 'live', last_checked = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), pid),
                )
                live_count += 1

        for norm in result["dead"]:
            pid = proxy_ids.get(norm)
            if pid:
                dead_ids.append(pid)

        for pid in dead_ids:
            self.conn.execute("DELETE FROM user_proxies WHERE id = ?", (pid,))

        self.conn.commit()
        self._load_pool(user_id)
        logger.info(
            "User %d: cleaned proxies — %d live, %d dead removed (30 workers)",
            user_id, live_count, len(dead_ids),
        )
        return {"live": live_count, "dead": len(dead_ids)}

    async def clear_proxies(self, user_id: int) -> int:
        """Delete all proxies for a user. Returns count removed."""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM user_proxies WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        self.conn.execute("DELETE FROM user_proxies WHERE user_id = ?", (user_id,))
        self.conn.commit()
        self._pools.pop(user_id, None)
        logger.info("User %d: cleared %d proxies", user_id, count)
        return count

    def get_proxy(self, user_id: int) -> Optional[str]:
        """Get next proxy via round-robin rotation.

        Priority: user's own proxies → default pool from proxy.txt → None (direct).
        Returns None if no proxies available (direct connection).
        """
        if user_id not in self._pools:
            self._load_pool(user_id)

        pool = self._pools.get(user_id)
        if pool:
            proxy = pool[0]
            pool.rotate(-1)
            return proxy

        if self._default_pool:
            proxy = self._default_pool[0]
            self._default_pool.rotate(-1)
            return proxy

        return None

    def count(self, user_id: int) -> int:
        """Get count of live proxies for a user."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM user_proxies WHERE user_id = ? AND status = 'live'",
            (user_id,),
        ).fetchone()[0]