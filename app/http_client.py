"""HTTP-клиент поверх aiohttp: GET/POST -> JSON, таймауты, UA, опциональный прокси."""
from __future__ import annotations

from typing import Any

import aiohttp

USER_AGENT = "rates-bot/1.0 (telegram bot, contact: owner)"


class AiohttpClient:
    """Тонкая обёртка: таймаут на каждый запрос, raise при не-200."""

    def __init__(self, session: aiohttp.ClientSession, timeout: int = 10) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def get_json(self, url: str) -> Any:
        async with self._session.get(
            url, timeout=self._timeout, headers={"User-Agent": USER_AGENT}
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def post_json(
        self,
        url: str,
        payload: dict,
        proxy: str | None = None,
        headers: dict | None = None,
    ) -> Any:
        hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
        async with self._session.post(
            url, json=payload, proxy=proxy, headers=hdrs, timeout=self._timeout
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)
