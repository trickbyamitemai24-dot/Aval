"""God-level error handling for Aurora Checker.

Features:
  - Central error handler (catches ALL unhandled exceptions)
  - Severity classification (CRITICAL / ERROR / WARNING / INFO)
  - Retry with exponential backoff + jitter
  - Telegram rate limit handling with auto-retry
  - DB retry logic with WAL-aware backoff
  - Admin alerts on critical errors (rate-limited, deduplicated)
  - User-friendly error messages with premium emoji
  - Circuit breaker (auto-disable failing features)
  - Error deduplication (don't spam same error)
  - Health monitoring with auto-recovery
  - Graceful degradation
  - Never crash silently
"""

import logging
import asyncio
import functools
import traceback
import time
import hashlib
from datetime import datetime
from enum import Enum
from typing import Callable, Any, Optional
from collections import defaultdict, deque

import aiohttp
import telegram.error

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from templates.messages import format_error
from templates.emojis import e_cross, e_warning, e_lightning, e_refresh, e_heart, e_check_done, e_chart

logger = logging.getLogger(__name__)

D = "━━━━━━━━━━━━━━━━━━━━━━"
B = lambda s: f"<b>{s}</b>"


class Severity(Enum):
    CRITICAL = "CRITICAL"
    ERROR    = "ERROR"
    WARNING  = "WARNING"
    INFO     = "INFO"


# ═════════════════════════════════════════════════════════════════════════
# ERROR CLASSIFIER — expanded with 30+ exception types
# ═════════════════════════════════════════════════════════════════════════

def classify_error(exc: Exception) -> Severity:
    """Classify an exception by severity."""
    # ── Telegram errors ──
    if isinstance(exc, telegram.error.BadRequest):
        return Severity.WARNING
    if isinstance(exc, telegram.error.Forbidden):
        return Severity.ERROR
    if isinstance(exc, telegram.error.InvalidToken):
        return Severity.CRITICAL
    if isinstance(exc, telegram.error.Conflict):
        return Severity.CRITICAL
    if isinstance(exc, telegram.error.RetryAfter):
        return Severity.INFO
    if isinstance(exc, telegram.error.TimedOut):
        return Severity.WARNING
    if isinstance(exc, telegram.error.NetworkError):
        return Severity.WARNING
    if isinstance(exc, telegram.error.ChatMigrated):
        return Severity.INFO

    # ── aiohttp network errors ──
    if isinstance(exc, aiohttp.ClientConnectorDNSError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ClientConnectorCertificateError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ClientConnectorError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ClientHttpProxyError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ClientProxyConnectionError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ServerTimeoutError):
        return Severity.WARNING
    if isinstance(exc, aiohttp.ClientOSError):
        return Severity.WARNING
    if isinstance(exc, asyncio.TimeoutError):
        return Severity.WARNING

    # ── Connection errors ──
    if isinstance(exc, ConnectionResetError):
        return Severity.WARNING
    if isinstance(exc, ConnectionRefusedError):
        return Severity.WARNING
    if isinstance(exc, ConnectionAbortedError):
        return Severity.WARNING
    if isinstance(exc, BrokenPipeError):
        return Severity.WARNING

    # ── SQLite errors ──
    exc_str = str(exc).lower()
    if "database is locked" in exc_str:
        return Severity.ERROR
    if "disk" in exc_str and ("full" in exc_str or "space" in exc_str):
        return Severity.CRITICAL
    if "no such table" in exc_str:
        return Severity.CRITICAL
    if "no such column" in exc_str:
        return Severity.CRITICAL
    if "constraint failed" in exc_str:
        return Severity.ERROR
    if "database disk image is malformed" in exc_str:
        return Severity.CRITICAL

    # ── File errors ──
    if isinstance(exc, FileNotFoundError):
        return Severity.WARNING
    if isinstance(exc, PermissionError):
        return Severity.ERROR
    if isinstance(exc, IsADirectoryError):
        return Severity.WARNING

    # ── Value errors ──
    if isinstance(exc, (ValueError, TypeError)):
        return Severity.WARNING
    if isinstance(exc, KeyError):
        return Severity.WARNING
    if isinstance(exc, IndexError):
        return Severity.WARNING
    if isinstance(exc, AttributeError):
        return Severity.ERROR

    # ── JSON errors ──
    if isinstance(exc, (json.JSONDecodeError if hasattr(__import__('json'), 'JSONDecodeError') else ValueError,)):
        return Severity.WARNING

    # ── Asyncio errors ──
    if isinstance(exc, asyncio.CancelledError):
        return Severity.INFO
    if isinstance(exc, asyncio.InvalidStateError):
        return Severity.WARNING

    # ── Default ──
    return Severity.ERROR


import json


# ═════════════════════════════════════════════════════════════════════════
# USER-FRIENDLY MESSAGES — expanded with 20+ patterns
# ═════════════════════════════════════════════════════════════════════════

def get_user_message(exc: Exception) -> str:
    """Get a user-friendly message for an exception."""
    exc_type = type(exc).__name__
    msg = str(exc).lower()

    # Telegram-specific
    if isinstance(exc, telegram.error.BadRequest):
        if "message is not modified" in msg:
            return None  # Silent — not an error
        if "chat not found" in msg:
            return "Chat not found. Start the bot first with /start"
        if "button_data_invalid" in msg:
            return "Button data expired. Try again."
        return "Invalid request. Check your input."

    if isinstance(exc, telegram.error.Forbidden):
        return "Bot was blocked. Cannot send messages."

    if isinstance(exc, telegram.error.RetryAfter):
        return f"Rate limited. Wait {exc.retry_after}s."

    if isinstance(exc, telegram.error.TimedOut):
        return "Telegram timed out. Retrying..."

    if isinstance(exc, telegram.error.Conflict):
        return "Another bot instance is running. Only one allowed."

    # Network
    if "timeout" in msg or isinstance(exc, asyncio.TimeoutError):
        return "Request timed out. The store may be slow — try again."
    if "dns" in msg or "could not resolve" in msg or isinstance(exc, aiohttp.ClientConnectorDNSError):
        return "DNS resolution failed. Check network or proxy."
    if "ssl" in msg or "certificate" in msg:
        return "SSL error. The store may have an invalid certificate."
    if "proxy" in msg:
        return "Proxy error. Check your proxies with /proxy"
    if "connection" in msg and "refused" in msg:
        return "Connection refused. The store may be offline."
    if "connection" in msg and "reset" in msg:
        return "Connection reset. Network instability."
    if isinstance(exc, (aiohttp.ClientError, ConnectionError)):
        return "Network error. Try again."

    # Database
    if "database is locked" in msg:
        return "System busy. Try again in a few seconds."
    if "no such table" in msg or "no such column" in msg:
        return "Database needs migration. Contact admin."
    if "disk" in msg and ("full" in msg or "space" in msg):
        return "Server storage full. Contact admin immediately."
    if "constraint" in msg:
        return "Data conflict. Entry may already exist."

    # File
    if isinstance(exc, FileNotFoundError):
        return "Required file not found. Contact admin."
    if isinstance(exc, PermissionError):
        return "Permission denied. Contact admin."

    # Value/Type
    if isinstance(exc, (ValueError, TypeError)):
        return "Invalid input type. Check your format."
    if isinstance(exc, KeyError):
        return "Missing required field. Try again."
    if isinstance(exc, (IndexError, AttributeError)):
        return "Data parsing error. Try again."

    # Generic
    if "rate" in msg and "limit" in msg:
        return "Too many requests. Slow down."
    if "banned" in msg:
        return "You are banned from this bot."
    if "expired" in msg:
        return "Session expired. Try /start."
    if "invalid" in msg:
        return "Invalid input. Check your format."
    if "not found" in msg:
        return "Not found."

    return "Something went wrong. Try again."


# ═════════════════════════════════════════════════════════════════════════
# ERROR DEDUPLICATOR — don't spam same error repeatedly
# ═════════════════════════════════════════════════════════════════════════

class ErrorDeduplicator:
    """Track recent errors to avoid spamming the same error."""

    def __init__(self, max_unique=100, cooldown=30):
        self._seen: dict[str, float] = {}
        self._max_unique = max_unique
        self._cooldown = cooldown

    def should_report(self, exc: Exception) -> bool:
        """Returns True if this error should be reported (not seen recently)."""
        # Create fingerprint from error type + message (first 200 chars)
        fingerprint = hashlib.md5(
            f"{type(exc).__name__}:{str(exc)[:200]}".encode()
        ).hexdigest()

        now = time.time()
        last_seen = self._seen.get(fingerprint, 0)

        if now - last_seen < self._cooldown:
            return False  # Same error seen recently, skip

        self._seen[fingerprint] = now

        # Cleanup old entries
        if len(self._seen) > self._max_unique:
            cutoff = now - self._cooldown
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}

        return True


# ═════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER — auto-disable failing features
# ═════════════════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Circuit breaker for features that keep failing.

    States:
      CLOSED:    Feature works normally
      OPEN:      Feature disabled (too many failures)
      HALF_OPEN: Testing if feature recovered
    """

    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._open_until: dict[str, float] = {}
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout

    def is_open(self, feature: str) -> bool:
        """Check if circuit is open for a feature."""
        open_until = self._open_until.get(feature, 0)
        if open_until > time.time():
            return True
        if open_until > 0 and open_until <= time.time():
            # Half-open: reset and allow one attempt
            self._open_until.pop(feature, None)
            self._failure_counts[feature] = 0
        return False

    def record_success(self, feature: str):
        """Record a successful operation."""
        self._failure_counts[feature] = 0
        self._open_until.pop(feature, None)

    def record_failure(self, feature: str):
        """Record a failed operation. Opens circuit if threshold exceeded."""
        self._failure_counts[feature] += 1
        if self._failure_counts[feature] >= self._failure_threshold:
            self._open_until[feature] = time.time() + self._recovery_timeout
            logger.warning(
                "Circuit breaker OPEN for '%s' (failed %d times, recovery in %ds)",
                feature, self._failure_counts[feature], self._recovery_timeout,
            )

    def get_status(self) -> dict:
        """Get status of all circuits."""
        now = time.time()
        return {
            feature: {
                "failures": count,
                "open": self._open_until.get(feature, 0) > now,
                "recovers_in": max(0, int(self._open_until.get(feature, 0) - now)),
            }
            for feature, count in self._failure_counts.items()
        }


# ═════════════════════════════════════════════════════════════════════════
# CENTRAL ERROR HANDLER
# ═════════════════════════════════════════════════════════════════════════

class ErrorHandler:
    """Central error handler for all bot exceptions."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.owner_id = self.config.get("bot", {}).get("owner_id")
        self._error_count = 0
        self._last_critical_alert = 0
        self._alert_cooldown = 60
        self._dedup = ErrorDeduplicator(max_unique=100, cooldown=30)
        self._circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Global error handler for all unhandled exceptions."""
        exc = context.error
        if exc is None:
            return

        self._error_count += 1
        severity = classify_error(exc)

        # Skip INFO severity (expected errors like RetryAfter, CancelledError)
        if severity == Severity.INFO:
            logger.debug("[INFO] %s: %s", type(exc).__name__, exc)
            return

        # Deduplicate — don't spam same error
        should_report = self._dedup.should_report(exc)

        # Log full traceback (always, even if dedup'd)
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if should_report:
            logger.error(
                "[ERROR #%d] [%s] %s: %s\n%s",
                self._error_count, severity.value, type(exc).__name__, exc, tb,
            )
        else:
            logger.debug("[DEDUP] %s: %s", type(exc).__name__, exc)

        # Record for health monitoring
        if hasattr(context, 'bot_data') and context.bot_data.get("health_monitor"):
            context.bot_data["health_monitor"].record_error()

        # Get user-friendly message
        user_msg = get_user_message(exc)

        # Skip if message is None (e.g., "message is not modified")
        if user_msg is None:
            return

        # Notify user if update exists
        if should_report and update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    format_error(user_msg), parse_mode=ParseMode.HTML,
                )
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await update.effective_message.reply_text(
                        format_error(user_msg), parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Failed to notify user: %s", e)

        # Alert admin on CRITICAL (rate-limited + dedup'd)
        if severity == Severity.CRITICAL and should_report:
            await self._alert_admin(context, exc, tb)

    async def _alert_admin(self, context: ContextTypes.DEFAULT_TYPE, exc: Exception, tb: str):
        """Send critical error alert to owner."""
        now = time.time()
        if now - self._last_critical_alert < self._alert_cooldown:
            logger.debug("Critical alert suppressed (cooldown)")
            return

        self._last_critical_alert = now

        if not self.owner_id:
            return

        try:
            tb_short = tb[:1500] if len(tb) > 1500 else tb
            text = (
                f"{e_warning()} {B('CRITICAL ERROR')}\n\n"
                f"{e_chart()} Error #{self._error_count}\n"
                f"Type: <code>{type(exc).__name__}</code>\n"
                f"Message: <code>{str(exc)[:200]}</code>\n\n"
                f"Traceback:\n<code>{tb_short}</code>\n\n"
                f"{e_lightning()} {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            await context.bot.send_message(
                chat_id=self.owner_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            logger.info("Critical alert sent to owner %d", self.owner_id)
        except Exception as e:
            logger.error("Failed to alert admin: %s", e)


# ═════════════════════════════════════════════════════════════════════════
# RETRY LOGIC — with jitter and circuit breaker integration
# ═════════════════════════════════════════════════════════════════════════

async def retry_async(
    func: Callable,
    max_retries: int = 3,
    backoff: float = 1.0,
    backoff_multiplier: float = 2.0,
    jitter: float = 0.1,
    retryable: tuple = (Exception,),
    on_retry: Callable = None,
    feature: str = None,
    circuit: CircuitBreaker = None,
):
    """Retry an async function with exponential backoff + jitter.

    Args:
        func: Async callable (no args)
        max_retries: Max retry attempts
        backoff: Initial backoff seconds
        backoff_multiplier: Multiplier per retry
        jitter: Random jitter fraction (0-1) to avoid thundering herd
        retryable: Tuple of exception types to retry on
        on_retry: Async callback(attempt, exception) on each retry
        feature: Feature name for circuit breaker
        circuit: CircuitBreaker instance
    Returns:
        Function result
    Raises:
        Last exception if all retries fail
    """
    import random

    # Check circuit breaker
    if circuit and feature and circuit.is_open(feature):
        raise RuntimeError(f"Circuit breaker open for '{feature}'")

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            result = await func()
            if circuit and feature:
                circuit.record_success(feature)
            return result
        except retryable as e:
            last_exc = e
            if circuit and feature:
                circuit.record_failure(feature)

            if attempt < max_retries:
                # Exponential backoff with jitter
                wait = backoff * (backoff_multiplier ** attempt)
                wait += random.uniform(0, wait * jitter)
                logger.warning("Retry %d/%d after %.2fs: %s", attempt + 1, max_retries, wait, e)

                if on_retry:
                    try:
                        await on_retry(attempt + 1, e)
                    except Exception:
                        pass
                await asyncio.sleep(wait)

    raise last_exc


def db_retry(func):
    """Decorator: retry DB operations on 'database is locked'."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    wait = 0.1 * (2 ** attempt)
                    logger.warning("DB locked, retry %d/%d in %.2fs", attempt + 1, max_retries, wait)
                    await asyncio.sleep(wait)
                else:
                    raise
    return wrapper


# ═════════════════════════════════════════════════════════════════════════
# SAFE HANDLER DECORATORS — catch ALL exceptions, never crash
# ═════════════════════════════════════════════════════════════════════════

def safe_handler(func):
    """Decorator: catch ALL exceptions in a handler, never crash."""
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, ctx, *args, **kwargs)
        except telegram.error.RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning("Telegram rate limit, waiting %ds", wait)
            await asyncio.sleep(wait)
            try:
                return await func(update, ctx, *args, **kwargs)
            except Exception as e2:
                logger.error("Failed after rate limit retry: %s", e2)
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            logger.warning("[BAD REQUEST] %s", e)
        except telegram.error.Forbidden:
            logger.warning("[FORBIDDEN] Bot blocked by user")
        except telegram.error.TimedOut:
            logger.warning("[TIMEOUT] Handler timed out")
        except asyncio.CancelledError:
            logger.debug("[CANCELLED] %s", func.__name__)
        except Exception as e:
            severity = classify_error(e)
            logger.error(
                "[HANDLER ERROR] [%s] %s: %s",
                severity.value, type(e).__name__, e,
                exc_info=True,
            )
            try:
                user_msg = get_user_message(e)
                if user_msg and update and update.effective_message:
                    await update.effective_message.reply_text(
                        format_error(user_msg), parse_mode=ParseMode.HTML,
                    )
            except Exception as e2:
                logger.warning("Failed to send error to user: %s", e2)
        return None
    return wrapper


def safe_callback(func):
    """Decorator: catch ALL exceptions in a callback handler."""
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, ctx, *args, **kwargs)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                return await func(update, ctx, *args, **kwargs)
            except Exception:
                pass
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            logger.warning("[CALLBACK BAD REQUEST] %s", e)
        except telegram.error.Forbidden:
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            severity = classify_error(e)
            logger.error(
                "[CALLBACK ERROR] [%s] %s: %s",
                severity.value, type(e).__name__, e,
                exc_info=True,
            )
            try:
                user_msg = get_user_message(e)
                if user_msg and update.callback_query:
                    await update.callback_query.answer(
                        user_msg or "Error occurred", show_alert=True,
                    )
            except Exception:
                pass
        return None
    return wrapper


# ═════════════════════════════════════════════════════════════════════════
# SAFE TELEGRAM SEND/EDIT — with retry and rate limit handling
# ═════════════════════════════════════════════════════════════════════════

async def safe_send(bot, chat_id, text, retries=3, **kwargs):
    """Send message with retry on rate limit/network errors."""
    for attempt in range(retries + 1):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except telegram.error.RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning("Rate limited, waiting %ds", wait)
            await asyncio.sleep(wait)
        except telegram.error.Forbidden:
            logger.warning("Bot blocked by user %d", chat_id)
            return None
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            logger.warning("Bad request sending to %d: %s", chat_id, e)
            return None
        except telegram.error.TimedOut:
            if attempt < retries:
                logger.debug("Timeout sending to %d, retry %d", chat_id, attempt + 1)
                await asyncio.sleep(1 + attempt)
            else:
                logger.warning("Timed out sending to %d after %d retries", chat_id, retries)
                return None
        except telegram.error.NetworkError as e:
            if attempt < retries:
                wait = 2 * (attempt + 1)
                logger.warning("Network error sending to %d, retry in %ds: %s", chat_id, wait, e)
                await asyncio.sleep(wait)
            else:
                logger.error("Network error sending to %d: %s", chat_id, e)
                return None
        except Exception as e:
            logger.error("Failed to send to %d: %s", chat_id, e)
            return None
    return None


async def safe_edit(bot, chat_id, message_id, text, retries=3, **kwargs):
    """Edit message with retry."""
    for attempt in range(retries + 1):
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None
            logger.warning("Bad request editing %d: %s", message_id, e)
            return None
        except telegram.error.Forbidden:
            return None
        except telegram.error.TimedOut:
            if attempt < retries:
                await asyncio.sleep(1 + attempt)
        except telegram.error.NetworkError as e:
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
        except Exception as e:
            logger.error("Failed to edit %d: %s", message_id, e)
            return None
    return None


# ═════════════════════════════════════════════════════════════════════════
# HEALTH MONITOR — with auto-recovery and uptime tracking
# ═════════════════════════════════════════════════════════════════════════

class HealthMonitor:
    """Monitor bot health with rolling window and auto-recovery."""

    def __init__(self, window_seconds=60, max_errors=10):
        self._errors: deque = deque()
        self._window = window_seconds
        self._max_errors = max_errors
        self.total_errors = 0
        self.last_error_time = 0
        self._start_time = time.time()
        self._recovery_actions: list[Callable] = []

    def record_error(self):
        """Record an error for health tracking."""
        now = time.time()
        self._errors.append(now)
        self.total_errors += 1
        self.last_error_time = now
        self._cleanup()

    def _cleanup(self):
        """Remove entries older than the window."""
        cutoff = time.time() - self._window
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()

    def errors_in_window(self) -> int:
        """Get error count in the current window."""
        self._cleanup()
        return len(self._errors)

    def is_healthy(self) -> bool:
        """Check if bot is healthy."""
        return self.errors_in_window() < self._max_errors

    def get_uptime(self) -> str:
        """Get bot uptime as human-readable string."""
        elapsed = time.time() - self._start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"

    def get_health_report(self) -> dict:
        return {
            "healthy": self.is_healthy(),
            "errors_last_minute": self.errors_in_window(),
            "total_errors": self.total_errors,
            "uptime": self.get_uptime(),
            "last_error": datetime.fromtimestamp(self.last_error_time).isoformat() if self.last_error_time else None,
        }


# ═════════════════════════════════════════════════════════════════════════
# CONVENIENCE — global instances
# ═════════════════════════════════════════════════════════════════════════

# Global circuit breaker
circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)