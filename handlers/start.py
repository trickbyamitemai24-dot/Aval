"""Start handler — /start command with user stats."""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.database import get_or_create_user, is_banned
from core.tier_manager import get_user_config, get_user_tier
from core.rate_limiter import rate_limiter
from templates.messages import format_start, format_banned, B

logger = logging.getLogger(__name__)


async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with user stats."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    # Create or get user
    get_or_create_user(conn, user.id, user.username, user.first_name)

    # Check ban
    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Get tier (auto-downgrades if expired)
    tier = get_user_tier(conn, user.id)
    tier_config = get_user_config(conn, user.id)
    card_limit = tier_config["card_limit"]

    # Get user stats
    db_user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()
    total_checks = db_user["total_checks"] if db_user else 0
    total_charged = db_user["total_charged"] if db_user else 0
    total_live = db_user["total_live"] if db_user else 0

    text = format_start(tier, card_limit)

    # Append user stats
    if total_checks > 0:
        text += (
            f"\n\n📊 {B('Your Stats')}\n"
            f"🔑 Checks: {total_checks}\n"
            f"🤍 Charged: {total_charged}\n"
            f"😀 Live: {total_live}"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    logger.info("User %d (%s) started the bot [tier=%s]", user.id, user.username, tier)


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /status — show bot health + user rate limits."""
    user = update.effective_user
    conn = ctx.bot_data["db"]
    hm = ctx.bot_data.get("health_monitor")

    # Get user stats
    stats = rate_limiter.get_user_stats(user.id)
    tier = get_user_tier(conn, user.id)
    tier_config = get_user_config(conn, user.id)

    # Bot health
    health = hm.get_health_report() if hm else {"healthy": True, "errors_last_minute": 0, "total_errors": 0}

    # Proxy count
    pm = ctx.bot_data.get("proxy_manager")
    proxy_count = pm.count(user.id) if pm else 0

    # Store counts
    loader = ctx.bot_data.get("loader")
    store_counts = loader.get_counts() if loader else {}

    health_emoji = "✅" if health["healthy"] else "⚠️"
    health_text = "Healthy" if health["healthy"] else "Degraded"

    text = (
        f"⚡️ 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 ⚡️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{health_emoji} {B('Bot Status')}: {health_text}\n\n"
        f"💎 {B('Your Tier')} : {tier}\n"
        f"📊 {B('Card Limit')} : {tier_config['card_limit']}/run\n"
        f"⚡ {B('Workers')}    : {tier_config['workers']}\n\n"
        f"📈 {B('Your Activity')}\n"
        f"  Checks this hour: {stats['checks_this_hour']}\n"
        f"  Active mass checks: {stats['active_mass_checks']}\n"
        f"  Proxies: {proxy_count}\n\n"
        f"🏪 {B('Sites')}\n"
        f"  All: {store_counts.get('all', 0)}\n"
        f"  $5: {store_counts.get('5', 0)}\n"
        f"  $10: {store_counts.get('10', 0)}\n"
        f"  HQ: {store_counts.get('hq', 0)}\n\n"
        f"📋 {B('Bot Health')}\n"
        f"  Errors (1m): {health['errors_last_minute']}\n"
        f"  Total errors: {health['total_errors']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📬 <i>Owner: @rayzenqx</i>"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)