"""Proxy manager — add, validate, rotate, clean, clear proxies per user.

Supports formats:
  - ip:port
  - ip:port:user:pass
  - user:pass@ip:port
  - socks5://ip:port
  - http://ip:port
"""

import re
import logging
import sqlite3
from collections import deque
from pathlib import Path
from typing import Optional
from datetime import datetime

import aiohttp
from aiohttp.resolver import ThreadedResolver

logger = logging.getLogger(__name__)

# Proxy format validation — accepts IP or hostname
PROXY_PATTERN = re.compile(
    r"^(?:(?:https?|socks[45])://)?"           # optional scheme
    r"(?:(\S+):(\S+)@)?"                       # optional user:pass@
    r"([a-zA-Z0-9][a-zA-Z0-9.\-]*"             # host (IP or domain)
    r"(?:\.[a-zA-Z]{2,})*)"                     # TLD if domain
    r":(\d{2,5})"                              # port
    r"(?::(\S+):(\S+))?$"                      # optional :user:pass
)

VALIDATION_URL = "https://httpbin.org/ip"
MAX_PROXIES_PER_USER = 100


def normalize_proxy(raw: str) -> Optional[str]:
    """Normalize a proxy string. Returns None if invalid."""
    raw = raw.strip()
    if not raw:
        return None

    match = PROXY_PATTERN.match(raw)
    if not match:
        return None

    user1, pass1, ip, port, user2, pass2 = match.groups()
    user = user1 or user2
    pw = pass1 or pass2

    # Determine scheme
    scheme = "http"
    if raw.lower().startswith("socks5://"):
        scheme = "socks5"
    elif raw.lower().startswith("socks4://"):
        scheme = "socks4"
    elif raw.lower().startswith("https://"):
        scheme = "https"
    elif raw.lower().startswith("http://"):
        scheme = "http"

    if user and pw:
        return f"{scheme}://{user}:{pw}@{ip}:{port}"
    return f"{scheme}://{ip}:{port}"


class ProxyManager:
    """Per-user proxy pool with rotation, validation, cleanup.
    
    Falls back to default proxies from proxy.txt if user has none.
    """

    DEFAULT_PROXY_FILE = "proxy.txt"

    def __init__(self, conn: sqlite3.Connection, validation_url: str = VALIDATION_URL):
        self.conn = conn
        self.validation_url = validation_url
        self._pools: dict[int, deque] = {}  # user_id -> deque of proxy strings
        self._default_pool: deque | None = None
        self._load_defaults()

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

    async def validate_proxy(self, proxy: str, timeout: int = 10) -> bool:
        """Test if a proxy works by making a request through it."""
        norm = normalize_proxy(proxy)
        if not norm:
            return False
        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=ThreadedResolver())) as session:
                async with session.get(
                    self.validation_url,
                    proxy=norm,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.debug("Proxy validation failed for %s: %s", proxy, e)
            return False

    async def add_proxies(self, user_id: int, proxies: list[str]) -> dict:
        """Validate and add proxies for a user. Returns {live, dead}."""
        live = []
        dead = []

        # Check current count
        current = self.conn.execute(
            "SELECT COUNT(*) FROM user_proxies WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        slots = MAX_PROXIES_PER_USER - current

        for raw in proxies[:slots]:
            norm = normalize_proxy(raw)
            if not norm:
                dead.append(raw)
                continue
            if await self.validate_proxy(norm):
                self.conn.execute(
                    "INSERT INTO user_proxies (user_id, proxy, status, last_checked) VALUES (?, ?, 'live', ?)",
                    (user_id, norm, datetime.utcnow().isoformat()),
                )
                live.append(norm)
            else:
                dead.append(raw)

        self.conn.commit()
        self._load_pool(user_id)
        logger.info("User %d: added %d live, %d dead proxies", user_id, len(live), len(dead))
        return {"live": live, "dead": dead}

    async def clean_proxies(self, user_id: int) -> dict:
        """Re-validate all proxies, remove dead ones. Returns {live, dead}."""
        rows = self.conn.execute(
            "SELECT id, proxy FROM user_proxies WHERE user_id = ?",
            (user_id,),
        ).fetchall()

        live = 0
        dead_ids = []
        for row in rows:
            if await self.validate_proxy(row["proxy"]):
                live += 1
                self.conn.execute(
                    "UPDATE user_proxies SET status = 'live', last_checked = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), row["id"]),
                )
            else:
                dead_ids.append(row["id"])

        for pid in dead_ids:
            self.conn.execute("DELETE FROM user_proxies WHERE id = ?", (pid,))

        self.conn.commit()
        self._load_pool(user_id)
        logger.info("User %d: cleaned proxies — %d live, %d dead removed", user_id, live, len(dead_ids))
        return {"live": live, "dead": len(dead_ids)}

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
        # Try user's own pool first
        if user_id not in self._pools:
            self._load_pool(user_id)

        pool = self._pools.get(user_id)
        if pool:
            proxy = pool[0]
            pool.rotate(-1)
            return proxy

        # Fall back to default pool
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