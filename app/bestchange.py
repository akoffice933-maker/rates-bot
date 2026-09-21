"""BestChange-сервис: загрузка страницы направления, кэш, топ обменников."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .sources.bestchange import (
    BROWSER_HEADERS,
    DIRECTIONS,
    ExchangerRow,
    direction_url,
    parse_rows,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BestChangeResult:
    ok: bool
    error: str | None
    direction_key: str
    rows: tuple[ExchangerRow, ...] = ()
    fetched_at: datetime | None = None


class BestChangeService:
    def __init__(self, client, cache_ttl_seconds: int = 300, top_n: int = 5) -> None:
        self._client = client
        self._ttl = timedelta(seconds=cache_ttl_seconds)
        self._top_n = top_n
        self._cache: dict[str, tuple[BestChangeResult, datetime]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, force: bool = False) -> BestChangeResult:
        direction = DIRECTIONS.get(key)
        if direction is None:
            raise ValueError(f"unknown direction: {key}")
        async with self._lock:
            now = datetime.now(timezone.utc)
            cached = self._cache.get(key)
            if cached is not None and not force and (now - cached[1]) < self._ttl:
                return cached[0]

            try:
                html = await self._client.get_text(direction_url(direction), headers=BROWSER_HEADERS)
                rows = parse_rows(html)
            except Exception as exc:
                log.warning("bestchange %s недоступен: %s", key, exc)
                # ошибки не кэшируем: следующее нажатие попробует снова
                return BestChangeResult(
                    ok=False, error="unavailable", direction_key=key, fetched_at=now
                )

            result = BestChangeResult(
                ok=True,
                error=None,
                direction_key=key,
                rows=tuple(rows[: self._top_n]),  # порядок BestChange: лучшие сверху
                fetched_at=now,
            )
            self._cache[key] = (result, now)
            return result
