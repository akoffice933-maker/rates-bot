"""Пул прокси: round-robin, отметка сбойных, авто-сброс.

Поддерживаются http/https-прокси (передаются в aiohttp per-request).
Пустой список — работаем напрямую (proxy=None).
"""
from __future__ import annotations

MAX_FAILS = 3


class ProxyPool:
    def __init__(self, proxies: list[str] | None) -> None:
        self._urls: list[str | None] = list(proxies) if proxies else [None]
        self._fails: dict[str | None, int] = {u: 0 for u in self._urls}
        self._idx = 0

    def next(self) -> str | None:
        """Следующий живой прокси (None = без прокси). Если все сбойные — сброс счетчиков."""
        for _ in range(len(self._urls)):
            url = self._urls[self._idx % len(self._urls)]
            self._idx += 1
            if self._fails.get(url, 0) < MAX_FAILS:
                return url
        for u in self._urls:  # всем второй шанс
            self._fails[u] = 0
        url = self._urls[self._idx % len(self._urls)]
        self._idx += 1
        return url

    def report_failure(self, url: str | None) -> None:
        if url is not None:
            self._fails[url] = self._fails.get(url, 0) + 1

    def report_success(self, url: str | None) -> None:
        if url is not None:
            self._fails[url] = 0
