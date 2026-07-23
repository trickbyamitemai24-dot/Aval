"""SQLite database init, migrations, and query helpers."""

import os
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    tier TEXT DEFAULT 'FREE',
    card_limit INTEGER DEFAULT 500,
    workers INTEGER DEFAULT 10,
    key_expires_at TIMESTAMP,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_checks INTEGER DEFAULT 0,
    total_charged INTEGER DEFAULT 0,
    total_live INTEGER DEFAULT 0,
    total_dead INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0,
    banned_reason TEXT
);

CREATE TABLE IF NOT EXISTS keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    tier TEXT NOT NULL,
    days INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    redeemed_by INTEGER,
    redeemed_at TIMESTAMP,
    expires_at TIMESTAMP,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    proxy TEXT NOT NULL,
    protocol TEXT DEFAULT 'http',
    status TEXT DEFAULT 'untested',
    last_checked TIMESTAMP,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    check_type TEXT NOT NULL,
    cards_total INTEGER,
    cards_live INTEGER DEFAULT 0,
    cards_dead INTEGER DEFAULT 0,
    cards_charged INTEGER DEFAULT 0,
    price_range TEXT,
    duration_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS mass_check_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER,
    cards_total INTEGER NOT NULL,
    cards_checked INTEGER DEFAULT 0,
    cards_json TEXT NOT NULL,
    stores_json TEXT NOT NULL,
    price_range TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'running',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS bin_cache (
    bin TEXT PRIMARY KEY,
    bank TEXT,
    brand TEXT,
    type TEXT,
    level TEXT,
    country TEXT,
    flag TEXT,
    cached_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS charged_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    card_number TEXT NOT NULL,
    card_masked TEXT NOT NULL,
    gateway TEXT,
    response TEXT,
    price REAL,
    store_url TEXT,
    bin TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS admin_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_cookies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    cookies TEXT NOT NULL,
    provider TEXT DEFAULT 'amazon',
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, provider),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);
CREATE INDEX IF NOT EXISTS idx_keys_active ON keys(active);
CREATE INDEX IF NOT EXISTS idx_keys_redeemed_by ON keys(redeemed_by);
CREATE INDEX IF NOT EXISTS idx_proxies_user ON user_proxies(user_id, status);
CREATE INDEX IF NOT EXISTS idx_history_user ON check_history(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_charged_user ON charged_cards(user_id, checked_at);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with schema. WAL mode for concurrent access."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode: allows concurrent readers + single writer
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA cache_size=10000")
    conn.executescript(SCHEMA)
    conn.commit()
    logger.info("Database initialized at %s (WAL mode)", path)
    return conn


def get_or_create_user(conn: sqlite3.Connection, user_id: int,
                       username: str = None, first_name: str = None) -> sqlite3.Row:
    """Get user record or create if new. Returns user row."""
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user:
        if username and user["username"] != username:
            conn.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()
        return user

    conn.execute(
        "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name),
    )
    conn.commit()
    logger.info("New user created: %d (%s)", user_id, username)
    return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def is_banned(conn: sqlite3.Connection, user_id: int) -> bool:
    user = conn.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(user and user["banned"])


def increment_check_stats(conn: sqlite3.Connection, user_id: int,
                          status: str, amount: int = 1):
    """Increment user's check statistics."""
    col = f"total_{status}" if status in ("charged", "live", "dead") else "total_checks"
    conn.execute(
        f"UPDATE users SET {col} = {col} + ?, total_checks = total_checks + ? WHERE user_id = ?",
        (amount, amount, user_id),
    )
    conn.commit()


def batch_increment_stats(conn: sqlite3.Connection, user_id: int,
                          charged: int = 0, live: int = 0, dead: int = 0):
    """Batch increment all stats in one query."""
    total = charged + live + dead
    conn.execute(
        """UPDATE users SET
           total_charged = total_charged + ?,
           total_live = total_live + ?,
           total_dead = total_dead + ?,
           total_checks = total_checks + ?
           WHERE user_id = ?""",
        (charged, live, dead, total, user_id),
    )
    conn.commit()


def log_check_history(conn: sqlite3.Connection, user_id: int, check_type: str,
                      cards_total: int, live: int = 0, dead: int = 0,
                      charged: int = 0, price_range: str = None,
                      duration: float = 0):
    conn.execute(
        """INSERT INTO check_history
           (user_id, check_type, cards_total, cards_live, cards_dead,
            cards_charged, price_range, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, check_type, cards_total, live, dead, charged, price_range, duration),
    )
    conn.commit()


def log_charged_card(conn: sqlite3.Connection, user_id: int, card_number: str,
                     card_masked: str, gateway: str, response: str,
                     price: float, store_url: str, bin_code: str):
    conn.execute(
        """INSERT INTO charged_cards
           (user_id, card_number, card_masked, gateway, response, price, store_url, bin)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, card_number, card_masked, gateway, response, price, store_url, bin_code),
    )
    conn.commit()


def batch_log_charged_cards(conn: sqlite3.Connection, user_id: int, cards: list):
    """Batch log multiple charged cards. cards = [(card, result), ...]"""
    for card, res in cards:
        conn.execute(
            """INSERT INTO charged_cards
               (user_id, card_number, card_masked, gateway, response, price, store_url, bin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, card.number, card.masked, res.gateway, res.message,
             res.price, res.store, card.bin),
        )
    conn.commit()


# ── User cookies (Amazon / other providers) ───────────────────────────

def set_user_cookies(conn: sqlite3.Connection, user_id: int,
                     cookies: str, provider: str = "amazon"):
    """Insert or replace a user's cookies for a provider."""
    conn.execute(
        """INSERT INTO user_cookies (user_id, cookies, provider, set_at)
           VALUES (?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, provider) DO UPDATE SET
               cookies = excluded.cookies,
               set_at = excluded.set_at""",
        (user_id, cookies, provider),
    )
    conn.commit()


def get_user_cookies(conn: sqlite3.Connection, user_id: int,
                      provider: str = "amazon"):
    """Return cookies row (dict-like) or None."""
    return conn.execute(
        "SELECT * FROM user_cookies WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    ).fetchone()


def clear_user_cookies(conn: sqlite3.Connection, user_id: int,
                       provider: str = "amazon") -> bool:
    """Delete a user's cookies. Returns True if a row was removed."""
    cur = conn.execute(
        "DELETE FROM user_cookies WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    conn.commit()
    return cur.rowcount > 0


# ── Amazon check history ──────────────────────────────────────────────

def log_amazon_check(conn: sqlite3.Connection, user_id: int,
                     cards_total: int, approved: int = 0,
                     declined: int = 0, errors: int = 0,
                     duration: float = 0.0):
    """Log an Amazon check run to check_history."""
    conn.execute(
        """INSERT INTO check_history
           (user_id, check_type, cards_total, cards_live, cards_dead,
            cards_charged, price_range, duration_seconds)
           VALUES (?, 'amazon', ?, ?, ?, ?, NULL, ?)""",
        (user_id, cards_total, approved, declined, errors, duration),
    )
    conn.commit()