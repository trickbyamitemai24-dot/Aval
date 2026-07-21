"""BIN lookup with API + SQLite cache."""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver

logger = logging.getLogger(__name__)

# Fallback bin data for common BINs when API fails or is unavailable
# This provides basic info for testing without external API
CACHE_TTL = timedelta(hours=720)


class BinLookup:
    """BIN lookup with caching. Uses bins.ws API with SQLite fallback cache."""

    def __init__(self, conn: sqlite3.Connection, api_url: str = ""):
        self.conn = conn
        self.api_url = api_url
        self._mem_cache: dict[str, dict] = {}

    async def lookup(self, bin_code: str) -> dict:
        """Look up BIN info. Returns dict with bank, brand, type, level, country, flag."""
        if not bin_code or len(bin_code) < 6:
            return self._empty(bin_code)

        bin_code = bin_code[:6]

        # Memory cache
        if bin_code in self._mem_cache:
            return self._mem_cache[bin_code]

        # SQLite cache
        cached = self.conn.execute(
            "SELECT * FROM bin_cache WHERE bin = ?", (bin_code,)
        ).fetchone()
        if cached:
            info = dict(cached)
            self._mem_cache[bin_code] = info
            return info

        # API call
        info = await self._api_lookup(bin_code)

        # Cache to SQLite
        self.conn.execute(
            """INSERT OR REPLACE INTO bin_cache
               (bin, bank, brand, type, level, country, flag, cached_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (bin_code, info["bank"], info["brand"], info["type"],
             info["level"], info["country"], info.get("flag", ""),
             datetime.utcnow().isoformat()),
        )
        self.conn.commit()
        self._mem_cache[bin_code] = info
        return info

    async def _api_lookup(self, bin_code: str) -> dict:
        """Call BIN API. Falls back to generic info on failure."""
        if not self.api_url:
            return self._guess_info(bin_code)

        try:
            url = f"{self.api_url}{bin_code}"
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=ThreadedResolver())) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "bin": bin_code,
                            "bank": data.get("bank", {}).get("name", "Unknown"),
                            "brand": data.get("brand", "Unknown"),
                            "type": data.get("type", "Unknown"),
                            "level": data.get("level", "Unknown"),
                            "country": data.get("country", {}).get("name", "Unknown"),
                            "flag": data.get("country", {}).get("flag", ""),
                        }
        except Exception as e:
            logger.warning("BIN API failed for %s: %s", bin_code, e)

        return self._guess_info(bin_code)

    def _guess_info(self, bin_code: str) -> dict:
        """Fallback: guess brand from first digit. Returns generic info."""
        first = bin_code[0] if bin_code else ""
        brand_map = {"4": "VISA", "5": "MASTERCARD", "3": "AMERICAN EXPRESS", "6": "DISCOVER"}
        brand = brand_map.get(first, "Unknown")
        return {
            "bin": bin_code,
            "bank": "Unknown",
            "brand": brand,
            "type": "Unknown",
            "level": "Unknown",
            "country": "Unknown",
            "flag": "",
        }

    def _empty(self, bin_code: str) -> dict:
        return {
            "bin": bin_code or "",
            "bank": "Unknown",
            "brand": "Unknown",
            "type": "Unknown",
            "level": "Unknown",
            "country": "Unknown",
            "flag": "",
        }


# Country flag emoji mapping (common countries)
COUNTRY_FLAGS = {
    "UNITED STATES": "🇺🇸", "UNITEDSTATES": "🇺🇸", "US": "🇺🇸",
    "UNITED KINGDOM": "🇬🇧", "UK": "🇬🇧", "GB": "🇬🇧",
    "CANADA": "🇨🇦", "CA": "🇨🇦",
    "AUSTRALIA": "🇦🇺", "AU": "🇦🇺",
    "GERMANY": "🇩🇪", "DE": "🇩🇪",
    "FRANCE": "🇫🇷", "FR": "🇫🇷",
    "BRAZIL": "🇧🇷", "BR": "🇧🇷",
    "INDIA": "🇮🇳", "IN": "🇮🇳",
    "JAPAN": "🇯🇵", "JP": "🇯🇵",
    "MEXICO": "🇲🇽", "MX": "🇲🇽",
    "NETHERLANDS": "🇳🇱", "NL": "🇳🇱",
    "SPAIN": "🇪🇸", "ES": "🇪🇸",
    "ITALY": "🇮🇹", "IT": "🇮🇹",
    "CHINA": "🇨🇳", "CN": "🇨🇳",
    "RUSSIA": "🇷🇺", "RU": "🇷🇺",
    "TURKEY": "🇹🇷", "TR": "🇹🇷",
    "SINGAPORE": "🇸🇬", "SG": "🇸🇬",
    "SWEDEN": "🇸🇪", "SE": "🇸🇪",
    "SWITZERLAND": "🇨🇭", "CH": "🇨🇭",
    "IRELAND": "🇮🇪", "IE": "🇮🇪",
    "PORTUGAL": "🇵🇹", "PT": "🇵🇹",
    "POLAND": "🇵🇱", "PL": "🇵🇱",
    "SOUTH AFRICA": "🇿🇦", "ZA": "🇿🇦",
    "ARGENTINA": "🇦🇷", "AR": "🇦🇷",
    "COLOMBIA": "🇨🇴", "CO": "🇨🇴",
    "CHILE": "🇨🇱", "CL": "🇨🇱",
    "UAE": "🇦🇪", "DUBAI": "🇦🇪",
    "SAUDI ARABIA": "🇸🇦", "SA": "🇸🇦",
    "INDONESIA": "🇮🇩", "ID": "🇮🇩",
    "MALAYSIA": "🇲🇾", "MY": "🇲🇾",
    "PHILIPPINES": "🇵🇭", "PH": "🇵🇭",
    "THAILAND": "🇹🇭", "TH": "🇹🇭",
    "VIETNAM": "🇻🇳", "VN": "🇻🇳",
    "EGYPT": "🇪🇬", "EG": "🇪🇬",
    "NIGERIA": "🇳🇬", "NG": "🇳🇬",
    "KENYA": "🇰🇪", "KE": "🇰🇪",
    "BELGIUM": "🇧🇪", "BE": "🇧🇪",
    "AUSTRIA": "🇦🇹", "AT": "🇦🇹",
    "DENMARK": "🇩🇰", "DK": "🇩🇰",
    "FINLAND": "🇫🇮", "FI": "🇫🇮",
    "NORWAY": "🇳🇴", "NO": "🇳🇴",
    "GREECE": "🇬🇷", "GR": "🇬🇷",
    "CZECH": "🇨🇿", "CZ": "🇨🇿",
    "ROMANIA": "🇷🇴", "RO": "🇷🇴",
    "NEW ZEALAND": "🇳🇿", "NZ": "🇳🇿",
    "PAKISTAN": "🇵🇰", "PK": "🇵🇰",
    "BANGLADESH": "🇧🇩", "BD": "🇧🇩",
    "ISRAEL": "🇮🇱", "IL": "🇮🇱",
    "HONG KONG": "🇭🇰", "HK": "🇭🇰",
}


def get_flag(country: str) -> str:
    """Get flag emoji for a country name."""
    if not country:
        return ""
    upper = country.upper().strip()
    if upper in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[upper]
    # Try abbreviation
    abbr = upper[:2]
    if abbr in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[abbr]
    return ""