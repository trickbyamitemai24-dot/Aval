"""Rich fallback message handler — templates/rich_fallback.py

Provides reply_rich() / edit_rich() that try sending with premium inline
buttons (custom emoji + style api_kwargs) and fall back gracefully when
Telegram rejects them (e.g. non-premium bot token).

Fallback chain:
1. HTML parse mode + original reply_markup
2. HTML parse mode + stripped reply_markup (custom kwargs removed)
3. Plain text + stripped reply_markup
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from templates.emojis import strip_tg_emoji

logger = logging.getLogger(__name__)


def _strip_markup(markup):
    """Return a copy of *markup* with style/emoji kwargs removed, or None."""
    if markup is None or not hasattr(markup, "inline_keyboard"):
        return None

    rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for btn in row:
            new_row.append(
                InlineKeyboardButton(
                    text=btn.text,
                    callback_data=btn.callback_data,
                    url=btn.url,
                    switch_inline_query=btn.switch_inline_query,
                    switch_inline_query_current_chat=btn.switch_inline_query_current_chat,
                )
            )
        rows.append(new_row)


    return InlineKeyboardMarkup(rows) if rows else None


async def reply_rich(message: Message, text: str, reply_markup=None):
    """Safely reply to a Telegram message with HTML format and graceful fallback."""
    # Attempt 1: full rich
    try:
        return await message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning("reply_rich full attempt failed: %s", e)

    # Attempt 2: strip keyboard kwargs
    stripped = _strip_markup(reply_markup)
    try:
        return await message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=stripped
        )
    except Exception as e:
        logger.warning("reply_rich stripped attempt failed: %s", e)

    # Attempt 3: plain text, no markup
    clean = strip_tg_emoji(text)
    try:
        return await message.reply_text(clean, reply_markup=None)
    except Exception as e:
        logger.error("reply_rich plain text attempt failed: %s", e)

    return None


async def edit_rich(query, text: str, reply_markup=None):
    """Safely edit a message via callback query with graceful fallback."""
    # Attempt 1: full rich
    try:
        return await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning("edit_rich full attempt failed: %s", e)

    # Attempt 2: strip keyboard kwargs
    stripped = _strip_markup(reply_markup)
    try:
        return await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=stripped
        )
    except Exception as e:
        logger.warning("edit_rich stripped attempt failed: %s", e)

    # Attempt 3: plain text, no markup
    clean = strip_tg_emoji(text)
    try:
        return await query.edit_message_text(clean, reply_markup=None)
    except Exception as e:
        logger.error("edit_rich plain text attempt failed: %s", e)

    return None
