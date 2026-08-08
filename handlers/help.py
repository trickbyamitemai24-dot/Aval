"""Help handler — /help command. Shows all commands with pagination."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from templates.messages import format_help_page
from templates.rich_fallback import reply_rich, edit_rich

def get_help_keyboard(page: int):
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"help_page_{page-1}", api_kwargs={"style": "primary"}))
    buttons.append(InlineKeyboardButton(f"{page}/3", callback_data="ignore"))
    if page < 3:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"help_page_{page+1}", api_kwargs={"style": "primary"}))
    return InlineKeyboardMarkup([buttons])

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await reply_rich(update.message, format_help_page(1), reply_markup=get_help_keyboard(1))

async def help_pagination_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle help pagination buttons."""
    query = update.callback_query
    if query.data == "ignore":
        await query.answer()
        return

    await query.answer()
    try:
        page = int(query.data.replace("help_page_", ""))
        await edit_rich(query, format_help_page(page), reply_markup=get_help_keyboard(page))
    except Exception as e:
        pass
