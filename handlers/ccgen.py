"""CC Generator handler — /ccgen command.

Generates Luhn-valid card numbers with random/fixed expiry and CVV.

Usage:
  /ccgen                     — 10 random cards
  /ccgen <count>             — N random cards (max 50)
  /ccgen <bin> <count>       — N cards with BIN prefix
  /ccgen <bin> <month> <year> <count> — N cards with fixed expiry
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.cc_generator import (
    generate_cards,
    normalize_bin,
)
from core.database import is_banned, get_or_create_user
from core.rate_limiter import rate_limiter, get_cooldown_message
from templates.messages import format_ccgen, format_ccgen_usage, format_error
from templates.emojis import e_card, e_warning

logger = logging.getLogger(__name__)

MAX_GEN = 50          # hard cap per invocation
DEFAULT_COUNT = 10


async def ccgen_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /ccgen — generate Luhn-valid cards."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    get_or_create_user(conn, user.id, user.username, user.first_name)

    if is_banned(conn, user.id):
        await update.message.reply_text(
            format_error("You are banned."), parse_mode=ParseMode.HTML,
        )
        return

    # Rate limit
    allowed, remaining = rate_limiter.check_command_cooldown(user.id, "ccgen")
    if not allowed:
        await update.message.reply_text(get_cooldown_message("/ccgen", remaining))
        return

    args = ctx.args

    # ── Parse arguments ──
    bin_prefix = None
    fixed_month = None
    fixed_year = None
    count = DEFAULT_COUNT

    if len(args) == 1:
        # /ccgen <count>
        if args[0].isdigit() and 1 <= int(args[0]) <= 1000:
            count = min(int(args[0]), MAX_GEN)
        else:
            await update.message.reply_text(
                format_ccgen_usage(), parse_mode=ParseMode.HTML,
            )
            return

    elif len(args) == 2:
        # /ccgen <bin> <count>
        bin_prefix = normalize_bin(args[0])
        if not bin_prefix:
            await update.message.reply_text(
                format_ccgen_usage(), parse_mode=ParseMode.HTML,
            )
            return
        if args[1].isdigit():
            count = min(int(args[1]), MAX_GEN)
        else:
            await update.message.reply_text(
                format_ccgen_usage(), parse_mode=ParseMode.HTML,
            )
            return

    elif len(args) == 4:
        # /ccgen <bin> <month> <year> <count>
        bin_prefix = normalize_bin(args[0])
        if not bin_prefix:
            await update.message.reply_text(
                format_ccgen_usage(), parse_mode=ParseMode.HTML,
            )
            return
        fixed_month = args[1]
        fixed_year = args[2]
        # Validate month
        if not (fixed_month.isdigit() and 1 <= int(fixed_month) <= 12):
            await update.message.reply_text(
                format_error("Invalid month (01-12)."), parse_mode=ParseMode.HTML,
            )
            return
        # Validate year
        if not fixed_year.isdigit():
            await update.message.reply_text(
                format_error("Invalid year."), parse_mode=ParseMode.HTML,
            )
            return
        if len(fixed_year) == 2:
            fixed_year = "20" + fixed_year
        if len(fixed_year) != 4:
            await update.message.reply_text(
                format_error("Invalid year (use YYYY or YY)."), parse_mode=ParseMode.HTML,
            )
            return
        if args[3].isdigit():
            count = min(int(args[3]), MAX_GEN)
        else:
            await update.message.reply_text(
                format_ccgen_usage(), parse_mode=ParseMode.HTML,
            )
            return

    elif len(args) > 0 and len(args) not in (1, 2, 4):
        await update.message.reply_text(
            format_ccgen_usage(), parse_mode=ParseMode.HTML,
        )
        return

    # ── Generate ──
    cards = generate_cards(
        count=count,
        bin_prefix=bin_prefix,
        fixed_month=fixed_month,
        fixed_year=fixed_year,
    )

    if not cards:
        await update.message.reply_text(
            format_error("Generation failed. Try a different BIN."), parse_mode=ParseMode.HTML,
        )
        return

    # Format and send
    text = format_ccgen(
        cards=cards,
        bin_prefix=bin_prefix or "RANDOM",
        count=len(cards),
        fixed_month=fixed_month,
        fixed_year=fixed_year,
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    logger.info(
        "CC gen: user=%d count=%d bin=%s",
        user.id, len(cards), bin_prefix or "RANDOM",
    )
