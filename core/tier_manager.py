"""Tier manager — get user tier, check expiry, enforce limits."""

import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

TIER_CONFIG = {
    "FREE":  {"workers": 10,  "card_limit": 500,  "speed": "Low"},
    "BASIC": {"workers": 20,  "card_limit": 1000, "speed": "Decent"},
    "PRO":   {"workers": 30,  "card_limit": 5000, "speed": "Medium"},
    "MAX":   {"workers": 50,  "card_limit": 10000, "speed": "Fast"},
    "ULTRA": {"workers": 200, "card_limit": 50000, "speed": "Ultra Fast"},
}


def get_user_tier(conn: sqlite3.Connection, user_id: int) -> str:
    """Get user's current tier. Auto-downgrades if expired."""
    user = conn.execute(
        "SELECT tier, key_expires_at FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        return "FREE"

    tier = user["tier"] or "FREE"
    expires = user["key_expires_at"]

    # Check expiry
    if expires and tier != "FREE":
        try:
            exp_dt = datetime.fromisoformat(expires)
            if exp_dt < datetime.utcnow():
                # Downgrade to FREE
                cfg = TIER_CONFIG["FREE"]
                conn.execute(
                    """UPDATE users
                       SET tier = 'FREE', card_limit = ?, workers = ?,
                           key_expires_at = NULL
                       WHERE user_id = ?""",
                    (cfg["card_limit"], cfg["workers"], user_id),
                )
                conn.commit()
                logger.info("User %d tier expired: %s → FREE", user_id, tier)
                return "FREE"
        except (ValueError, TypeError):
            pass

    return tier


def get_tier_config(tier: str) -> dict:
    """Get tier configuration (workers, card_limit, speed)."""
    return TIER_CONFIG.get(tier, TIER_CONFIG["FREE"])


def get_user_config(conn: sqlite3.Connection, user_id: int) -> dict:
    """Get user's tier config (workers, card_limit). Checks expiry."""
    tier = get_user_tier(conn, user_id)
    return TIER_CONFIG.get(tier, TIER_CONFIG["FREE"])


def is_owner(user_id: int, config: dict) -> bool:
    """Check if user is the bot owner."""
    return user_id == config.get("bot", {}).get("owner_id")


def is_admin(user_id: int, config: dict) -> bool:
    """Check if user is owner or admin."""
    if is_owner(user_id, config):
        return True
    admin_ids = config.get("bot", {}).get("admin_ids", [])
    return user_id in admin_ids