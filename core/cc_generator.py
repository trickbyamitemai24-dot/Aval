"""Luhn-valid credit card generator.

Generates card numbers that pass the Luhn check.
Supports:
  - Random BIN (from a curated pool) or user-supplied BIN prefix
  - Random future expiry dates (MM/YYYY)
  - Random CVV (3 or 4 digits depending on card length/brand)
  - Single or batch generation
"""

import random
from datetime import datetime
from typing import Optional

from core.card_parser import luhn_valid


# Curated BIN pool (6-digit prefixes) covering common brands/issuers.
# All are real BIN ranges — generation only produces Luhn-valid *numbers*,
# never real accounts.
BIN_POOL = [
    "479851",  # VISA
    "453264",  # VISA
    "411111",  # VISA (test range)
    "518600",  # Mastercard
    "555555",  # Mastercard
    "542418",  # Mastercard
    "377178",  # AMEX (15-digit)
    "601100",  # Discover
    "601111",  # Discover
    "352800",  # JCB
    "354900",  # JCB
    "675910",  # Maestro
    "627780",  # Maestro
]

# BIN prefix → total card length
BIN_LENGTH = {
    "377178": 15,   # AMEX
}
DEFAULT_LENGTH = 16

# BIN prefix → CVV length
BIN_CVV_LEN = {
    "377178": 4,    # AMEX uses 4-digit CID
}
DEFAULT_CVV_LEN = 3


def _card_length(bin_prefix: str) -> int:
    return BIN_LENGTH.get(bin_prefix[:6], DEFAULT_LENGTH)


def _cvv_len(bin_prefix: str) -> int:
    return BIN_CVV_LEN.get(bin_prefix[:6], DEFAULT_CVV_LEN)


def _luhn_check_digit(partial: str) -> str:
    """Calculate the Luhn check digit for a partial number (missing last digit)."""
    total = 0
    reverse = partial[::-1]
    for i, digit in enumerate(reverse):
        d = int(digit)
        # The check digit sits at index 0 (rightmost); the digit to its
        # left is at index 1 (doubled), etc. Since we're computing the
        # check digit, the partial number's rightmost char is index 0
        # and should NOT be doubled. So double at odd indices.
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - (total % 10)) % 10
    return str(check)


def generate_number(bin_prefix: str, length: Optional[int] = None) -> str:
    """Generate a single Luhn-valid card number starting with bin_prefix.

    Args:
        bin_prefix: Leading digits (1-10 chars). Padded to `length`.
        length:    Total card length. Defaults to brand default (16, AMEX=15).
    Returns:
        Full card number string (digits only).
    """
    if length is None:
        length = _card_length(bin_prefix)

    # Build the number minus the check digit
    body = bin_prefix
    remaining = length - len(body) - 1
    if remaining < 0:
        # BIN already fills the number — trim and recalc
        body = body[: length - 1]
        remaining = 0
    body += "".join(str(random.randint(0, 9)) for _ in range(remaining))

    check = _luhn_check_digit(body)
    number = body + check

    # Safety: ensure Luhn validity (should always pass)
    if not luhn_valid(number):
        return generate_number(bin_prefix, length)
    return number


def generate_expiry(fixed_month: Optional[str] = None,
                    fixed_year: Optional[str] = None) -> tuple[str, str]:
    """Generate a (month, year) expiry pair.

    If fixed values are given they are returned (zero-padded).
    Otherwise a random future month/year is generated (1-6 years ahead).
    """
    if fixed_month and fixed_year:
        m = str(fixed_month).strip().zfill(2)
        y = str(fixed_year).strip()
        if len(y) == 2:
            y = "20" + y
        return m, y

    now = datetime.utcnow()
    # 1 to 6 years ahead
    year = now.year + random.randint(1, 6)
    month = random.randint(1, 12)
    return f"{month:02d}", str(year)


def generate_cvv(bin_prefix: str) -> str:
    """Generate a random CVV of the correct length for the brand."""
    length = _cvv_len(bin_prefix)
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def generate_card(bin_prefix: Optional[str] = None,
                  fixed_month: Optional[str] = None,
                  fixed_year: Optional[str] = None) -> str:
    """Generate one full card string: number|month|year|cvv."""
    if not bin_prefix:
        bin_prefix = random.choice(BIN_POOL)
    bin_prefix = bin_prefix.strip()

    number = generate_number(bin_prefix)
    month, year = generate_expiry(fixed_month, fixed_year)
    cvv = generate_cvv(bin_prefix)

    return f"{number}|{month}|{year}|{cvv}"


def generate_cards(count: int,
                   bin_prefix: Optional[str] = None,
                   fixed_month: Optional[str] = None,
                   fixed_year: Optional[str] = None) -> list[str]:
    """Generate `count` unique Luhn-valid card strings."""
    cards: list[str] = []
    seen: set[str] = set()
    attempts = 0
    max_attempts = count * 20
    while len(cards) < count and attempts < max_attempts:
        attempts += 1
        card = generate_card(bin_prefix, fixed_month, fixed_year)
        if card not in seen:
            seen.add(card)
            cards.append(card)
    return cards


def normalize_bin(raw: str) -> Optional[str]:
    """Normalize a raw BIN input. Returns digits or None if invalid.

    Accepts 1-10 leading digits. Non-digits are stripped.
    """
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if 1 <= len(digits) <= 10:
        return digits
    return None
