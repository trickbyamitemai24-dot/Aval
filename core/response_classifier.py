"""Response classifier — maps Shopify/Stripe responses to status."""

# Expanded Shopify/Stripe response codes mapped to classifications
RESPONSE_MAP = {
    # CHARGED — payment succeeded or processing
    "succeeded":           ("CHARGED", "succeeded"),
    "processing":          ("CHARGED", "processing"),
    "completed":           ("CHARGED", "completed"),
    "paid":                ("CHARGED", "paid"),
    "capture":             ("CHARGED", "captured"),
    "approved":            ("CHARGED", "approved"),

    # LIVE — card is valid but payment didn't complete / soft decline
    "requires_action":     ("LIVE_3DS", "3ds_required"),
    "insufficient_funds":  ("LIVE", "insufficient_funds"),
    "test_mode_live_card": ("LIVE", "test_mode_live_card"),
    "call_issuer":         ("LIVE", "call_issuer"),
    "do_not_honor":        ("LIVE", "do_not_honor"),
    "3d_secure":           ("LIVE_3DS", "3ds_required"),
    "3ds":                 ("LIVE_3DS", "3ds_required"),
    "redirect":            ("LIVE_3DS", "3ds_redirect"),
    "pickup_card":         ("LIVE", "pickup_card"),
    "transaction_needs_verification": ("LIVE_3DS", "3ds_required"),
    "transaction_not_allowed": ("LIVE", "transaction_not_allowed"),
    "amount_too_large":    ("LIVE", "amount_too_large"),
    "withdrawal_count_limit_exceeded": ("LIVE", "withdrawal_limit_exceeded"),
    "authentication_required": ("LIVE_3DS", "3ds_required"),
    "requires_payment_method": ("LIVE", "requires_payment_method"),
    "approve_with_id":     ("LIVE", "approve_with_id"),
    "issuer_not_available": ("LIVE", "issuer_not_available"),
    "verify_address":      ("LIVE", "verify_address"),

    # DEAD — hard decline
    "card_declined":       ("DEAD", "card_declined"),
    "incorrect_cvc":       ("DEAD", "incorrect_cvc"),
    "invalid_cvc":         ("DEAD", "incorrect_cvc"),
    "invalid_number":      ("DEAD", "invalid_number"),
    "expired_card":        ("DEAD", "expired_card"),
    "generic_decline":     ("DEAD", "generic_decline"),
    "processor_declined":  ("DEAD", "processor_declined"),
    "fraudulent":          ("DEAD", "fraudulent"),
    "stolen_card":         ("DEAD", "stolen_card"),
    "lost_card":           ("DEAD", "lost_card"),
    "invalid_expiry_month": ("DEAD", "invalid_expiry_month"),
    "invalid_expiry_year":  ("DEAD", "invalid_expiry_year"),
    "blocked":             ("DEAD", "blocked"),
    "security_violation":  ("DEAD", "security_violation"),
    "invalid_zip":         ("DEAD", "invalid_zip"),
    "incorrect_number":    ("DEAD", "incorrect_number"),
    "card_velocity_exceeded": ("DEAD", "velocity_exceeded"),
    "rejected":            ("DEAD", "rejected"),
    "processing_error":    ("DEAD", "processing_error"),
    "reenter_transaction": ("DEAD", "reenter_transaction"),
    "card_not_supported":  ("DEAD", "card_not_supported"),
    "currency_not_supported": ("DEAD", "currency_not_supported"),
}

def classify_shopify_response(status_code: int, response_body: dict | str) -> tuple[str, str]:
    """Classify a Shopify checkout response.
    
    Args:
        status_code: HTTP status code
        response_body: Response body (dict or raw string)
    Returns:
        Tuple of (status, message) where status is CHARGED, LIVE, LIVE_3DS, or DEAD
    """
    body_str = str(response_body).lower()

    # Priority exact matching from body dictionary if possible
    if isinstance(response_body, dict):
        # Traverse for error codes
        if "error" in response_body:
            err = response_body["error"]
            if isinstance(err, dict):
                code = err.get("code") or err.get("decline_code") or err.get("type")
                if code and code.lower() in RESPONSE_MAP:
                    return RESPONSE_MAP[code.lower()]
            elif isinstance(err, str) and err.lower() in RESPONSE_MAP:
                return RESPONSE_MAP[err.lower()]

    # Fallback string matching
    for key, (classification, message) in RESPONSE_MAP.items():
        if key in body_str:
            return classification, message

    # Check HTTP status heuristics
    if status_code in (200, 201, 202):
        if "succeeded" in body_str or "processing" in body_str:
            return "CHARGED", "succeeded"
        if "requires_action" in body_str or "3ds" in body_str or "challenge" in body_str:
            return "LIVE_3DS", "3ds_required"
        if "insufficient" in body_str:
            return "LIVE", "insufficient_funds"
        if "declined" in body_str:
            return "DEAD", "card_declined"
        return "DEAD", "unknown_decline"

    if status_code == 402:
        return "DEAD", "card_declined"

    if 400 <= status_code < 500:
        if "fraud" in body_str or "risk" in body_str:
            return "DEAD", "fraud_blocked"
        return "DEAD", "card_declined"

    if status_code >= 500:
        return "DEAD", "processor_error"

    return "DEAD", "unknown"