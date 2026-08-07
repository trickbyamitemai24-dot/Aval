"""Help handler — /help command. Shows all commands with pagination."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from templates.messages import format_help_page

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
    await update.message.reply_text(
        format_help_page(1), 
        parse_mode=ParseMode.HTML,
        reply_markup=get_help_keyboard(1)
    )

async def help_pagination_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle help pagination buttons."""
    query = update.callback_query
    if query.data == "ignore":
        await query.answer()
        return
        
    await query.answer()
    try:
        page = int(query.data.replace("help_page_", ""))
        await query.edit_message_text(
            format_help_page(page),
            parse_mode=ParseMode.HTML,
            reply_markup=get_help_keyboard(page)
        )
    except Exception as e:
        pass
