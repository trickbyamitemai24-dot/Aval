"""Brave Search Dorker Handler — handlers/dork_handler.py

Ported from autoShopify/dork.py.
Scrapes organic result URLs across multiple pages on search.brave.com using curl_cffi.
Extracts 1 URL per root domain, filters big platforms, and adds results directly to stores.
"""

from __future__ import annotations

import re
import asyncio
import html as _html_mod
import logging
from urllib.parse import quote_plus, urlparse
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from curl_cffi.requests import AsyncSession
from core.tier_manager import is_admin, is_owner
from core.database import is_banned
from templates.messages import hdr, ftr, frame, format_error, sc, C, B, I
from templates.emojis import e_search, e_globe, e_check_done, e_cross, e_rocket, e_folder

logger = logging.getLogger(__name__)

BASE_URL    = "https://search.brave.com/search"
MAX_PAGES   = 5
PAGE_DELAY  = 1.0
REQ_TIMEOUT = 30

_HEADERS_BASE = {
    "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-encoding":           "gzip, deflate",
    "accept-language":           "en-US,en;q=0.6",
    "priority":                  "u=0, i",
    "sec-ch-ua":                 '"Brave";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile":          "?0",
    "sec-ch-ua-platform":        '"Windows"',
    "sec-fetch-dest":            "document",
    "sec-fetch-mode":            "navigate",
    "sec-fetch-user":            "?1",
    "sec-gpc":                   "1",
    "upgrade-insecure-requests": "1",
    "user-agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
}

_BRAVE_DOMAINS = {
    "search.brave.com", "safesearch.brave.com", "cdn.search.brave.com",
    "brave.com", "accounts.brave.com", "brave.app", "status.brave.app",
}

_BLOCKED_DOMAINS = {
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "pinterest.com", "tiktok.com", "reddit.com", "snapchat.com",
    "telegram.org", "t.me", "whatsapp.com", "discord.com", "tumblr.com",
    "youtube.com", "youtu.be", "vimeo.com", "twitch.tv",
    "play.google.com", "apps.apple.com", "apple.com", "microsoft.com",
    "amazon.com", "amazon.co.uk", "ebay.com", "etsy.com", "walmart.com", "shopify.com",
    "github.com", "stackoverflow.com", "medium.com",
    "google.com", "bing.com", "yahoo.com", "duckduckgo.com",
    "wikipedia.org", "cloudflare.com", "wordpress.com", "wix.com",
}

_SHORT_SLD = {"co", "com", "org", "net", "gov", "edu", "ac", "me", "ne", "or"}


def _root_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in _SHORT_SLD:
            return ".".join(parts[-3:])
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return host
    except Exception:
        return url


def _is_blocked(root: str) -> bool:
    if any(root == bd or root.endswith("." + bd) for bd in _BRAVE_DOMAINS):
        return True
    if any(root == bd or root.endswith("." + bd) for bd in _BLOCKED_DOMAINS):
        return True
    return False


def _extract_urls(html_str: str) -> list[str]:
    seen_href = set()
    urls = []
    for href in re.findall(r'href=["\']?(https?://[^"\'>\s]+)', html_str):
        href = _html_mod.unescape(href)
        if "brave.com" in href:
            href = href.split("?")[0]
        if href.endswith((".css", ".js", ".woff2", ".woff", ".png", ".jpg", ".svg", ".ico")):
            continue
        if href not in seen_href:
            seen_href.add(href)
            urls.append(href)
    return urls


async def scrape_dork(query: str, max_pages: int = MAX_PAGES) -> list[str]:
    all_urls = []
    seen_domains = set()
    q_enc = quote_plus(query)

    async with AsyncSession(impersonate="chrome131") as session:
        for page in range(max_pages):
            if page == 0:
                url = f"{BASE_URL}?q={q_enc}&source=desktop"
                headers = {**_HEADERS_BASE, "sec-fetch-site": "none"}
            else:
                url = f"{BASE_URL}?q={q_enc}&offset={page}&spellcheck=0"
                headers = {
                    **_HEADERS_BASE,
                    "referer": f"{BASE_URL}?q={q_enc}&source=desktop",
                    "sec-fetch-site": "same-origin",
                }

            try:
                resp = await session.get(url, headers=headers, timeout=REQ_TIMEOUT)
                if resp.status_code != 200 or not resp.text:
                    break

                raw_urls = _extract_urls(resp.text)
                new_added = 0
                for u in raw_urls:
                    root = _root_domain(u)
                    if _is_blocked(root) or root in seen_domains:
                        continue
                    seen_domains.add(root)
                    all_urls.append(f"https://{root}")
                    new_added += 1

                if new_added == 0 and page > 0:
                    break

            except Exception as exc:
                logger.warning("Dork page %d error: %s", page + 1, exc)
                break

            if page < max_pages - 1:
                await asyncio.sleep(PAGE_DELAY)

    return all_urls


async def dork_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if not (is_owner(user.id) or is_admin(conn, user.id)):
        await update.message.reply_text(format_error("Admin command only."), parse_mode=ParseMode.HTML)
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
        f"{I('sᴄʀᴀᴘɪɴɢ ᴍᴜʟᴛɪ-ᴘᴀɢᴇ ʀᴇsᴜʟᴛs...')}\n\n{ftr()}",
        parse_mode=ParseMode.HTML,
    )

    found_domains = await scrape_dork(keyword, max_pages=5)

    if not found_domains:
        await status_msg.edit_text(
            f"{e_cross()} {B('ɴᴏ ɴᴇᴡ ᴅᴏᴍᴀɪɴs ғᴏᴜɴᴅ.')}",
            parse_mode=ParseMode.HTML,
        )
        return

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
    app.add_handler(CommandHandler("dork", dork_cmd))
