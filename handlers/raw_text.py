import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from core.card_parser import Card, parse_card_list, _DedupeList
from core.database import is_banned
from templates.messages import format_error, hdr, ftr, frame
from templates.emojis import e_sparkles, e_lightning, e_card, e_memo, strip_tg_emoji

CC_PATTERN = re.compile(r'\b(4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|2(?:22[1-9]|2[3-9][0-9]|[3-6][0-9]{2}|7[0-1][0-9]|720)[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})[\s/\|:]+((?:0[1-9]|1[0-2]))[\s/\|:]+((?:20)?\d{2})[\s/\|:]+(\d{3,4})\b')

async def handle_raw_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """If a user sends raw CC(s) in PRIVATE chat, auto-detect and offer to check."""
    if not update.message or update.message.chat.type != "private":
        return

    text = update.message.text or ""
    all_ccs = _DedupeList()
    
    for m in CC_PATTERN.finditer(text):
        cc = f"{m.group(1)}|{m.group(2)}|{m.group(3)}|{m.group(4)}"
        if cc not in all_ccs:
            all_ccs.append(cc)

    if not all_ccs:
        # Fallback line by line
        for line in text.strip().splitlines():
            parts = re.split(r'[|/:]', line)
            if len(parts) >= 4:
                cc = "|".join(p.strip() for p in parts[:4])
                if cc not in all_ccs and len(cc) > 10:
                    all_ccs.append(cc)

    if not all_ccs:
        return

    conn = ctx.bot_data["db"]
    user_id = update.effective_user.id
    if is_banned(conn, user_id):
        return

    count = len(all_ccs)
    if count == 1:
        cc_str = all_ccs[0]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                strip_tg_emoji(f"{e_card()} Check This CC"), 
                callback_data=f"quick_check:{cc_str[:40]}", 
                api_kwargs={"style": "primary"}
            )
        ]])
        await update.message.reply_text(
            f"{hdr()}\n\n{e_sparkles()} <b>CC Detected!</b>\n\n"
            f"{e_lightning()} <tg-spoiler>{cc_str}</tg-spoiler>\n\n"
            f"Tap below to check it immediately.\n\n{ftr()}",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    else:
        # Avoid callback_data limit
        ctx.user_data["mass_check_cards"] = parse_card_list(text)
        if not ctx.user_data["mass_check_cards"]:
            return
            
        count = len(ctx.user_data["mass_check_cards"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                strip_tg_emoji(f"{e_memo()} Mass Check {count} CCs"), 
                callback_data="quick_msh", 
                api_kwargs={"style": "primary"}
            )
        ]])
        
        preview = "\n".join(f"{e_lightning()} <tg-spoiler>{c.raw}</tg-spoiler>" for c in ctx.user_data["mass_check_cards"][:5])
        extra = f"\n... {count - 5} more" if count > 5 else ""
        
        await update.message.reply_text(
            f"{hdr()}\n\n{e_sparkles()} <b>Multiple CCs Detected!</b>\n\n"
            f"<b>Total:</b> {count}\n\n{preview}{extra}\n\n"
            f"Tap below to start a mass check.\n\n{ftr()}",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

async def cb_quick_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle quick single check button."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":", 1)[1]
    # Re-route the text to the single_check handler
    # We will simulate a message
    from handlers.single_check import single_check_cmd
    ctx.args = [data]
    await single_check_cmd(update, ctx)

async def cb_quick_msh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle quick mass check button."""
    query = update.callback_query
    await query.answer()
    
    # Send them to the price range options
    from handlers.mass_check import process_card_document
    # Mocking a document since they already have mass_check_cards in user_data
    # Actually, we can just display the price options manually
    from core.tier_manager import get_user_tier, get_tier_config
    from templates.messages import format_mass_check_options, format_mass_check_limit_warning
    from handlers.mass_check import CB_PRICE_5, CB_PRICE_10, CB_PRICE_HQ, CB_PRICE_V40, CB_PRICE_SURESHIP, CB_PRICE_ALL, CB_PRICE_ALL_COMBINED, CB_CANCEL
    from core.rate_limiter import rate_limiter, get_hourly_message
    
    user = query.from_user
    conn = ctx.bot_data["db"]
    cards = ctx.user_data.get("mass_check_cards", [])
    if not cards:
        await query.edit_message_text(format_error("Session expired."), parse_mode=ParseMode.HTML)
        return
        
    tier = get_user_tier(conn, user.id)
    hourly_ok, hourly_remaining = rate_limiter.check_hourly_limit(user.id, tier, len(cards))
    if not hourly_ok:
        await query.edit_message_text(get_hourly_message(tier, hourly_remaining), parse_mode=ParseMode.HTML)
        return
        
    tier_cfg = get_tier_config(tier)
    card_limit = tier_cfg["card_limit"]
    if len(cards) > card_limit:
        cards = cards[:card_limit]
        limit_warn = format_mass_check_limit_warning(len(ctx.user_data["mass_check_cards"]), card_limit)
        ctx.user_data["mass_check_cards"] = cards
    else:
        limit_warn = ""
        
    ctx.user_data["mass_check_tier"] = tier
    ctx.user_data["mass_check_limit"] = card_limit
    
    loader = ctx.bot_data["loader"]
    counts = loader.get_counts()
    
    text = format_mass_check_options(
        c5=counts["5"], c10=counts["10"], call=counts["all"], cc=len(cards),
        warn=limit_warn, chq=counts.get("hq", 0), cv40=counts.get("v40", 0),
        csureship=counts.get("sureship", 0), call_combined=counts.get("all_combined", 0)
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"$1-5 ({counts['5']})", callback_data=CB_PRICE_5, api_kwargs={"style": "primary"}),
            InlineKeyboardButton(f"$1-10 ({counts['10']})", callback_data=CB_PRICE_10, api_kwargs={"style": "primary"}),
        ],
        [
            InlineKeyboardButton(strip_tg_emoji(f"✅ HQ ({counts.get('hq', 0)})"), callback_data=CB_PRICE_HQ, api_kwargs={"style": "primary"}),
            InlineKeyboardButton(strip_tg_emoji(f"⚡ V40 ({counts.get('v40', 0)})"), callback_data=CB_PRICE_V40, api_kwargs={"style": "primary"}),
        ],
        [
            InlineKeyboardButton(strip_tg_emoji(f"🚀 Sureship ({counts.get('sureship', 0)})"), callback_data=CB_PRICE_SURESHIP, api_kwargs={"style": "primary"}),
            InlineKeyboardButton(strip_tg_emoji(f"📦 Working ({counts['all']})"), callback_data=CB_PRICE_ALL, api_kwargs={"style": "primary"}),
        ],
        [
            InlineKeyboardButton(strip_tg_emoji(f"🌐 ALL Sites ({counts.get('all_combined', 0)})"), callback_data=CB_PRICE_ALL_COMBINED, api_kwargs={"style": "primary"}),
        ],
        [
            InlineKeyboardButton(strip_tg_emoji(f"❌ Cancel"), callback_data=CB_CANCEL, api_kwargs={"style": "danger"}),
        ],
    ])
    
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

