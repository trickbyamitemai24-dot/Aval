"""Pricing handler — /plans command."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from templates.messages import format_plans


async def plans_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /plans — show pricing plans."""
    await update.message.reply_text(format_plans(), parse_mode=ParseMode.HTML)