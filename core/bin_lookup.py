"""BIN lookup with API + SQLite cache + free fallback APIs."""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from aiohttp.resolver import ThreadedResolver

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=720)

# Free BIN lookup APIs (tried in order)
DEFAULT_BIN_APIS = [
    "https://lookup.binlist.net/",           # Free, no key needed
    "https://data.handyapi.com/bin/",         # Free, no key needed
]


class BinLookup:
    """BIN lookup with caching. Uses free APIs with SQLite fallback cache."""

    def __init__(self, conn: sqlite3.Connection, config: dict = None):
        self.conn = conn
        self.config = config or {}
        
        # Load APIs from config if available
        config_apis = self.config.get("bin_lookup", {}).get("apis")
        self.apis = config_apis if config_apis else DEFAULT_BIN_APIS
        self._mem_cache: dict[str, dict] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._ensure_table()

    def _ensure_table(self):
        """Create bin_cache table if it doesn't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bin_cache (
                bin TEXT PRIMARY KEY,
                bank TEXT,
                brand TEXT,
                type TEXT,
                level TEXT,
                country TEXT,
                flag TEXT,
                cached_at TIMESTAMP
            )
        """)
        self.conn.commit()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(limit=5, resolver=ThreadedResolver()),
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def lookup(self, bin_code: str) -> dict:
        """Look up BIN info. Returns dict with bank, brand, type, level, country, flag."""
        if not bin_code or len(bin_code) < 6:
            return self._empty(bin_code)

        bin_code = bin_code[:6]

        if bin_code in self._mem_cache:
            return self._mem_cache[bin_code]

        cached = self.conn.execute(
            "SELECT * FROM bin_cache WHERE bin = ?", (bin_code,)
        ).fetchone()
        
        if cached:
            # Enforce CACHE_TTL
            cached_at = cached["cached_at"]
            if cached_at:
                try:
                    dt = datetime.fromisoformat(cached_at)
                    if datetime.utcnow() - dt <= CACHE_TTL:
                        info = {
                            "bin": cached["bin"],
                            "bank": self._clean_cached(cached["bank"]),
                            "brand": self._clean_cached(cached["brand"]),
                            "type": self._clean_cached(cached["type"]),
                            "level": self._clean_cached(cached["level"]),
                            "country": self._clean_cached(cached["country"]),
                            "flag": cached["flag"] or "",
                        }
                        self._mem_cache[bin_code] = info
                        return info
                except (ValueError, TypeError):
                    pass
            # If expired or missing timestamp, we fetch a fresh one

        info = await self._api_lookup(bin_code)

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
        """Call BIN APIs. Falls back to generic info on failure."""
        # Try configured APIs first
        for api in self.apis:
            result = await self._try_api(api, bin_code)
            if result:
                return result

        return self._guess_info(bin_code)

    async def _try_api(self, base_url: str, bin_code: str) -> Optional[dict]:
        """Try a single BIN API. Returns dict or None on failure."""
        try:
            url = f"{base_url.rstrip('/')}/{bin_code}"
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_response(data, bin_code)
        except Exception as e:
            logger.debug("BIN API %s failed for %s: %s", base_url, bin_code, e)
        return None

    def _parse_response(self, data: dict, bin_code: str) -> dict:
        """Parse API response into standard format. Handles binlist.net and handyapi formats."""
        # binlist.net format
        if "scheme" in data or "brand" in data:
            country = data.get("country", {})
            bank = data.get("bank", {})
            return {
                "bin": bin_code,
                "bank": bank.get("name", "Unknown") if isinstance(bank, dict) else str(bank or "Unknown"),
                "brand": (data.get("scheme") or data.get("brand") or "Unknown").upper(),
                "type": (data.get("type") or "Unknown").upper(),
                "level": (data.get("level") or "Unknown").upper(),
                "country": country.get("name", "Unknown") if isinstance(country, dict) else str(country or "Unknown"),
                "flag": country.get("emoji", "") if isinstance(country, dict) else "",
            }

        # handyapi format
        if "Scheme" in data or "Brand" in data:
            return {
                "bin": bin_code,
                "bank": data.get("Issuer", "Unknown"),
                "brand": (data.get("Scheme") or data.get("Brand") or "Unknown").upper(),
                "type": (data.get("Type") or "Unknown").upper(),
                "level": (data.get("Level") or "Unknown").upper(),
                "country": data.get("Country", {}).get("Name", "Unknown") if isinstance(data.get("Country"), dict) else "Unknown",
                "flag": data.get("Country", {}).get("Emoji", "") if isinstance(data.get("Country"), dict) else "",
            }

        # Generic: try to extract known fields
        return {
            "bin": bin_code,
            "bank": self._extract_str(data, ("bank", "issuer", "Issuer"), "Unknown"),
            "brand": self._extract_str(data, ("brand", "scheme", "Scheme"), "Unknown").upper(),
            "type": self._extract_str(data, ("type", "Type"), "Unknown").upper(),
            "level": self._extract_str(data, ("level", "Level"), "Unknown").upper(),
            "country": self._extract_str(data, ("country", "Country"), "Unknown"),
            "flag": "",
        }

    @staticmethod
    def _extract_str(data: dict, keys: tuple, default: str = "Unknown") -> str:
        """Extract a string value from nested dict, handling dict/None/empty values."""
        for k in keys:
            val = data.get(k)
            if val is None:
                continue
            if isinstance(val, dict):
                # Try common sub-keys for nested objects
                for sub in ("name", "Name", "title", "Title"):
                    if sub in val:
                        return str(val[sub]) or default
                # Empty dict — skip
                continue
            s = str(val).strip()
            if s and s != "{}":
                return s
        return default

    @staticmethod
    def _clean_cached(val) -> str:
        """Clean a cached DB value — convert None, empty, or '{}' to 'Unknown'."""
        if not val:
            return "Unknown"
        s = str(val).strip()
        if s in ("", "{}", "None"):
            return "Unknown"
        return s

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
    abbr = upper[:2]
    if abbr in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[abbr]
    return ""
