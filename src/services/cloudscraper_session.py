"""Async wrapper around cloudscraper for project HTTP requests."""
import asyncio
from typing import Any, Dict, Optional

import cloudscraper


class CloudScraperSession:
    """Minimal async-compatible session wrapper backed by cloudscraper."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    @staticmethod
    def _prepare_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        request_kwargs = dict(kwargs)

        proxy = request_kwargs.pop("proxy", None)
        if proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        # curl_cffi-only option, ignored by cloudscraper/requests
        request_kwargs.pop("impersonate", None)

        # Match requests naming if older callers still pass allow_redirects.
        if "allow_redirects" in request_kwargs:
            request_kwargs["allow_redirects"] = request_kwargs["allow_redirects"]

        return request_kwargs

    @staticmethod
    def _request_sync(method: str, url: str, **kwargs):
        scraper = cloudscraper.create_scraper()
        return scraper.request(method=method, url=url, **CloudScraperSession._prepare_kwargs(kwargs))

    async def request(self, method: str, url: str, **kwargs):
        return await asyncio.to_thread(self._request_sync, method, url, **kwargs)

    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)
