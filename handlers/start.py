"""Start handler — /start command with user stats + inline buttons."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import get_or_create_user, is_banned
from core.tier_manager import get_user_config, get_user_tier
from core.rate_limiter import rate_limiter
from templates.messages import format_start, format_banned, format_plans
from templates.emojis import (
    e_card, e_memo, e_gem, e_clipboard, e_mobile,
    e_check_done, e_warning, e_lightning, e_chart, e_mailbox,
)

logger = logging.getLogger(__name__)


def _start_keyboard():
    """Inline keyboard for /start message."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{e_card()} Single Check", callback_data="start_sh"),
            InlineKeyboardButton(f"{e_memo()} Mass Check", callback_data="start_chk"),
        ],
        [
            InlineKeyboardButton(f"{e_gem()} Plans", callback_data="start_plans"),
            InlineKeyboardButton(f"{e_gem()} Redeem", callback_data="start_redeem"),
        ],
        [
            InlineKeyboardButton(f"{e_clipboard()} Status", callback_data="start_status"),
            InlineKeyboardButton(f"{e_mobile()} Proxies", callback_data="start_proxy"),
        ],
    ])


async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with user stats + buttons."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    tier = get_user_tier(conn, user.id)
    tier_config = get_user_config(conn, user.id)
    card_limit = tier_config["card_limit"]

    db_user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()
    total_checks = db_user["total_checks"] if db_user else 0
    total_charged = db_user["total_charged"] if db_user else 0
    total_live = db_user["total_live"] if db_user else 0

    text = format_start(tier, card_limit, total_checks, total_charged, total_live)

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_start_keyboard(),
    )
    logger.info("User %d (%s) started the bot [tier=%s]", user.id, user.username, tier)


async def start_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks from /start message."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await query.edit_message_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    if data == "start_sh":
        await query.message.reply_text(
            "{e_card()} Usage: <code>/sh 4798510629051356|12|2028|893</code>\n\n"
            "Or reply to a card message with <code>/sh</code>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "start_chk":
        await query.message.reply_text(
            "📝 Send <code>/chk</code> then upload a .txt file with cards.\n"
            "One card per line: <code>NUMBER|MM|YYYY|CVV</code>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "start_plans":
        from templates.messages import format_plans
        try:
            await query.message.reply_text(
                format_plans(), parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("start_plans error: %s", e)

    elif data == "start_redeem":
        await query.message.reply_text(
            "{e_gem()} Usage: <code>/redeem AURORA-XXXX-XXXX-XXXX-XXXX</code>\n\n"
            "Or reply to a key message with <code>/redeem</code>",
            parse_mode=ParseMode.HTML,
        )

    elif data == "start_status":
        from core.tier_manager import get_user_tier, get_tier_config
        from core.key_system import get_user_tier_info, TIER_CONFIG
        try:
            get_or_create_user(conn, user.id, user.username, user.first_name)
            info = get_user_tier_info(conn, user.id)
            tier = get_user_tier(conn, user.id)
            cfg = get_tier_config(tier)
            from templates.messages import format_status_user
            text = format_status_user(
                tier=info["tier"], expires=info["expires"], expired=info["expired"],
                card_limit=cfg["card_limit"], workers=cfg["workers"],
            )
            await query.message.reply_text(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning("start_status error: %s", e)

    elif data == "start_proxy":
        await query.message.reply_text(
            "{e_mobile()} Proxy commands:\n\n"
            "• <code>/addproxy</code> — Add proxies (tested on Shopify)\n"
            "• <code>/proxy</code> — Check &amp; clean dead proxies\n"
            "• <code>/clearproxy</code> — Clear all proxies",
            parse_mode=ParseMode.HTML,
        )


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /status — show bot health + user rate limits."""
    user = update.effective_user
    conn = ctx.bot_data["db"]
    hm = ctx.bot_data.get("health_monitor")

    stats = rate_limiter.get_user_stats(user.id)
    tier = get_user_tier(conn, user.id)
    tier_config = get_user_config(conn, user.id)

    health = hm.get_health_report() if hm else {"healthy": True, "errors_last_minute": 0, "total_errors": 0}

    pm = ctx.bot_data.get("proxy_manager")
    proxy_count = pm.count(user.id) if pm else 0

    loader = ctx.bot_data.get("loader")
    store_counts = loader.get_counts() if loader else {}

    health_emoji = e_check_done() if health["healthy"] else e_warning()
    health_text = "Healthy" if health["healthy"] else "Degraded"

    text = (
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{health_emoji} <b>Bot Status</b>: {health_text}\n\n"
        f"{e_gem()} <b>Your Tier</b> : {tier}\n"
        f"{e_chart()} <b>Card Limit</b> : {tier_config['card_limit']}/run\n"
        f"{e_lightning()} <b>Workers</b>    : {tier_config['workers']}\n\n"
        f"{e_chart()} <b>Your Activity</b>\n"
        f"  Checks this hour: {stats['checks_this_hour']}\n"
        f"  Active mass checks: {stats['active_mass_checks']}\n"
        f"  Proxies: {proxy_count}\n\n"
        f"{e_chart()} <b>Sites</b>\n"
        f"  All: {store_counts.get('all', 0)}\n"
        f"  $5: {store_counts.get('5', 0)}\n"
        f"  $10: {store_counts.get('10', 0)}\n"
        f"  HQ: {store_counts.get('hq', 0)}\n\n"
        f"{e_clipboard()} <b>Bot Health</b>\n"
        f"  Errors (1m): {health['errors_last_minute']}\n"
        f"  Total errors: {health['total_errors']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{e_mailbox()} <i>Owner: @rayzenqx</i>"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)