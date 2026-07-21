"""Proxy handlers — /addproxy, /proxy, /clearproxy.

/addproxy — send proxies (text or file), validates, adds live ones
/proxy    — re-check and clean dead proxies
/clearproxy — remove all proxies
"""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler

from core.database import is_banned
from core.proxy_manager import ProxyManager, normalize_proxy
from templates.messages import (
    format_banned,
    format_proxy_checking,
    format_proxy_added,
    format_proxy_cleaned,
    format_proxy_cleared,
    format_error,
)
from templates.emojis import e_lightning, e_memo, e_cross

logger = logging.getLogger(__name__)

WAITING_FOR_PROXY = 1

D = "━━━━━━━━━━━━━━━━━━━━━━"
BOLD = lambda s: f"<b>{s}</b>"
CODE = lambda s: f"<code>{s}</code>"
I = lambda s: f"<i>{s}</i>"


async def addproxy_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /addproxy — ask user to send proxies."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{D}\n\n"
        f"{e_memo()} {BOLD('Send proxies')}\n\n"
        f"Formats supported:\n"
        f"• {CODE('ip:port')}\n"
        f"• {CODE('ip:port:user:pass')}\n"
        f"• {CODE('user:pass@ip:port')}\n"
        f"• {CODE('socks5://ip:port')}\n\n"
        f"{I('Send as text message or .txt file.')}\n"
        f"{e_cross()} {CODE('/cancel')} to abort.",
        parse_mode=ParseMode.HTML,
    )
    return WAITING_FOR_PROXY


async def receive_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle proxy text or file upload."""
    user = update.effective_user
    conn = ctx.bot_data["db"]
    pm: ProxyManager = ctx.bot_data["proxy_manager"]

    raw_text = ""

    # File upload
    if update.message.document:
        try:
            file = await update.message.document.get_file()
            bytes_content = await file.download_as_bytearray()
            raw_text = bytes_content.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error("Proxy file download error: %s", e)
            await update.message.reply_text(
                format_error("Failed to download file."), parse_mode=ParseMode.HTML,
            )
            return WAITING_FOR_PROXY
    # Text message
    elif update.message.text:
        raw_text = update.message.text

    if not raw_text.strip():
        await update.message.reply_text(
            format_error("No proxies found."), parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_PROXY

    # Parse proxies
    lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
    proxies = []
    for line in lines:
        norm = normalize_proxy(line)
        if norm:
            proxies.append(norm)

    if not proxies:
        await update.message.reply_text(
            format_error("No valid proxies found.\nCheck format: ip:port"),
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_PROXY

    # Send "checking..." message
    msg = await update.message.reply_text(
        format_proxy_checking(len(proxies)), parse_mode=ParseMode.HTML,
    )

    # Add + validate
    result = await pm.add_proxies(user.id, proxies)
    total = pm.count(user.id)

    await msg.edit_text(
        format_proxy_added(len(result["live"]), total), parse_mode=ParseMode.HTML,
    )
    logger.info("User %d added proxies: %d live, %d dead", user.id, len(result["live"]), len(result["dead"]))
    return ConversationHandler.END


async def cancel_proxy_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel proxy adding."""
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def proxy_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /proxy — check and clean proxies."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    pm: ProxyManager = ctx.bot_data["proxy_manager"]
    count = pm.count(user.id)

    if count == 0:
        await update.message.reply_text(
            format_error("You have no proxies. Use /addproxy to add some."),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        format_proxy_checking(count), parse_mode=ParseMode.HTML,
    )

    result = await pm.clean_proxies(user.id)

    await update.message.reply_text(
        format_proxy_cleaned(result["live"], result["dead"]),
        parse_mode=ParseMode.HTML,
    )


async def clearproxy_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /clearproxy — clear all proxies."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    pm: ProxyManager = ctx.bot_data["proxy_manager"]
    count = pm.count(user.id)

    if count == 0:
        await update.message.reply_text(
            format_error("You have no proxies to clear."),
            parse_mode=ParseMode.HTML,
        )
        return

    removed = await pm.clear_proxies(user.id)
    await update.message.reply_text(
        format_proxy_cleared(removed), parse_mode=ParseMode.HTML,
    )
    logger.info("User %d cleared %d proxies", user.id, removed)