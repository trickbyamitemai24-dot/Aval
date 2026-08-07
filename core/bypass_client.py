"""Bypass HTTP Client Module — core/bypass_client.py

Async HTTP client built on top of curl_cffi.requests.AsyncSession to bypass
Cloudflare, DataDome, and TLS fingerprinting protections.
"""

import logging
from typing import Optional, Dict, Any
from curl_cffi.requests import AsyncSession, Response

logger = logging.getLogger(__name__)

DEFAULT_IMPERSONATE = "chrome131"


class BypassSession:
    """Async session wrapper using curl_cffi for browser impersonation."""

    def __init__(
        self,
        impersonate: str = DEFAULT_IMPERSONATE,
        proxy: Optional[str] = None,
        timeout: int = 20,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.impersonate = impersonate
        self.proxy = proxy
        self.timeout = timeout
        self.headers = headers or {}
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self):
        self.session = AsyncSession(
            impersonate=self.impersonate,
            headers=self.headers,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
        **kwargs,
    ) -> Response:
        """Perform GET request with impersonation."""
        req_proxy = proxy or self.proxy
        proxies = {"http": req_proxy, "https": req_proxy} if req_proxy else None
        
        if not self.session:
            async with AsyncSession(impersonate=self.impersonate) as sess:
                return await sess.get(url, params=params, headers=headers, proxies=proxies, **kwargs)
        
        return await self.session.get(url, params=params, headers=headers, proxies=proxies, **kwargs)

    async def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
        **kwargs,
    ) -> Response:
        """Perform POST request with impersonation."""
        req_proxy = proxy or self.proxy
        proxies = {"http": req_proxy, "https": req_proxy} if req_proxy else None

        if not self.session:
            async with AsyncSession(impersonate=self.impersonate) as sess:
                return await sess.post(url, data=data, json=json, headers=headers, proxies=proxies, **kwargs)

        return await self.session.post(url, data=data, json=json, headers=headers, proxies=proxies, **kwargs)


async def fetch_page_bypass(
    url: str,
    impersonate: str = DEFAULT_IMPERSONATE,
    proxy: Optional[str] = None,
    timeout: int = 15,
) -> Optional[str]:
    """Helper function to quickly fetch page HTML with browser impersonation."""
    try:
        async with BypassSession(impersonate=impersonate, proxy=proxy, timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
            logger.warning("Bypass fetch returned HTTP %d for %s", resp.status_code, url)
            return resp.text
    except Exception as e:
        logger.error("Bypass fetch failed for %s: %s", url, e)
        return None
