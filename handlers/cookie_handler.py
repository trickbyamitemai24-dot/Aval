"""Cookie management handlers — /setcookies, /cookies, /clearcookies.

Stores Amazon (and other provider) cookies per user in SQLite.
"""

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import (
    is_banned,
    get_or_create_user,
    set_user_cookies,
    get_user_cookies,
    clear_user_cookies,
)
from core.rate_limiter import rate_limiter, get_cooldown_message
from templates.messages import (
    format_cookies_saved,
    format_cookies_status,
    format_cookies_cleared,
    format_cookies_missing,
    format_cookies_usage,
    format_error,
    format_banned,
)

logger = logging.getLogger(__name__)


async def setcookies_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /setcookies — store Amazon cookies for the user."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Rate limit
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "setcookies")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/setcookies", remaining))
        return

    # Get cookies from args or reply
    cookies = None
    if ctx.args:
        cookies = " ".join(ctx.args)
    elif update.message.reply_to_message:
        cookies = update.message.reply_to_message.text

    if not cookies or len(cookies.strip()) < 10:
        await update.message.reply_text(format_cookies_usage(), parse_mode=ParseMode.HTML)
        return

    # Strip wrapping quotes if user pasted with quotes
    cookies = cookies.strip()
    if (cookies.startswith('"') and cookies.endswith('"')) or \
       (cookies.startswith("'") and cookies.endswith("'")):
        cookies = cookies[1:-1]

    set_user_cookies(conn, user.id, cookies, provider="amazon")

    # Fetch the stored set_at for display
    row = get_user_cookies(conn, user.id, "amazon")
    set_at = ""
    if row and row["set_at"]:
        try:
            dt = datetime.fromisoformat(str(row["set_at"]).replace("Z", ""))
            set_at = dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            set_at = str(row["set_at"])

    await update.message.reply_text(
        format_cookies_saved(set_at), parse_mode=ParseMode.HTML,
    )
    logger.info("User %d set Amazon cookies (%d chars)", user.id, len(cookies))


async def cookies_status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /cookies — show cookie status."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    row = get_user_cookies(conn, user.id, "amazon")
    if not row or not row["cookies"]:
        await update.message.reply_text(format_cookies_missing(), parse_mode=ParseMode.HTML)
        return

    set_at = ""
    if row["set_at"]:
        try:
            dt = datetime.fromisoformat(str(row["set_at"]).replace("Z", ""))
            set_at = dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            set_at = str(row["set_at"])

    await update.message.reply_text(
        format_cookies_status(set_at), parse_mode=ParseMode.HTML,
    )


async def clearcookies_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /clearcookies — remove stored cookies."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    removed = clear_user_cookies(conn, user.id, "amazon")
    await update.message.reply_text(
        format_cookies_cleared() if removed else format_cookies_missing(),
        parse_mode=ParseMode.HTML,
    )
    logger.info("User %d cleared Amazon cookies (removed=%s)", user.id, removed)
