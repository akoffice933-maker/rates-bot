"""Binance P2P сервис: загрузка объявлений через пул прокси, кэш, фильтры."""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .proxy_pool import ProxyPool
from .sources.binance_p2p import URL, USER_AGENTS, P2PAd, build_payload, parse_ads

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class P2PResult:
    ok: bool
    error: str | None                      # 'blocked' | 'unavailable' | None
    sell_ads: tuple[P2PAd, ...] = ()       # продавцы USDT → пользователь покупает (по возрастанию цены)
    buy_ads: tuple[P2PAd, ...] = ()        # покупатели USDT → пользователь продаёт (по убыванию цены)
    fetched_at: datetime | None = None


def _classify(exc: Exception) -> str:
    return "blocked" if "403" in str(exc) else "unavailable"


class BinanceP2PService:
    def __init__(
        self,
        client,
        proxies: list[str] | None = None,
        min_completion_rate: float = 0.90,
        pages: int = 2,
        rows: int = 10,
        cache_ttl_seconds: int = 60,
        top_n: int = 5,
    ) -> None:
        self._client = client
        self._proxies = proxies
        self._min_completion = min_completion_rate
        self._pages = pages
        self._rows = rows
        self._top_n = top_n
        self._ttl = timedelta(seconds=cache_ttl_seconds)
        self._cached: P2PResult | None = None
        self._lock = asyncio.Lock()

    async def get(self, force: bool = False) -> P2PResult:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if (
                not force
                and self._cached is not None
                and self._cached.fetched_at is not None
                and (now - self._cached.fetched_at) < self._ttl
            ):
                return self._cached
            fresh = await self._fetch()
            self._cached = fresh
            return fresh

    def _pass(self, ad: P2PAd) -> bool:
        if ad.completion_rate is not None and ad.completion_rate < self._min_completion:
            return False
        return True

    async def _fetch(self) -> P2PResult:
        pool = ProxyPool(self._proxies)
        sell_ads: list[P2PAd] = []
        buy_ads: list[P2PAd] = []

        for trade_type, sink in (("SELL", sell_ads), ("BUY", buy_ads)):
            for page in range(1, self._pages + 1):
                payload = build_payload(trade_type, page, self._rows)
                last_exc: Exception | None = None
                for _attempt in range(2):  # 2 попытки с ротацией прокси
                    proxy = pool.next()
                    try:
                        resp = await self._client.post_json(
                            URL,
                            payload,
                            proxy=proxy,
                            headers={
                                "User-Agent": random.choice(USER_AGENTS),
                                "Accept": "application/json",
                            },
                        )
                        pool.report_success(proxy)
                        sink.extend(parse_ads(resp))
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        pool.report_failure(proxy)
                        log.warning("binance p2p ошибка: %s (proxy=%s)", exc, proxy or "direct")
                if last_exc is not None:
                    return P2PResult(ok=False, error=_classify(last_exc))

        sell = sorted((a for a in sell_ads if self._pass(a)), key=lambda a: a.price)
        buy = sorted((a for a in buy_ads if self._pass(a)), key=lambda a: a.price, reverse=True)
        return P2PResult(
            ok=True,
            error=None,
            sell_ads=tuple(sell[: self._top_n]),
            buy_ads=tuple(buy[: self._top_n]),
            fetched_at=datetime.now(timezone.utc),
        )
