"""Load and manage Shopify store URLs from sites/ directory."""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StoreLoader:
    """Loads store URLs from .txt files, deduplicates, normalizes."""

    def __init__(self, sites_dir: str = "sites"):
        self.sites_dir = Path(sites_dir)
        self._cache: dict[str, list[str]] = {}

    def _load_file(self, filename: str) -> list[str]:
        """Load URLs from a single file. Returns deduplicated, normalized list."""
        filepath = self.sites_dir / filename
        if not filepath.exists():
            logger.warning("Store file not found: %s", filepath)
            return []

        urls = set()
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and line.startswith("http"):
                    # Remove trailing slash for consistency
                    url = line.rstrip("/")
                    urls.add(url)
        logger.info("Loaded %d unique URLs from %s", len(urls), filename)
        return list(urls)

    def get_stores(self, price_range: str = "all") -> list[str]:
        """Get store URLs for a price range.

        Args:
            price_range: '5', '10', 'all', 'hq', or filename
        Returns:
            List of store URLs
        """
        if price_range in self._cache:
            return self._cache[price_range]

        if price_range == "5":
            urls = self._load_file("5$.txt")
        elif price_range == "10":
            urls = self._load_file("10$.txt")
        elif price_range == "all":
            urls = self._load_file("working.txt")
        elif price_range == "hq":
            urls = self._load_file("hq.txt")
        elif price_range == "v40":
            urls = self._load_file("v40.txt")
        else:
            # Treat as filename
            urls = self._load_file(price_range)

        self._cache[price_range] = urls
        return urls

    def get_counts(self) -> dict[str, int]:
        """Get store count for each price range (for inline buttons)."""
        return {
            "5": len(self.get_stores("5")),
            "10": len(self.get_stores("10")),
            "all": len(self.get_stores("all")),
            "hq": len(self.get_stores("hq")),
            "v40": len(self.get_stores("v40")),
        }

    def reload(self):
        """Clear cache and reload all files."""
        self._cache.clear()
        logger.info("Store cache cleared")


def pick_store(stores: list[str], used: set[str]) -> Optional[str]:
    """Pick a random store that hasn't been used recently.
    
    Args:
        stores: List of store URLs
        used: Set of recently used store URLs
    Returns:
        A store URL, or None if stores is empty
    """
    import random
    
    if not stores:
        return None

    available = [s for s in stores if s not in used]
    if not available:
        used.clear()
        available = stores

    store = random.choice(available)
    used.add(store)
    return store