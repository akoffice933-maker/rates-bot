"""DolarAPI: oficial, blue, MEP (bolsa), CCL, tarjeta, mayorista, cripto (USD/ARS)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .bluelytics import RatePair

URL = "https://dolarapi.com/v1/dolares"

# casa в API -> наш внутренний ключ
ALIAS = {
    "oficial": "oficial",
    "blue": "blue",
    "bolsa": "mep",
    "contadoconliqui": "ccl",
    "tarjeta": "tarjeta",
    "mayorista": "mayorista",
    "cripto": "cripto",
}


@dataclass(frozen=True)
class DolarApiSnapshot:
    rates: dict[str, RatePair] = field(default_factory=dict)
    fetched_at: datetime | None = None


def parse(payload: list[dict], fetched_at: datetime) -> DolarApiSnapshot:
    rates: dict[str, RatePair] = {}
    for item in payload:
        key = ALIAS.get(item.get("casa"))
        if key:
            rates[key] = RatePair(buy=item.get("compra"), sell=item.get("venta"))
    return DolarApiSnapshot(rates=rates, fetched_at=fetched_at)
