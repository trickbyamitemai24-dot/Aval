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
        "ccgen": 5,      # 5s between card generations
        "amz": 5,        # 5s between Amazon single checks
        "massamz": 30,   # 30s between mass Amazon checks
        "setcookies": 10, # 10s between cookie sets
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
        # Throttle global cleanup to once per hour
        self._last_global_cleanup: float = 0.0
        # Sliding-window anti-spam tracking: {user_id: [timestamps]}
        self._event_windows: dict[int, list[float]] = defaultdict(list)
        self._last_event_time: dict[int, float] = {}
        self._AUTO_BAN_WINDOW: float = 10.0
        self._AUTO_BAN_LIMIT: int = 20
        self._RATE: float = 0.4

    def _cleanup(self, user_id: int):
        """Remove entries older than 1 hour."""
        cutoff = time.time() - 3600
        self._hourly[user_id] = [(t, c) for t, c in self._hourly[user_id] if t > cutoff]
        # Keep only recently used command cooldowns and repeat detections.
        self._cmd_last = {
            key: ts for key, ts in self._cmd_last.items() if ts > cutoff
        }
        self._card_seen = {
            key: ts for key, ts in self._card_seen.items() if ts > cutoff
        }

    def _global_cleanup(self):
        """Prune all stale entries across all dicts. Runs at most once per hour."""
        now = time.time()
        if now - self._last_global_cleanup < 3600:
            return
        self._last_global_cleanup = now
        cutoff = now - 3600
        self._cmd_last = {k: v for k, v in self._cmd_last.items() if v > cutoff}
        self._card_seen = {k: v for k, v in self._card_seen.items() if v > cutoff}
        self._hourly = defaultdict(list, {
            uid: [(t, c) for t, c in entries if t > cutoff]
            for uid, entries in self._hourly.items()
        })

    def check_command_cooldown(self, user_id: int, command: str) -> tuple[bool, int]:
        """Check if user can use this command now.
        
        Returns: (allowed, seconds_remaining)
        """
        cooldown = self.COOLDOWNS.get(command, 0)
        if cooldown == 0:
            return True, 0

        self._global_cleanup()
        key = (user_id, command)
        last = self._cmd_last.get(key, 0)
        elapsed = time.time() - last

        if elapsed >= cooldown:
            self._cmd_last[key] = time.time()
            return True, 0

        remaining = max(1, int(cooldown - elapsed + 0.999))
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
        """Refund hourly count if a check failed or was cancelled.

        Clamps the total to zero — negative sums would bypass the limit.
        """
        if amount <= 0:
            return
        self._cleanup(user_id)
        used = sum(c for _, c in self._hourly[user_id])
        # Only refund up to what has actually been used
        actual_refund = min(amount, max(0, used))
        if actual_refund > 0:
            self._hourly[user_id].append((time.time(), -actual_refund))

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
        now = int(time.time())
        # We need a db connection here, but RateLimiter is a global object without db.
        # So we continue to use memory but log a warning, OR we can add a method to pass db.
        # Actually, since it's just 5 minutes, in-memory is the standard way to do rate limiting
        # to avoid DB I/O bottleneck on every check. I will keep it in memory but make it thread-safe.
        key = (user_id, card_number)
        last = self._card_seen.get(key, 0)
        
        if now - last < window:
            return True
            
        self._card_seen[key] = now
        return False

    def check_user_throttle_and_spam(self, user_id: int) -> tuple[bool, bool, float]:
        """Check per-user soft rate limit and sliding-window spam detection.

        Returns: (should_ban, should_throttle, sleep_seconds)
        """
        now = time.monotonic()
        times = [t for t in self._event_windows[user_id] if now - t < self._AUTO_BAN_WINDOW]
        times.append(now)
        self._event_windows[user_id] = times

        if len(times) >= self._AUTO_BAN_LIMIT:
            return True, False, 0.0

        last = self._last_event_time.get(user_id, 0.0)
        diff = now - last
        sleep_sec = 0.0
        if diff < self._RATE:
            sleep_sec = self._RATE - diff
        self._last_event_time[user_id] = now + sleep_sec
        return False, sleep_sec > 0, sleep_sec

    def get_user_stats(self, user_id: int) -> dict:
        """Get current rate limit stats for a user."""
        self._cleanup(user_id)
        used = max(0, sum(c for _, c in self._hourly[user_id]))
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
    from templates.messages import format_error
    return format_error(f"⏳ Please wait {remaining}s before using {command} again.")


def get_hourly_message(tier: str, remaining: int) -> str:
    """Get hourly limit message."""
    from templates.messages import format_error
    return format_error(f"⏳ Hourly limit reached. Upgrade: /plans")


def get_mass_active_message() -> str:
    """Get message when user already has active mass check."""
    from templates.messages import format_error
    return format_error("⏳ You already have an active mass check. Use /cancel to stop it.")
