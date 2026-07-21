"""Help handler — /help command. Shows all commands."""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from templates.messages import format_help


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(format_help(), parse_mode=ParseMode.HTML)