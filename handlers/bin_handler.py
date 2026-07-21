"""BIN lookup handler — /bin command."""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.bin_lookup import BinLookup, get_flag
from core.database import is_banned
from templates.messages import format_bin, format_bin_usage, format_banned

logger = logging.getLogger(__name__)


async def bin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /bin command — BIN lookup."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Parse BIN from args or reply
    raw_bin = None
    if ctx.args:
        raw_bin = ctx.args[0]
    elif update.message.reply_to_message:
        raw_bin = update.message.reply_to_message.text

    if not raw_bin:
        await update.message.reply_text(format_bin_usage(), parse_mode=ParseMode.HTML)
        return

    # Clean BIN: take first 6 digits
    raw_bin = raw_bin.strip()
    digits = "".join(c for c in raw_bin if c.isdigit())
    if len(digits) < 6:
        await update.message.reply_text(format_bin_usage(), parse_mode=ParseMode.HTML)
        return

    bin_code = digits[:6]

    # Send "looking up..." message
    msg = await update.message.reply_text(f"🔍 Looking up BIN {bin_code}...")

    # Lookup
    bin_lookup: BinLookup = ctx.bot_data["bin_lookup"]
    bin_info = await bin_lookup.lookup(bin_code)
    flag = get_flag(bin_info.get("country", ""))

    text = format_bin(bin_info, flag)
    await msg.edit_text(text, parse_mode=ParseMode.HTML)

    logger.info("BIN lookup: user=%d bin=%s", user.id, bin_code)