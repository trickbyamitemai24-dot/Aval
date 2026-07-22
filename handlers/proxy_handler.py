"""Proxy handlers — /addproxy, /proxy, /clearproxy.

/addproxy — send proxies (text or file), validates against Shopify stores with 30 workers
/proxy    — re-check and clean dead proxies against Shopify stores
/clearproxy — remove all proxies
"""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler

from core.database import is_banned
from core.proxy_manager import ProxyManager, normalize_proxy, VALIDATION_WORKERS
from templates.messages import (
    format_banned,
    format_proxy_checking,
    format_proxy_added,
    format_proxy_cleaned,
    format_proxy_cleared,
    format_error,
)
from templates.emojis import e_lightning, e_memo, e_cross, e_refresh, e_check_done

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
        f"⚡ Proxies tested against {BOLD('real Shopify stores')}\n"
        f"⚡ {BOLD('30 workers')} parallel validation\n"
        f"⚡ Only live proxies added, dead ones discarded\n\n"
        f"{I('Send as text message or .txt file.')}\n"
        f"{e_cross()} {CODE('/cancel')} to abort.",
        parse_mode=ParseMode.HTML,
    )
    return WAITING_FOR_PROXY


async def receive_proxies(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle proxy text or file upload — validate against Shopify stores."""
    user = update.effective_user
    conn = ctx.bot_data["db"]
    pm: ProxyManager = ctx.bot_data["proxy_manager"]

    raw_text = ""

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
    elif update.message.text:
        raw_text = update.message.text

    if not raw_text.strip():
        await update.message.reply_text(
            format_error("No proxies found."), parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_PROXY

    # Parse raw lines
    lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
    if not lines:
        await update.message.reply_text(
            format_error("No proxies found."), parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_PROXY

    # Send initial "checking..." message
    msg = await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{D}\n\n"
        f"{e_refresh()} {BOLD(f'Checking {len(lines)} proxies...')}\n\n"
        f"🏪 Testing against Shopify stores\n"
        f"⚡ 30 workers parallel\n\n"
        f"{I('Only live proxies will be added.')}\n\n{D}",
        parse_mode=ParseMode.HTML,
    )

    # Progress callback for live updates
    async def progress_cb(checked, total, live_count):
        try:
            pct = int(checked / total * 100) if total > 0 else 0
            text = (
                f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
                f"{D}\n\n"
                f"{e_refresh()} {BOLD(f'Validating proxies against Shopify...')}\n\n"
                f"📊 Progress: {checked}/{total} ({pct}%)\n"
                f"✅ Live so far: {live_count}\n"
                f"⚡ Workers: {VALIDATION_WORKERS}\n\n"
                f"{I('Testing each proxy on real Shopify stores...')}\n\n{D}"
            )
            await msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    # Add + validate against Shopify stores
    result = await pm.add_proxies(user.id, lines, progress_callback=progress_cb)
    total = pm.count(user.id)

    # Final message
    if result["total_tested"] > 0:
        feedback = (
            f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
            f"{D}\n\n"
            f"{e_check_done()} {BOLD('Proxy validation complete')}\n\n"
            f"✅ Live (added): {BOLD(str(len(result['live'])))}\n"
            f"❌ Dead (discarded): {BOLD(str(len(result.get('dead', []))))}\n"
        )
    else:
        feedback = (
            f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
            f"{D}\n\n"
            f"{e_check_done()} {BOLD('Proxy validation complete')}\n\n"
            f"✅ Live: {BOLD(str(len(result['live'])))}\n"
            f"❌ Dead/invalid: {BOLD(str(len(result.get('dead', []))))}\n"
        )

    if result.get("skipped", 0) > 0:
        feedback += f"⏭️ Skipped: {result['skipped']} (limit reached)\n"
    if result.get("total_tested", 0) > 0:
        feedback += f"🔍 Tested: {result['total_tested']} proxies on Shopify\n"

    feedback += f"\n{e_check_done()} Your total proxies: {BOLD(str(total))}\n\n{D}"

    await msg.edit_text(feedback, parse_mode=ParseMode.HTML)
    logger.info(
        "User %d added proxies: %d live, %d dead, %d skipped (tested %d on Shopify)",
        user.id, len(result["live"]), len(result.get("dead", [])),
        result.get("skipped", 0), result.get("total_tested", 0),
    )
    return ConversationHandler.END


async def cancel_proxy_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel proxy adding."""
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def proxy_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /proxy — check and clean proxies against Shopify stores."""
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

    msg = await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{D}\n\n"
        f"{e_refresh()} {BOLD(f'Re-checking {count} proxies on Shopify...')}\n"
        f"⚡ 30 workers parallel\n\n"
        f"{I('Dead proxies will be removed.')}\n\n{D}",
        parse_mode=ParseMode.HTML,
    )

    # Progress callback
    async def progress_cb(checked, total, live_count):
        try:
            pct = int(checked / total * 100) if total > 0 else 0
            text = (
                f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
                f"{D}\n\n"
                f"{e_refresh()} {BOLD('Re-validating on Shopify...')}\n\n"
                f"📊 Progress: {checked}/{total} ({pct}%)\n"
                f"✅ Live: {live_count}\n"
                f"⚡ Workers: {VALIDATION_WORKERS}\n\n{D}"
            )
            await msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    result = await pm.clean_proxies(user.id, progress_callback=progress_cb)

    await msg.edit_text(
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