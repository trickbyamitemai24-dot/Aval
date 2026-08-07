"""Rich fallback message handler — templates/rich_fallback.py

Provides reply_rich() to safely send HTML formatted messages with fallback to plain text if custom tags fail.
"""

from telegram import Message
from telegram.constants import ParseMode
from templates.emojis import strip_tg_emoji


async def reply_rich(message: Message, text: str, reply_markup=None):
    """Safely reply to a Telegram message with HTML format and fallback."""
    try:
        return await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception:
        clean_text = strip_tg_emoji(text)
        return await message.reply_text(clean_text, reply_markup=reply_markup)
