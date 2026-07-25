"""Card parsing, validation, and normalization.

Supports 4 formats:
  - Pipe:  4798510629051356|12|2028|893
  - Colon:  4798510629051356:12:2028:893
  - Space:  4798510629051356 12 2028 893
  - Comma:  4798510629051356,12,2028,893
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Card:
    number: str
    month: str
    year: str
    cvv: str
    raw: str

    @property
    def bin(self) -> str:
        return self.number[:6]

    @property
    def last4(self) -> str:
        return self.number[-4:]

    @property
    def masked(self) -> str:
        """Masked format: 479851******1356|12|2028|893"""
        n = self.number
        masked_num = n[:6] + "*" * (len(n) - 10) + n[-4:]
        return f"{masked_num}|{self.month}|{self.year}|{self.cvv}"


def parse_card(raw: str) -> Optional[Card]:
    """Parse a single card line. Returns Card or None if invalid."""
    raw = raw.strip()
    if not raw:
        return None

    # Strip out non-card content before parsing
    # Card strings might have leading/trailing garbage
    # Let's extract the longest run of characters that could be a card
    
    # First just clean up internal spaces if using another separator
    clean_raw = raw
    if "|" in clean_raw or ":" in clean_raw or "," in clean_raw:
        # Some people copy cards like "4111 1111 1111 1111 | 12 | 2026 | 123"
        # We should just let the split handle it, but if they have spaces AND colons,
        # parts[0] = "4111 1111..." which fails isdigit().
        pass

    # Try each separator
    for sep in ["|", ":", ",", " "]:
        parts = [p.strip() for p in raw.split(sep)]
        if len(parts) >= 4:
            # Clean up internal spaces from parts (e.g. "4111 1111" -> "41111111")
            number = parts[0].replace(" ", "")
            month = parts[1].replace(" ", "")
            year = parts[2].replace(" ", "")
            cvv = parts[3].replace(" ", "")

            # Validate number: 12-19 digits
            if not number.isdigit() or not (12 <= len(number) <= 19):
                continue

            # Validate month: 2 digits, 01-12
            if not month.isdigit():
                continue
            if not (1 <= int(month) <= 12):
                continue
            month = month.zfill(2)

            # Validate year: 2 or 4 digits
            if not year.isdigit():
                continue
            if len(year) == 2:
                year = "20" + year
            if len(year) != 4:
                continue

            # Validate CVV: 3-4 digits
            if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
                continue

            return Card(number=number, month=month.zfill(2),
                        year=year, cvv=cvv, raw=raw)

    return None


def parse_card_list(text: str) -> list[Card]:
    """Parse multiple card lines from text. Skips invalid lines."""
    cards = []
    for line in text.strip().splitlines():
        card = parse_card(line)
        if card:
            cards.append(card)
    return cards


def luhn_valid(number: str) -> bool:
    """Validate card number using Luhn algorithm."""
    total = 0
    reverse = number[::-1]
    for i, digit in enumerate(reverse):
        d = int(digit)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_expired(month: str, year: str) -> bool:
    """Check if card is expired. Cards expire at end of the month."""
    import datetime
    try:
        m = int(month)
        y = int(year)
        now = datetime.datetime.utcnow()
        # Card valid until end of expiry month
        if y < now.year:
            return True
        if y == now.year and m < now.month:
            return True
        return False
    except (ValueError, TypeError):
        return True