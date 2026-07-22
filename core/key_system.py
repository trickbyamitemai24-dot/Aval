"""Key system v2 — batch generation, reply-to-redeem, cooldowns.

Key format: AURORA-XXXX-XXXX-XXXX-XXXX (4 blocks, uppercase alphanumeric)
Batch generation: /genkey <plan> <quantity> <duration_days>
Reply-to-redeem: reply to key message with /redeem → picks next unused key
Cooldown: 3h between redemptions per user
"""

import re
import secrets
import string
import sqlite3
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)

VALID_TIERS = ["FREE", "BASIC", "PRO", "MAX", "ULTRA"]

# AURORA-XXXX-XXXX-XXXX-XXXX
KEY_PATTERN = re.compile(
    r"^AURORA-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$"
)

from core.tier_manager import TIER_CONFIG

REDEEM_COOLDOWN = 3 * 3600  # 3 hours


def generate_key() -> str:
    """Generate a single AURORA-XXXX-XXXX-XXXX-XXXX key."""
    segments = []
    for _ in range(4):
        seg = "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)
        )
        segments.append(seg)
    return f"AURORA-{segments[0]}-{segments[1]}-{segments[2]}-{segments[3]}"


def generate_keys(count: int) -> list[str]:
    """Generate multiple unique keys."""
    keys = set()
    attempts = 0
    while len(keys) < count and attempts < count * 5:
        keys.add(generate_key())
        attempts += 1
    return list(keys)


def validate_key_format(key: str) -> bool:
    return bool(KEY_PATTERN.match(key.upper().strip()))


@dataclass
class RedemptionResult:
    success: bool
    message: str
    tier: str = ""
    expires_at: str = ""
    card_limit: int = 0
    workers: int = 0
    key: str = ""
    position: str = ""  # "1 of 50 in message"


def create_batch_table(conn: sqlite3.Connection):
    """Create the key batch table if not exists."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS key_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            tier TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            total INTEGER NOT NULL,
            message_id INTEGER,
            chat_id INTEGER,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS batch_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            key TEXT UNIQUE NOT NULL,
            position INTEGER NOT NULL,
            tier TEXT NOT NULL,
            duration_days INTEGER NOT NULL,
            status TEXT DEFAULT 'unused',
            redeemed_by INTEGER,
            redeemed_at TIMESTAMP,
            expires_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_batch_keys_batch ON batch_keys(batch_id, status);
        CREATE INDEX IF NOT EXISTS idx_batch_keys_key ON batch_keys(key);
    """)
    conn.commit()


def save_batch(
    conn: sqlite3.Connection,
    keys: list[str],
    tier: str,
    duration_days: int,
    created_by: int,
    message_id: int = None,
    chat_id: int = None,
) -> str:
    """Save a batch of keys to DB. Returns batch_id."""
    import uuid
    batch_id = str(uuid.uuid4())[:8]

    conn.execute(
        """INSERT INTO key_batches (batch_id, tier, duration_days, total, message_id, chat_id, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (batch_id, tier, duration_days, len(keys), message_id, chat_id, created_by),
    )

    for i, key in enumerate(keys, 1):
        conn.execute(
            """INSERT OR IGNORE INTO batch_keys (batch_id, key, position, tier, duration_days, status)
               VALUES (?, ?, ?, ?, ?, 'unused')""",
            (batch_id, key, i, tier, duration_days),
        )

    conn.commit()
    logger.info("Batch %s saved: %d keys, tier=%s, %dd", batch_id, len(keys), tier, duration_days)
    return batch_id


def get_next_unused_key(conn: sqlite3.Connection, batch_id: str) -> Optional[sqlite3.Row]:
    """Get the next unused key from a batch."""
    return conn.execute(
        """SELECT * FROM batch_keys WHERE batch_id = ? AND status = 'unused'
           ORDER BY position ASC LIMIT 1""",
        (batch_id,),
    ).fetchone()


def get_batch_by_message(conn: sqlite3.Connection, chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
    """Find a batch by its Telegram message."""
    return conn.execute(
        "SELECT * FROM key_batches WHERE chat_id = ? AND message_id = ?",
        (chat_id, message_id),
    ).fetchone()


def redeem_batch_key(
    conn: sqlite3.Connection,
    key_row: sqlite3.Row,
    user_id: int,
) -> RedemptionResult:
    """Redeem a specific batch key row."""
    tier = key_row["tier"]
    duration = key_row["duration_days"]
    cfg = TIER_CONFIG.get(tier, TIER_CONFIG["FREE"])

    now = datetime.utcnow()
    expires = now + timedelta(days=duration)
    expires_str = expires.strftime("%d/%m/%Y %H:%M")

    # Lock key to user
    conn.execute(
        """UPDATE batch_keys SET status = 'redeemed', redeemed_by = ?, redeemed_at = ?, expires_at = ?
           WHERE id = ?""",
        (user_id, now.isoformat(), expires.isoformat(), key_row["id"]),
    )

    # Apply tier to user
    conn.execute(
        """INSERT INTO users (user_id, tier, card_limit, workers, key_expires_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             tier = ?, card_limit = ?, workers = ?, key_expires_at = ?""",
        (user_id, tier, cfg["card_limit"], cfg["workers"], expires.isoformat(),
         tier, cfg["card_limit"], cfg["workers"], expires.isoformat()),
    )

    conn.commit()

    total = conn.execute(
        "SELECT total FROM key_batches WHERE batch_id = ?",
        (key_row["batch_id"],),
    ).fetchone()["total"]

    position_str = f"{key_row['position']} of {total} in message"

    logger.info("Key redeemed: %s → user %d, tier %s, expires %s",
                key_row["key"], user_id, tier, expires_str)

    return RedemptionResult(
        success=True,
        message="Key redeemed!",
        tier=tier,
        expires_at=expires_str,
        card_limit=cfg["card_limit"],
        workers=cfg["workers"],
        key=key_row["key"],
        position=position_str,
    )


def check_cooldown(conn: sqlite3.Connection, user_id: int) -> tuple[bool, str]:
    """Check if user is on redemption cooldown.
    
    Returns: (can_redeem, cooldown_message)
    """
    row = conn.execute(
        "SELECT redeemed_at FROM batch_keys WHERE redeemed_by = ? ORDER BY redeemed_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if not row or not row["redeemed_at"]:
        return True, ""

    try:
        last_redeem = datetime.fromisoformat(row["redeemed_at"])
        elapsed = (datetime.utcnow() - last_redeem).total_seconds()
        remaining = REDEEM_COOLDOWN - elapsed

        if remaining > 0:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return False, f"{hours}h {minutes}m"
        return True, ""
    except (ValueError, TypeError):
        return True, ""


def get_batch_status(conn: sqlite3.Connection, batch_id: str) -> dict:
    """Get batch status: total, redeemed, remaining."""
    total = conn.execute(
        "SELECT total FROM key_batches WHERE batch_id = ?", (batch_id,)
    ).fetchone()
    if not total:
        return {"total": 0, "redeemed": 0, "remaining": 0}

    redeemed = conn.execute(
        "SELECT COUNT(*) FROM batch_keys WHERE batch_id = ? AND status IN ('redeemed', 'revoked')",
        (batch_id,),
    ).fetchone()[0]

    return {
        "total": total["total"],
        "redeemed": redeemed,
        "remaining": total["total"] - redeemed,
    }


def redeem_direct_key(
    conn: sqlite3.Connection,
    key: str,
    user_id: int,
) -> RedemptionResult:
    """Redeem a key directly by key string."""
    key = key.upper().strip()

    if not validate_key_format(key):
        return RedemptionResult(success=False, message="Invalid key format.")

    # Check batch_keys table
    row = conn.execute(
        "SELECT * FROM batch_keys WHERE key = ?", (key,),
    ).fetchone()

    if not row:
        return RedemptionResult(success=False, message="Key not found.")

    if row["status"] in ("redeemed", "revoked"):
        if row["status"] == "redeemed":
            return RedemptionResult(success=False, message="Key already redeemed.")
        return RedemptionResult(success=False, message="Key has been revoked.")

    return redeem_batch_key(conn, row, user_id)


def get_user_tier_info(conn: sqlite3.Connection, user_id: int) -> dict:
    """Get user's current tier + expiry info."""
    user = conn.execute(
        "SELECT tier, key_expires_at FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        return {"tier": "FREE", "expires": None, "expired": False}

    tier = user["tier"] or "FREE"
    expires = user["key_expires_at"]

    expired = False
    if expires and tier != "FREE":
        try:
            exp_dt = datetime.fromisoformat(expires)
            if exp_dt < datetime.utcnow():
                expired = True
        except (ValueError, TypeError):
            pass

    return {"tier": tier, "expires": expires, "expired": expired}