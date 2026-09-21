"""RatesService: сборка снапшота рынка из источников.

Поддержка объёмов: цены CriptoYa зависят от объёма операции (комиссии,
ликвидность), поэтому criptoya-часть кэшируется ОТДЕЛЬНО на каждый объём,
а USD-часть (Bluelytics + DolarAPI) — одна на все.

Методология (из ревью ТЗ, раздел «Методология и расчёты»):
  * выбросы: площадка отбрасывается в каждой из сторон (ask/bid), если её цена
    отклоняется от медианы всех площадок более чем на ±10% (живой пример:
    HTX P2P отдаёт 1930/1122 при рынке ~1596);
  * спред vs Blue считаем по МЕДИАНЕ площадок, а не по лучшей цене
    (лучшая цена часто bait / недостижима на практике);
  * лучший ask = min (куда дешевле купить USDT), лучший bid = max
    (куда выгоднее продать USDT).

Отказоустойчивость:
  * источники опрашиваются параллельно, падение одного не роняет снапшот;
  * при отказе — отдаётся последний успешный (stale) результат этой части;
  * кэш по умолчанию 60 секунд (условия CriptoYa).
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .sources import bluelytics, criptoya, dolarapi
from .sources.bluelytics import RatePair
from .sources.criptoya import VenueQuote

log = logging.getLogger(__name__)

OUTLIER_TOLERANCE = 0.10            # ±10% от медианы
BLUE_CROSSCHECK_TOLERANCE = 0.02    # расхождение blue между источниками >2% -> warning


class ApiClient(Protocol):
    async def get_json(self, url: str) -> Any: ...


@dataclass(frozen=True)
class UsdData:
    """USD-часть снапшота (не зависит от объёма)."""

    blue: RatePair | None = None
    oficial: RatePair | None = None
    mep: RatePair | None = None
    ccl: RatePair | None = None
    tarjeta: RatePair | None = None
    errors: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any((self.blue, self.oficial, self.mep, self.ccl, self.tarjeta))


@dataclass(frozen=True)
class UsdtMarket:
    all_venues: tuple[VenueQuote, ...]   # все площадки как есть (для отладки/статуса)
    asks: tuple[VenueQuote, ...]         # после фильтра выбросов, по возрастанию ask (лучшая первая)
    bids: tuple[VenueQuote, ...]         # после фильтра выбросов, по убыванию bid (лучшая первая)
    median_ask: float | None
    median_bid: float | None


@dataclass(frozen=True)
class Snapshot:
    fetched_at: datetime
    blue: RatePair | None = None
    oficial: RatePair | None = None
    mep: RatePair | None = None
    ccl: RatePair | None = None
    tarjeta: RatePair | None = None
    usdt: UsdtMarket | None = None
    source_errors: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        has_usdt = self.usdt and (self.usdt.asks or self.usdt.bids)
        return not (self.blue or self.oficial or self.mep or self.ccl or self.tarjeta or has_usdt)

    def spread_sell_pct(self) -> float | None:
        """На сколько % больше песо даёт продажа USDT (медиана bid)
        по сравнению с продажей наличного USD по blue compra."""
        if self.usdt and self.usdt.median_bid and self.blue and self.blue.buy:
            return (self.usdt.median_bid - self.blue.buy) / self.blue.buy * 100
        return None

    def spread_buy_pct(self) -> float | None:
        """На сколько % дороже купить USDT (медиана ask),
        чем наличный USD по blue venta."""
        if self.usdt and self.usdt.median_ask and self.blue and self.blue.sell:
            return (self.usdt.median_ask - self.blue.sell) / self.blue.sell * 100
        return None


@dataclass(frozen=True)
class UsdtUsdView:
    """Экран /usdtusd: пара USDT/USD (CriptoYa) + снапшот для наличного кросса.

    Безнал — прямые котировки USDT/USD аргентинских площадок (Xapo, Fiwind, …);
    наличные — расчётный кросс USD-нал ⇄ ARS (blue) ⇄ USDT (лучшая площадка).
    """

    snap: Snapshot
    usd: UsdtMarket | None = None


def _filter_outliers(quotes: list[VenueQuote], attr: str, tolerance: float = OUTLIER_TOLERANCE) -> list[VenueQuote]:
    values = [getattr(q, attr) for q in quotes]
    median = statistics.median(values)
    return [q for q in quotes if abs(getattr(q, attr) - median) <= median * tolerance]


def build_market(quotes: list[VenueQuote]) -> UsdtMarket:
    asks = [q for q in quotes if q.ask is not None]
    bids = [q for q in quotes if q.bid is not None]
    kept_asks = sorted(_filter_outliers(asks, "ask"), key=lambda q: q.ask)
    kept_bids = sorted(_filter_outliers(bids, "bid"), key=lambda q: q.bid, reverse=True)
    return UsdtMarket(
        all_venues=tuple(quotes),
        asks=tuple(kept_asks),
        bids=tuple(kept_bids),
        median_ask=statistics.median([q.ask for q in kept_asks]) if kept_asks else None,
        median_bid=statistics.median([q.bid for q in kept_bids]) if kept_bids else None,
    )


class RatesService:
    def __init__(
        self,
        client: ApiClient,
        cache_ttl_seconds: int = 60,
        default_volume: int = 100,
        force_min_interval_seconds: int = 10,
    ) -> None:
        self._client = client
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._force_min_interval = timedelta(seconds=force_min_interval_seconds)
        self._default_volume = default_volume
        self._usd: tuple[UsdData, datetime] | None = None
        self._criptoya: dict[int, tuple[list[VenueQuote], datetime]] = {}
        self._criptoya_usd: tuple[list[VenueQuote], datetime] | None = None
        self._lock = asyncio.Lock()

    async def get_snapshot(self, volume: int | None = None, force: bool = False) -> Snapshot:
        """Снапшот для объёма volume (USDT, по умолчанию — default_volume).

        force=True обходит кэш (кнопка «Обновить»), но не чаще
        force_min_interval (анти-спам). USD-часть кэшируется общая,
        criptoya-часть — отдельно на каждый объём.
        """
        vol = volume or self._default_volume
        async with self._lock:
            now = datetime.now(timezone.utc)
            usd, usd_ts = await self._get_usd(force, now)
            quotes, ct_ts = await self._get_criptoya(vol, force, now)
            errors = usd.errors + (("criptoya",) if quotes is None else ())
            return Snapshot(
                fetched_at=max(usd_ts, ct_ts),
                blue=usd.blue,
                oficial=usd.oficial,
                mep=usd.mep,
                ccl=usd.ccl,
                tarjeta=usd.tarjeta,
                usdt=build_market(quotes) if quotes else None,
                source_errors=tuple(errors),
            )

    def _cache_ok(self, ts: datetime, now: datetime, force: bool) -> bool:
        age = now - ts
        if force:
            return age < self._force_min_interval
        return age < self._cache_ttl

    async def _get_usd(self, force: bool, now: datetime) -> tuple[UsdData, datetime]:
        cached = self._usd
        if cached is not None and self._cache_ok(cached[1], now, force):
            return cached
        fresh = await self._fetch_usd(now)
        if fresh.is_empty and cached is not None:
            log.warning("источники USD упали — использую предыдущие (stale) данные")
            return cached
        self._usd = (fresh, now)
        return self._usd

    async def _get_criptoya(
        self, vol: int, force: bool, now: datetime
    ) -> tuple[list[VenueQuote] | None, datetime]:
        cached = self._criptoya.get(vol)
        if cached is not None and self._cache_ok(cached[1], now, force):
            return cached
        try:
            payload = await self._client.get_json(criptoya.URL_TEMPLATE.format(volume=vol))
            quotes = criptoya.parse(payload, now)
        except Exception as exc:
            log.warning("источник criptoya недоступен: %s", exc)
            if cached is not None:
                return cached
            return None, now
        if not quotes and cached is not None:
            return cached
        self._criptoya[vol] = (quotes, now)
        return self._criptoya[vol]

    async def _fetch_usd(self, now: datetime) -> UsdData:
        bl, da = await asyncio.gather(
            self._fetch_bluelytics(),
            self._fetch_dolarapi(),
            return_exceptions=True,
        )

        errors: list[str] = []
        for name, result in zip(("bluelytics", "dolarapi"), (bl, da)):
            if isinstance(result, BaseException):
                log.warning("источник %s недоступен: %s", name, result)
                errors.append(name)

        blue: RatePair | None = None
        oficial: RatePair | None = None
        if not isinstance(bl, BaseException) and bl is not None:
            oficial = bl.oficial
            blue = bl.blue
        if not isinstance(da, BaseException) and da is not None:
            d = da.rates
            oficial = oficial or d.get("oficial")
            if blue is None:
                blue = d.get("blue")
            elif d.get("blue") and d["blue"].sell and blue.sell:
                # кросс-чек blue между двумя источниками
                if abs(d["blue"].sell - blue.sell) / blue.sell > BLUE_CROSSCHECK_TOLERANCE:
                    log.warning(
                        "расхождение blue: bluelytics=%s dolarapi=%s (приоритет у bluelytics)",
                        blue.sell, d["blue"].sell,
                    )

        has_da = not isinstance(da, BaseException) and da is not None
        return UsdData(
            blue=blue,
            oficial=oficial,
            mep=da.rates.get("mep") if has_da else None,
            ccl=da.rates.get("ccl") if has_da else None,
            tarjeta=da.rates.get("tarjeta") if has_da else None,
            errors=tuple(errors),
        )

    async def get_usdtusd_view(self, force: bool = False) -> UsdtUsdView:
        """Данные для экрана /usdtusd: снапшот (blue + USDT/ARS) + пара USDT/USD."""
        snap = await self.get_snapshot(force=force)
        quotes = await self._get_criptoya_usd(force)
        return UsdtUsdView(snap=snap, usd=build_market(quotes) if quotes else None)

    async def _get_criptoya_usd(self, force: bool) -> list[VenueQuote] | None:
        """CriptoYa USDT/USD: тот же кэш/TTL, при сбое — последний успешный."""
        now = datetime.now(timezone.utc)
        cached = self._criptoya_usd
        if cached is not None and self._cache_ok(cached[1], now, force):
            return cached[0]
        try:
            payload = await self._client.get_json(criptoya.URL_USDT_USD)
            quotes = criptoya.parse(payload, now)
        except Exception as exc:
            log.warning("источник criptoya usdt/usd недоступен: %s", exc)
            return cached[0] if cached else None
        if not quotes and cached is not None:
            return cached[0]
        self._criptoya_usd = (quotes, now)
        return quotes

    async def _fetch_bluelytics(self):
        payload = await self._client.get_json(bluelytics.URL)
        return bluelytics.parse(payload, datetime.now(timezone.utc))

    async def _fetch_dolarapi(self):
        payload = await self._client.get_json(dolarapi.URL)
        return dolarapi.parse(payload, datetime.now(timezone.utc))
