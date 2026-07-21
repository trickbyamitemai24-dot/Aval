"""God-level error handling for Aurora Checker.

Features:
  - Central error handler (catches ALL unhandled exceptions)
  - Severity classification (CRITICAL / ERROR / WARNING / INFO)
  - Retry with exponential backoff
  - Telegram rate limit handling
  - DB retry logic
  - Admin alerts on critical errors
  - User-friendly error messages
  - Never crash silently
"""

import logging
import asyncio
import functools
import traceback
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Any

import aiohttp
import telegram.error

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from templates.messages import format_error
from templates.emojis import e_cross, e_warning, e_lightning, e_refresh

logger = logging.getLogger(__name__)

D = "━━━━━━━━━━━━━━━━━━━━━━"
B = lambda s: f"<b>{s}</b>"


class Severity(Enum):
    CRITICAL = "CRITICAL"   # System broken, admin alert
    ERROR    = "ERROR"      # Feature broken, user notified
    WARNING  = "WARNING"    # Minor issue, log only
    INFO     = "INFO"       # Expected error, silent


# ═════════════════════════════════════════════════════════════════════════
# ERROR CLASSIFIER
# ═════════════════════════════════════════════════════════════════════════

def classify_error(exc: Exception) -> Severity:
    """Classify an exception by severity."""
    # Telegram errors
    if isinstance(exc, telegram.error.BadRequest):
        return Severity.WARNING  # User input issue
    if isinstance(exc, telegram.error.Forbidden):
        return Severity.ERROR  # Bot blocked
    if isinstance(exc, telegram.error.InvalidToken):
        return Severity.CRITICAL  # Token invalid
    if isinstance(exc, telegram.error.Conflict):
        return Severity.CRITICAL  # Another instance running
    if isinstance(exc, telegram.error.RetryAfter):
        return Severity.WARNING  # Rate limited
    if isinstance(exc, telegram.error.TimedOut):
        return Severity.WARNING  # Network timeout

    # Network errors
    if isinstance(exc, (aiohttp.ClientConnectorDNSError,)):
        return Severity.WARNING  # DNS fail
    if isinstance(exc, asyncio.TimeoutError):
        return Severity.WARNING  # Timeout
    if isinstance(exc, ConnectionResetError):
        return Severity.WARNING  # Reset

    # DB errors
    if isinstance(exc, Exception) and "database is locked" in str(exc).lower():
        return Severity.ERROR  # DB locked
    if isinstance(exc, Exception) and "disk" in str(exc).lower():
        return Severity.CRITICAL  # Disk full

    # File errors
    if isinstance(exc, FileNotFoundError):
        return Severity.WARNING
    if isinstance(exc, PermissionError):
        return Severity.ERROR

    # Default
    return Severity.ERROR


def get_user_message(exc: Exception) -> str:
    """Get a user-friendly message for an exception."""
    msg = str(exc).lower()

    if "database is locked" in msg:
        return "System busy. Try again in a few seconds."
    if "timeout" in msg:
        return "Request timed out. Try again."
    if "dns" in msg or "could not resolve" in msg:
        return "Network error. Check your connection."
    if "rate" in msg and "limit" in msg:
        return "Too many requests. Slow down."
    if "forbidden" in msg:
        return "Bot doesn't have permission."
    if "not found" in msg:
        return "Resource not found."
    if "banned" in msg:
        return "You are banned from this bot."
    if "expired" in msg:
        return "Your session expired. Try /start."
    if "invalid" in msg:
        return "Invalid input. Check your format."

    return "Something went wrong. Try again."


# ═════════════════════════════════════════════════════════════════════════
# CENTRAL ERROR HANDLER
# ═════════════════════════════════════════════════════════════════════════

class ErrorHandler:
    """Central error handler for all bot exceptions.
    
    Features:
    - Catches ALL unhandled exceptions
    - Severity classification
    - Admin alerts on CRITICAL errors
    - Error rate limiting (prevents spam)
    - Health monitoring integration
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.owner_id = self.config.get("bot", {}).get("owner_id")
        self._error_count = 0
        self._last_critical_alert = 0
        self._alert_cooldown = 60  # seconds between critical alerts
        self._recent_errors: list = []  # track recent errors for rate limiting
        self._max_errors_per_minute = 20

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Global error handler for all unhandled exceptions."""
        exc = context.error
        if exc is None:
            return

        self._error_count += 1
        severity = classify_error(exc)

        # Log full traceback
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.error(
            "[ERROR #%d] [%s] %s: %s\n%s",
            self._error_count, severity.value, type(exc).__name__, exc, tb,
        )

        # Record for health monitoring
        if hasattr(context, 'bot_data') and context.bot_data.get("health_monitor"):
            context.bot_data["health_monitor"].record_error()

        # Notify user if update exists
        if update and update.effective_message:
            try:
                user_msg = get_user_message(exc)
                await update.effective_message.reply_text(
                    format_error(user_msg), parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning("Failed to notify user: %s", e)

        # Alert admin on CRITICAL (rate-limited)
        if severity == Severity.CRITICAL:
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
            # Truncate traceback for Telegram
            tb_short = tb[:1500] if len(tb) > 1500 else tb
            text = (
                f"⚠️ <b>CRITICAL ERROR ALERT</b> ⚠️\n\n"
                f"🆔 Error #{self._error_count}\n"
                f"📛 Type: <code>{type(exc).__name__}</code>\n"
                f"💬 Message: <code>{str(exc)[:200]}</code>\n\n"
                f"📋 Traceback:\n<code>{tb_short}</code>\n\n"
                f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            await context.bot.send_message(
                chat_id=self.owner_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
            logger.info("Critical error alert sent to owner %d", self.owner_id)
        except Exception as e:
            logger.error("Failed to alert admin: %s", e)


# ═════════════════════════════════════════════════════════════════════════
# RETRY LOGIC
# ═════════════════════════════════════════════════════════════════════════

async def retry_async(
    func: Callable,
    max_retries: int = 3,
    backoff: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable: tuple = (Exception,),
    on_retry: Callable = None,
):
    """Retry an async function with exponential backoff.

    Args:
        func: Async callable (no args)
        max_retries: Max retry attempts
        backoff: Initial backoff seconds
        backoff_multiplier: Multiplier per retry
        retryable: Tuple of exception types to retry on
        on_retry: Async callback(attempt, exception) on each retry
    Returns:
        Function result
    Raises:
        Last exception if all retries fail
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable as e:
            last_exc = e
            if attempt < max_retries:
                wait = backoff * (backoff_multiplier ** attempt)
                logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, wait, e)
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
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    wait = 0.1 * (2 ** attempt)
                    logger.warning("DB locked, retry %d in %.2fs", attempt + 1, wait)
                    await asyncio.sleep(wait)
                else:
                    raise
    return wrapper


def safe_handler(func):
    """Decorator: catch ALL exceptions in a handler, never crash."""
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, ctx, *args, **kwargs)
        except telegram.error.RetryAfter as e:
            # Telegram rate limit
            wait = e.retry_after + 1
            logger.warning("Telegram rate limit, waiting %ds", wait)
            await asyncio.sleep(wait)
            try:
                return await func(update, ctx, *args, **kwargs)
            except Exception as e2:
                logger.error("Failed after rate limit retry: %s", e2)
        except Exception as e:
            severity = classify_error(e)
            logger.error(
                "[HANDLER ERROR] [%s] %s: %s",
                severity.value, type(e).__name__, e,
                exc_info=True,
            )
            try:
                user_msg = get_user_message(e)
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
        except Exception as e:
            severity = classify_error(e)
            logger.error(
                "[CALLBACK ERROR] [%s] %s: %s",
                severity.value, type(e).__name__, e,
                exc_info=True,
            )
            try:
                user_msg = get_user_message(e)
                if update.callback_query:
                    await update.callback_query.answer(user_msg, show_alert=True)
            except Exception:
                pass
        return None
    return wrapper


# ═════════════════════════════════════════════════════════════════════════
# SAFE TELEGRAM SEND
# ═════════════════════════════════════════════════════════════════════════

async def safe_send(bot, chat_id, text, retries=2, **kwargs):
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
            logger.warning("Bad request sending to %d: %s", chat_id, e)
            return None
        except telegram.error.TimedOut:
            if attempt < retries:
                await asyncio.sleep(1)
            else:
                logger.warning("Timed out sending to %d", chat_id)
                return None
        except Exception as e:
            logger.error("Failed to send to %d: %s", chat_id, e)
            return None
    return None


async def safe_edit(bot, chat_id, message_id, text, retries=2, **kwargs):
    """Edit message with retry."""
    for attempt in range(retries + 1):
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except telegram.error.BadRequest as e:
            if "message is not modified" in str(e).lower():
                return None  # Same content, ignore
            logger.warning("Bad request editing %d: %s", message_id, e)
            return None
        except telegram.error.Forbidden:
            return None
        except telegram.error.TimedOut:
            if attempt < retries:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error("Failed to edit %d: %s", message_id, e)
            return None
    return None


# ═════════════════════════════════════════════════════════════════════════
# ERROR RECOVERY
# ═════════════════════════════════════════════════════════════════════════

class HealthMonitor:
    """Monitor bot health and attempt auto-recovery."""

    def __init__(self):
        self.errors_last_minute = 0
        self.last_error_time = 0
        self.total_errors = 0
        self._minute_start = time.time()

    def record_error(self):
        """Record an error for health tracking."""
        now = time.time()
        if now - self._minute_start > 60:
            self._minute_start = now
            self.errors_last_minute = 0
        self.errors_last_minute += 1
        self.total_errors += 1
        self.last_error_time = now

    def is_healthy(self) -> bool:
        """Check if bot is healthy (< 10 errors per minute)."""
        return self.errors_last_minute < 10

    def get_health_report(self) -> dict:
        return {
            "healthy": self.is_healthy(),
            "errors_last_minute": self.errors_last_minute,
            "total_errors": self.total_errors,
            "last_error": datetime.fromtimestamp(self.last_error_time).isoformat() if self.last_error_time else None,
        }