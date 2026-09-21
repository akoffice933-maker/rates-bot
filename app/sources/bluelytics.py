"""Bluelytics: курсы oficial и blue (USD/ARS).

Семантика (единая для всех источников бота):
    buy  = compra — курс, по которому источник ПОКУПАЕТ у вас доллары (вы продаёте);
    sell = venta  — курс, по которому источник ПРОДАЁТ доллары (вы покупаете).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

URL = "https://api.bluelytics.com.ar/v2/latest"


@dataclass(frozen=True)
class RatePair:
    buy: float | None   # compra
    sell: float | None  # venta


@dataclass(frozen=True)
class BluelyticsSnapshot:
    oficial: RatePair
    blue: RatePair
    fetched_at: datetime


def _pair(raw: dict) -> RatePair:
    return RatePair(buy=raw.get("value_buy"), sell=raw.get("value_sell"))


def parse(payload: dict, fetched_at: datetime) -> BluelyticsSnapshot:
    return BluelyticsSnapshot(
        oficial=_pair(payload["oficial"]),
        blue=_pair(payload["blue"]),
        fetched_at=fetched_at,
    )
