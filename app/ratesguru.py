"""RatesGuru-сервис: кэш, фильтр бэйт-строк, топ-5.

Фильтр выбросов — как в методологии CriptoYa-части: строка отбрасывается,
если её курс отклоняется от медианы всех строк более чем на ±10%
(живой пример: 97,45 RUB/USDT при кластере ~85–90 — приманка).
После фильтра сортируем по лучшему курсу (min/max) и берём top_n.
Ошибки НЕ кэшируются (как у BestChange).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .sources.ratesguru import (
    BROWSER_HEADERS,
    DIRECTIONS,
    direction_url,
    parse_rows,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RGResult:
    ok: bool
    error: str | None
    direction_key: str
    rows: tuple = ()            # tuple[RGRow, ...]
    dropped: int = 0            # сколько строк отсечено медианным фильтром
    fetched_at: datetime | None = None


class RatesGuruService:
    def __init__(self, client, cache_ttl_seconds: int = 300, top_n: int = 5,
                 tolerance: float = 0.10) -> None:
        self._client = client
        self._ttl = timedelta(seconds=cache_ttl_seconds)
        self._top_n = top_n
        self._tolerance = tolerance
        self._cache: dict[str, tuple[RGResult, datetime]] = {}

    async def get(self, key: str, force: bool = False) -> RGResult:
        direction = DIRECTIONS.get(key)
        if direction is None:
            return RGResult(ok=False, error="unknown_direction", direction_key=key)
        now = datetime.now(timezone.utc)
        cached = self._cache.get(key)
        if cached is not None and not force and (now - cached[1]) < self._ttl:
            return cached[0]
        try:
            page = await self._client.get_text(direction_url(direction), headers=BROWSER_HEADERS)
            rows = parse_rows(page, direction)
        except Exception as exc:
            log.warning("источник ratesguru недоступен: %s", exc)
            return RGResult(ok=False, error="unavailable", direction_key=key)
        if not rows:
            return RGResult(ok=False, error="empty", direction_key=key)
        kept, dropped = self._filter_and_sort(rows, direction)
        result = RGResult(
            ok=True, error=None, direction_key=key,
            rows=kept, dropped=dropped, fetched_at=now,
        )
        self._cache[key] = (result, now)
        return result

    def _filter_and_sort(self, rows, direction):
        median = statistics.median([r.rate for r in rows])
        kept = [r for r in rows if abs(r.rate - median) <= median * self._tolerance]
        dropped = len(rows) - len(kept)
        kept.sort(key=lambda r: r.rate, reverse=(direction.better == "max"))
        return tuple(kept[: self._top_n]), dropped
