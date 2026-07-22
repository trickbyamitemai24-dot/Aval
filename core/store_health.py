"""Store health scoring — track which Shopify stores work best.

Scores stores based on:
  - Response success rate
  - Average response time
  - Last seen alive timestamp
Stores with low scores get deprioritized in rotation.
"""

import sqlite3
import logging
import time
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS store_health (
    url TEXT PRIMARY KEY,
    checks INTEGER DEFAULT 0,
    successes INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    avg_response_ms INTEGER DEFAULT 0,
    last_success TIMESTAMP,
    last_check TIMESTAMP,
    score REAL DEFAULT 50.0
);

CREATE INDEX IF NOT EXISTS idx_store_score ON store_health(score);
"""


def init_store_health(conn: sqlite3.Connection):
    """Initialize store health table."""
    conn.executescript(SCHEMA)
    conn.commit()


def record_check(conn: sqlite3.Connection, url: str, success: bool, response_ms: int = 0):
    """Record a store check result."""
    _record_check_internal(conn, url, success, response_ms)
    conn.commit()


def _record_check_internal(conn: sqlite3.Connection, url: str, success: bool, response_ms: int = 0):
    """Record a store check result without committing. Caller must commit."""
    now = time.time()
    s = 1 if success else 0
    f = 0 if success else 1

    existing = conn.execute("SELECT * FROM store_health WHERE url = ?", (url,)).fetchone()
    if existing:
        new_checks = existing["checks"] + 1
        new_successes = existing["successes"] + s
        new_failures = existing["failures"] + f
        new_avg = (existing["avg_response_ms"] + response_ms) // 2 if existing["avg_response_ms"] else response_ms
        new_score = (new_successes / new_checks) * 100 if new_checks > 0 else 50.0
        conn.execute(
            """UPDATE store_health SET checks=?, successes=?, failures=?, avg_response_ms=?, last_check=?, score=? WHERE url=?""",
            (new_checks, new_successes, new_failures, new_avg, now, new_score, url),
        )
    else:
        score = 100.0 if success else 0.0
        conn.execute(
            """INSERT INTO store_health (url, checks, successes, failures, avg_response_ms, last_check, score) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (url, 1, s, f, response_ms, now, score),
        )


def get_store_score(conn: sqlite3.Connection, url: str) -> float:
    """Get health score for a store (0-100)."""
    row = conn.execute("SELECT score FROM store_health WHERE url = ?", (url,)).fetchone()
    return row["score"] if row else 50.0


def get_best_stores(conn: sqlite3.Connection, limit: int = 100) -> list[str]:
    """Get top-rated stores by health score."""
    rows = conn.execute(
        "SELECT url FROM store_health WHERE score > 30 ORDER BY score DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["url"] for r in rows]


def get_worst_stores(conn: sqlite3.Connection, limit: int = 50) -> list[str]:
    """Get worst-rated stores (candidates for removal)."""
    rows = conn.execute(
        "SELECT url FROM store_health WHERE score < 20 ORDER BY score ASC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["url"] for r in rows]


class StoreHealthCache:
    """In-memory cache for store scores to avoid DB lookups during mass check."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._cache: dict[str, float] = {}
        self._load_cache()

    def _load_cache(self):
        """Load all scores into memory."""
        rows = self.conn.execute("SELECT url, score FROM store_health").fetchall()
        self._cache = {r["url"]: r["score"] for r in rows}
        logger.info("Loaded %d store health scores", len(self._cache))

    def get_score(self, url: str) -> float:
        """Get score from cache (defaults to 50)."""
        return self._cache.get(url, 50.0)

    def update_score(self, url: str, success: bool):
        """Update score in cache (does not write to DB)."""
        current = self._cache.get(url, 50.0)
        if success:
            self._cache[url] = min(100.0, current + 2.0)
        else:
            self._cache[url] = max(0.0, current - 1.0)

    def get_ranked(self, stores: list[str]) -> list[str]:
        """Sort stores by health score (best first)."""
        return sorted(stores, key=lambda s: self._cache.get(s, 50.0), reverse=True)