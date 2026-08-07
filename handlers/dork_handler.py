"""Brave Search Dorker Handler — handlers/dork_handler.py

Provides /dork <keyword> for admins to scrape search.brave.com for new Shopify domains.
Extracts, deduplicates, and allows pings/saves to working sites.
"""

import re
import logging
from urllib.parse import quote, urlparse
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from core.tier_manager import is_admin, is_owner
from core.database import is_banned
from core.bypass_client import fetch_page_bypass
from templates.messages import hdr, ftr, frame, format_error, sc, C, B, I
from templates.emojis import e_search, e_globe, e_check_done, e_cross, e_rocket, e_folder

logger = logging.getLogger(__name__)

EXCLUDED_DOMAINS = {
    "brave.com", "google.com", "youtube.com", "facebook.com", "twitter.com",
    "instagram.com", "amazon.com", "ebay.com", "wikipedia.org", "reddit.com",
    "github.com", "pinterest.com", "linkedin.com", "tiktok.com", "apple.com"
}


def extract_domains_from_brave_html(html: str) -> list[str]:
    """Parse links from Brave search results HTML and return cleaned domains."""
    urls = re.findall(r'href="(https?://[^"]+)"', html)
    domains = set()
    for u in urls:
        parsed = urlparse(u)
        netloc = parsed.netloc.lower()
        if not netloc:
            continue
        # Strip port or www prefix for clean domain comparison
        domain = netloc.split(":")[0]
        root_domain = domain.removeprefix("www.")
        if root_domain in EXCLUDED_DOMAINS or any(root_domain.endswith(f".{ex}") for ex in EXCLUDED_DOMAINS):
            continue
        # Filter static assets
        if any(parsed.path.lower().endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"]):
            continue
        domains.add(f"https://{netloc}")
    return sorted(list(domains))


async def dork_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /dork <keyword> — search Brave for Shopify stores."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if not (is_owner(user.id) or is_admin(conn, user.id)):
        await update.message.reply_text(
            format_error("Admin command only."), parse_mode=ParseMode.HTML
        )
        return

    if not ctx.args:
        await update.message.reply_text(
            f"{e_cross()} {B('ᴜsᴀɢᴇ:')}\n{C('/dork myshopify.com powered by shopify')}\n\n"
            f"{I('sᴇᴀʀᴄʜᴇs ʙʀᴀᴠᴇ ғᴏʀ ɴᴇᴡ ᴍᴇʀᴄʜᴀɴᴛ sɪᴛᴇs.')}",
            parse_mode=ParseMode.HTML,
        )
        return

    keyword = " ".join(ctx.args)
    status_msg = await update.message.reply_text(
        f"{hdr()}\n\n{frame('sᴇᴀʀᴄʜɪɴɢ')}\n\n"
        f"{e_search()} {B('ᴅᴏʀᴋɪɴɢ ʙʀᴀᴠᴇ:')} {C(keyword)}\n"
        f"{I('ʙʏᴘᴀssɪɴɢ ᴄʟᴏᴜᴅғʟᴀʀᴇ / ᴛʟs...')}\n\n{ftr()}",
        parse_mode=ParseMode.HTML,
    )

    search_url = f"https://search.brave.com/search?q={quote(keyword)}"
    html = await fetch_page_bypass(search_url)

    if not html:
        await status_msg.edit_text(
            format_error("Failed to fetch Brave search results."),
            parse_mode=ParseMode.HTML,
        )
        return

    found_domains = extract_domains_from_brave_html(html)

    if not found_domains:
        await status_msg.edit_text(
            f"{e_cross()} {B('ɴᴏ ɴᴇᴡ ᴅᴏᴍᴀɪɴs ғᴏᴜɴᴅ.')}",
            parse_mode=ParseMode.HTML,
        )
        return

    # Add to working sites loader if loader is available
    loader = ctx.bot_data.get("loader")
    added_count = 0
    if loader:
        added_count = loader.add_sites(found_domains)

    results_preview = "\n".join(f"• {C(d)}" for d in found_domains[:15])
    total_str = f"Showing 15 of {len(found_domains)}" if len(found_domains) > 15 else f"Total: {len(found_domains)}"

    await status_msg.edit_text(
        f"{hdr()}\n\n{frame('ᴅᴏʀᴋ ʀᴇsᴜʟᴛs')}\n\n"
        f"{e_search()}   {B('ᴋᴇʏᴡᴏʀᴅ')} : {keyword}\n"
        f"{e_globe()}   {B('ғᴏᴜɴᴅ')}    : {len(found_domains)} ᴅᴏᴍᴀɪɴs\n"
        f"{e_folder()}  {B('ᴀᴅᴅᴇᴅ')}    : {added_count} ɴᴇᴡ\n\n"
        f"{results_preview}\n\n"
        f"<i>{total_str}</i>\n\n"
        f"{ftr()}",
        parse_mode=ParseMode.HTML,
    )


def register_dork_handlers(app):
    """Register /dork handler in Telegram app."""
    app.add_handler(CommandHandler("dork", dork_cmd))
