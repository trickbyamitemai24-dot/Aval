"""AI Debugger & Log Analyzer Handler — handlers/ai_handler.py

Provides /ai <prompt> for admins to analyze crashed gateway responses, debug logs, or generate payloads via Moonshot/Kimi or OpenAI API.
"""

import os
import aiohttp
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from core.tier_manager import is_admin, is_owner
from templates.messages import hdr, ftr, frame, format_error, C, B, I
from templates.emojis import e_robot, e_sparkles, e_cross, e_bulb, e_memo, e_pc

logger = logging.getLogger(__name__)

MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
MOONSHOT_API_URL = "https://api.moonshot.cn/v1/chat/completions"


async def query_kimi_ai(prompt: str) -> str:
    """Query Kimi/Moonshot AI completion endpoint."""
    if not MOONSHOT_API_KEY:
        return "AI Debugger error: MOONSHOT_API_KEY environment variable is not set."

    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": "You are an expert payment gateway debugger and Python async engineer for Telegram bots."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MOONSHOT_API_URL, json=payload, headers=headers, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
                text = await resp.text()
                return f"AI API Error (HTTP {resp.status}): {text[:100]}"
    except Exception as e:
        logger.error("Kimi AI query error: %s", e)
        return f"AI Connection Error: {str(e)}"


async def ai_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /ai <prompt> command for admins."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if not (is_owner(user.id) or is_admin(conn, user.id)):
        await update.message.reply_text(
            format_error("Admin command only."), parse_mode=ParseMode.HTML
        )
        return

    if not ctx.args:
        await update.message.reply_text(
            f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n{C('/ai analyze this response: ccard_declined')}\n\n"
            f"{I('ᴀɪ ᴅᴇʙᴜɢɢᴇʀ ғᴏʀ ʟᴏɢs ᴀɴᴅ ɢᴀᴛᴇᴡᴀʏ ʀᴇsᴘᴏɴsᴇs.')}",
            parse_mode=ParseMode.HTML,
        )
        return

    prompt = " ".join(ctx.args)
    status_msg = await update.message.reply_text(
        f"{hdr()}\n\n{frame('ᴀɪ ᴅᴇʙᴜɢɢᴇʀ')}\n\n"
        f"{e_robot()} {B('Thinking...')}\n\n{ftr()}",
        parse_mode=ParseMode.HTML,
    )

    ai_response = await query_kimi_ai(prompt)

    # Clean HTML characters for Telegram
    import html
    clean_ai_resp = html.escape(ai_response)

    await status_msg.edit_text(
        f"{hdr()}\n\n{frame('ᴀɪ ᴀɴᴀʟʏsɪs')}\n\n"
        f"{e_robot()} <b>Response:</b>\n"
        f"<code>{clean_ai_resp}</code>\n\n"
        f"{ftr()}",
        parse_mode=ParseMode.HTML,
    )


def register_ai_handlers(app):
    """Register /ai handler in Telegram app."""
    app.add_handler(CommandHandler("ai", ai_cmd))
