"""Auto-Proxy Scraper & Captcha Solver Integration — core/proxy_scraper.py

Scrapes public/API proxy sources, solves captchas via Captcha APIs (NopeCHA / Capsolver),
validates live proxies, and automatically inserts clean proxies into user_proxies table.
"""

import re
import aiohttp
import asyncio
import logging
from typing import List, Optional, Dict, Any

from core.bypass_client import fetch_page_bypass
from core.proxy_manager import normalize_proxy, ProxyManager

logger = logging.getLogger(__name__)

# Default free public proxy endpoints for scraping
PUBLIC_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
]


class CaptchaSolver:
    """Interface for external Captcha Solver APIs (NopeCHA / Capsolver / 2Captcha)."""

    def __init__(self, api_key: str = "", provider: str = "nopecha"):
        self.api_key = api_key
        self.provider = provider.lower()

    async def solve_recaptcha(self, sitekey: str, page_url: str) -> Optional[str]:
        """Solve ReCaptcha v2/v3 token."""
        if not self.api_key:
            logger.warning("No Captcha API key configured.")
            return None

        async with aiohttp.ClientSession() as session:
            try:
                if self.provider == "nopecha":
                    url = "https://api.nopecha.com/"
                    payload = {
                        "key": self.api_key,
                        "type": "recaptcha",
                        "sitekey": sitekey,
                        "url": page_url,
                    }
                    async with session.post(url, json=payload, timeout=30) as resp:
                        res = await resp.json()
                        if res.get("data"):
                            return res["data"]
                        job_id = res.get("id")
                        if job_id:
                            # Poll for solution
                            for _ in range(15):
                                await asyncio.sleep(2)
                                async with session.get(f"{url}?key={self.api_key}&id={job_id}") as poll_resp:
                                    poll_res = await poll_resp.json()
                                    if poll_res.get("data"):
                                        return poll_res["data"]
                elif self.provider == "capsolver":
                    url = "https://api.capsolver.com/createTask"
                    payload = {
                        "clientKey": self.api_key,
                        "task": {
                            "type": "ReCaptchaV2TaskProxyLess",
                            "websiteURL": page_url,
                            "websiteKey": sitekey,
                        }
                    }
                    async with session.post(url, json=payload, timeout=30) as resp:
                        res = await resp.json()
                        task_id = res.get("taskId")
                        if task_id:
                            for _ in range(15):
                                await asyncio.sleep(2)
                                async with session.post("https://api.capsolver.com/getTaskResult", json={"clientKey": self.api_key, "taskId": task_id}) as poll_resp:
                                    poll_res = await poll_resp.json()
                                    if poll_res.get("status") == "ready":
                                        return poll_res.get("solution", {}).get("gRecaptchaResponse")
            except Exception as e:
                logger.error("Captcha solving error (%s): %s", self.provider, e)
        return None


async def scrape_public_proxies() -> List[str]:
    """Fetch raw proxies from public endpoints."""
    raw_proxies = set()
    async with aiohttp.ClientSession() as session:
        for url in PUBLIC_PROXY_SOURCES:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        found = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b', text)
                        raw_proxies.update(found)
            except Exception as e:
                logger.debug("Failed to scrape %s: %s", url, e)
    return list(raw_proxies)


async def auto_scrape_and_save_proxies(pm: ProxyManager, user_id: int, max_valid: int = 50) -> int:
    """Scrape, validate, and dump live proxies directly into user_proxies table."""
    scraped = await scrape_public_proxies()
    if not scraped:
        return 0
    
    logger.info("Scraped %d potential proxies for user %d", len(scraped), user_id)
    
    # Filter and normalize
    normalized = [normalize_proxy(p) for p in scraped[:300] if normalize_proxy(p)]
    
    # Validate against Shopify test endpoint
    valid_proxies = await pm.check_list(normalized)
    
    if valid_proxies:
        added = pm.add_proxies(user_id, valid_proxies[:max_valid])
        logger.info("Auto-added %d verified proxies for user %d", added, user_id)
        return added
    
    return 0
