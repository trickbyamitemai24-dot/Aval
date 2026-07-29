"""Store health scoring — track which Shopify stores work best.

v2: Time-weighted exponential decay scoring.
  - Rolling window of last 20 results per store
  - Recent results weigh more (half-life ~10 checks)
  - Captcha/checkpoint/403 triggers instant penalty + 60s hard ban
  - Stores with recent CHARGED get a score boost
  - Weighted random selection via get_weighted()
"""

import sqlite3
import logging
import time
import math
import random
from typing import Optional
from collections import defaultdict, deque

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
        old_avg = existing["avg_response_ms"] or 0
        old_n = existing["checks"]
        if response_ms > 0:
            new_avg = int((old_avg * old_n + response_ms) / new_checks)
        else:
            new_avg = old_avg
        new_score = (new_successes / new_checks) * 100 if new_checks > 0 else 50.0
        last_success = now if success else existing["last_success"]
        conn.execute(
            """UPDATE store_health SET checks=?, successes=?, failures=?, avg_response_ms=?, last_check=?, last_success=?, score=? WHERE url=?""",
            (new_checks, new_successes, new_failures, new_avg, now, last_success, new_score, url),
        )
    else:
        score = 100.0 if success else 0.0
        last_success = now if success else None
        conn.execute(
            """INSERT INTO store_health (url, checks, successes, failures, avg_response_ms, last_check, last_success, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, 1, s, f, response_ms, now, last_success, score),
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


# ═══════════════════════════════════════════════════════════════════
# DECAY CONSTANTS
# ═══════════════════════════════════════════════════════════════════
_WINDOW_SIZE = 20       # Rolling window per store
_HALF_LIFE = 10         # Checks until weight halves
_DECAY = math.log(2) / _HALF_LIFE
_CHARGED_BOOST = 15.0   # Bonus points for a CHARGED result
_CAPTCHA_PENALTY = 40.0  # Instant penalty for captcha/checkpoint
_HARD_BAN_SECONDS = 60   # Store hard ban after captcha


class StoreHealthCache:
    """In-memory cache with time-weighted exponential decay scoring.
    
    Each store keeps a rolling window of the last 20 results.
    Recent results weigh exponentially more than older ones.
    Captcha/checkpoint triggers instant score penalty + hard ban.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._cache: dict[str, float] = {}
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=_WINDOW_SIZE))
        self._hard_bans: dict[str, float] = {}  # url -> ban_until timestamp
        self._load_cache()

    def _load_cache(self):
        """Load all scores into memory."""
        rows = self.conn.execute("SELECT url, score FROM store_health").fetchall()
        self._cache = {r["url"]: r["score"] for r in rows}
        logger.info("Loaded %d store health scores", len(self._cache))

    def _compute_weighted_score(self, url: str) -> float:
        """Compute exponentially weighted score from rolling window."""
        history = self._history.get(url)
        if not history or len(history) == 0:
            return self._cache.get(url, 50.0)

        total_weight = 0.0
        weighted_sum = 0.0
        n = len(history)
        for i, (success, result_type) in enumerate(history):
            # Most recent = index n-1, oldest = index 0
            age = n - 1 - i
            weight = math.exp(-_DECAY * age)
            
            value = 100.0 if success else 0.0
            if result_type == "CHARGED":
                value += _CHARGED_BOOST
                
            weighted_sum += value * weight
            total_weight += weight

        if total_weight == 0:
            return 50.0
        return max(0.0, min(100.0, weighted_sum / total_weight))

    def get_score(self, url: str) -> float:
        """Get score from cache (defaults to 50)."""
        return self._cache.get(url, 50.0)

    def update_score(self, url: str, success: bool, result_type: str = ""):
        """Update score with a new result. Supports CHARGED boost and captcha penalty."""
        # Record in rolling window
        self._history[url].append((success, result_type))
        
        # Captcha / checkpoint penalty
        if result_type in ("captcha", "checkpoint", "403"):
            self._cache[url] = max(0.0, self._cache.get(url, 50.0) - _CAPTCHA_PENALTY)
            self._hard_bans[url] = time.time() + _HARD_BAN_SECONDS
            logger.debug("Store %s hard-banned for %ds (captcha/checkpoint)", url, _HARD_BAN_SECONDS)
            return
        
        # Recompute weighted score
        self._cache[url] = self._compute_weighted_score(url)

    def is_banned(self, url: str) -> bool:
        """Check if a store is currently hard-banned."""
        ban_until = self._hard_bans.get(url, 0)
        if ban_until > time.time():
            return True
        if ban_until > 0:
            del self._hard_bans[url]
        return False

    def get_ranked(self, stores: list[str]) -> list[str]:
        """Sort stores by health score (best first), excluding banned stores."""
        now = time.time()
        available = [s for s in stores if self._hard_bans.get(s, 0) <= now]
        return sorted(available, key=lambda s: self._cache.get(s, 50.0), reverse=True)

    def get_weighted(self, stores: list[str], exclude: set = None) -> Optional[str]:
        """Pick a store using weighted random selection based on health scores.
        
        Higher-scored stores are selected more frequently.
        Banned and excluded stores are skipped.
        Returns None if no stores available.
        """
        now = time.time()
        candidates = []
        weights = []
        
        for s in stores:
            if exclude and s in exclude:
                continue
            if self._hard_bans.get(s, 0) > now:
                continue
            score = self._cache.get(s, 50.0)
            if score <= 0:
                continue
            candidates.append(s)
            weights.append(score)
        
        if not candidates:
            return None
        
        return random.choices(candidates, weights=weights, k=1)[0]