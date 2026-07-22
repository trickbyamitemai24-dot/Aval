"""Anti-spam + user rate limiting for Aurora Checker.

Prevents abuse:
  - Per-user command cooldowns
  - Max checks per hour per user
  - Max concurrent mass checks per user
  - Spam detection (same card repeatedly)
"""

import time
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """Per-user rate limiter with command cooldowns and hourly caps."""

    # Command cooldowns (seconds between uses)
    COOLDOWNS = {
        "sh": 3,         # 3s between single checks
        "st": 3,         # 3s between stripe checks
        "chk": 30,       # 30s between mass checks
        "bin": 2,        # 2s between bin lookups
        "addproxy": 60,  # 1m between proxy adds
        "proxy": 30,     # 30s between proxy cleans
    }

    # Max checks per hour per tier
    HOURLY_LIMITS = {
        "FREE": 50,
        "BASIC": 200,
        "PRO": 500,
        "MAX": 1000,
        "ULTRA": 5000,
    }

    # Max concurrent mass checks per user
    MAX_CONCURRENT_MASS = 1

    def __init__(self):
        # Command last-used timestamps: {(user_id, command): timestamp}
        self._cmd_last: dict[tuple[int, str], float] = {}
        # Hourly check counts: {user_id: [(timestamp, count), ...]}
        self._hourly: dict[int, list[tuple[float, int]]] = defaultdict(list)
        # Active mass checks: {user_id: int}
        self._active_mass: dict[int, int] = defaultdict(int)
        # Card repeat detection: {(user_id, card_number): timestamp}
        self._card_seen: dict[tuple[int, str], float] = {}

    def _cleanup(self, user_id: int):
        """Remove entries older than 1 hour."""
        cutoff = time.time() - 3600
        self._hourly[user_id] = [(t, c) for t, c in self._hourly[user_id] if t > cutoff]

    def check_command_cooldown(self, user_id: int, command: str) -> tuple[bool, int]:
        """Check if user can use this command now.
        
        Returns: (allowed, seconds_remaining)
        """
        cooldown = self.COOLDOWNS.get(command, 0)
        if cooldown == 0:
            return True, 0

        key = (user_id, command)
        last = self._cmd_last.get(key, 0)
        elapsed = time.time() - last

        if elapsed >= cooldown:
            self._cmd_last[key] = time.time()
            return True, 0

        remaining = int(cooldown - elapsed) + 1
        return False, remaining

    def check_hourly_limit(self, user_id: int, tier: str, amount: int = 1) -> tuple[bool, int]:
        """Check if user is under hourly check limit.
        
        Returns: (allowed, remaining)
        Note: This reserves the count. Call refund_hourly() if the check fails.
        """
        self._cleanup(user_id)
        limit = self.HOURLY_LIMITS.get(tier, self.HOURLY_LIMITS["FREE"])
        used = sum(c for _, c in self._hourly[user_id])

        if used + amount <= limit:
            self._hourly[user_id].append((time.time(), amount))
            return True, limit - used - amount

        return False, limit - used

    def refund_hourly(self, user_id: int, amount: int = 1):
        """Refund hourly count if a check failed or was cancelled."""
        self._hourly[user_id].append((time.time(), -amount))

    def can_start_mass(self, user_id: int) -> tuple[bool, int]:
        """Check if user can start a mass check.
        
        Returns: (allowed, active_count)
        Note: This increments the counter. Call end_mass() or cancel_mass() when done.
        """
        active = self._active_mass[user_id]
        if active >= self.MAX_CONCURRENT_MASS:
            return False, active
        self._active_mass[user_id] = active + 1
        return True, active + 1

    def end_mass(self, user_id: int):
        """Mark a mass check as finished."""
        if self._active_mass[user_id] > 0:
            self._active_mass[user_id] -= 1

    def cancel_mass(self, user_id: int):
        """Cancel a mass check that was started but never ran."""
        if self._active_mass[user_id] > 0:
            self._active_mass[user_id] -= 1

    def is_card_repeat(self, user_id: int, card_number: str, window: int = 300) -> bool:
        """Check if user checked this card recently (spam detection).
        
        Args:
            user_id: User ID
            card_number: Full card number
            window: Seconds to consider a repeat (default 5 min)
        Returns:
            True if this card was checked recently
        """
        key = (user_id, card_number)
        last = self._card_seen.get(key, 0)
        now = time.time()

        if now - last < window:
            return True

        self._card_seen[key] = now
        return False

    def get_user_stats(self, user_id: int) -> dict:
        """Get current rate limit stats for a user."""
        self._cleanup(user_id)
        used = sum(c for _, c in self._hourly[user_id])
        active_mass = self._active_mass[user_id]
        return {
            "checks_this_hour": used,
            "active_mass_checks": active_mass,
            "cooldowns": {cmd: self._cmd_last.get((user_id, cmd), 0) for cmd in self.COOLDOWNS},
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_cooldown_message(command: str, remaining: int) -> str:
    """Get cooldown message for a command."""
    return f"⏳ Please wait {remaining}s before using {command} again."


def get_hourly_message(tier: str, remaining: int) -> str:
    """Get hourly limit message."""
    return f"⏳ Hourly limit reached. Upgrade: /plans"


def get_mass_active_message() -> str:
    """Get message when user already has active mass check."""
    return "⏳ You already have an active mass check. Use /cancel to stop it."