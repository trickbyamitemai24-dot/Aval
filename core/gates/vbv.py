"""3D Secure / VBV Detection Engine — core/gates/vbv.py

Classifies 3DS OTP verification triggers vs card decline vs approved status.
"""

import re
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Keywords indicating 3DS / OTP / VBV Verification required
VBV_3DS_KEYWORDS = [
    "3d_secure", "three_d_secure", "3ds", "otp_required", "redirect_to_issuer",
    "authentication_required", "verify_card", "cardholder_authentication",
    "challenge_required", "card_error_authentication_required", "3ds_challenge",
    "bank_verification", "vbv_required", "secure_code"
]

DECLINED_KEYWORDS = [
    "card_declined", "insufficient_funds", "do_not_honor", "stolen_card",
    "lost_card", "expired_card", "incorrect_cvv", "invalid_cvv", "pickup_card",
    "generic_decline", "restricted_card", "fraudulent"
]

CHARGED_KEYWORDS = [
    "succeeded", "charged", "approved", "thank_you", "order_completed",
    "payment_successful", "100_percent_off"
]


def classify_gate_response(response_text: str, status_code: int = 200) -> Tuple[str, str]:
    """Classify gateway HTTP payload into (STATUS, HUMAN_MESSAGE).

    STATUS can be:
    - 'CHARGED': successful authorization / purchase
    - 'LIVE_3DS': 3DS OTP / VBV verification challenge required (Live card)
    - 'LIVE': Approved without charge
    - 'DEAD': Card decline / insufficient funds
    - 'ERROR': Technical error
    """
    txt = response_text.lower()

    # Check 3DS VBV triggers
    if any(kw in txt for kw in VBV_3DS_KEYWORDS):
        return ("LIVE_3DS", "3DS OTP Verification Required (Live)")

    # Check Charged / Succeeded
    if any(kw in txt for kw in CHARGED_KEYWORDS):
        return ("CHARGED", "Payment Authorized / Charged Successfully")

    # Check Decline
    if any(kw in txt for kw in DECLINED_KEYWORDS):
        for kw in DECLINED_KEYWORDS:
            if kw in txt:
                return ("DEAD", f"Card Declined ({kw.replace('_', ' ').title()})")
        return ("DEAD", "Card Declined")

    if status_code in (200, 201):
        return ("LIVE", "Approved / Live Card")

    return ("DEAD", f"Declined (HTTP {status_code})")
