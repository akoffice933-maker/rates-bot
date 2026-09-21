"""Binance P2P: прямые объявления USDT/ARS через bapi.

Семантика сторон (риск инверсии из ревью ТЗ — ключевой момент):
  tradeType=SELL — объявления ПРОДАВЦОВ USDT → пользователь ПОКУПАЕТ USDT
                   (лучшая цена = минимальная);
  tradeType=BUY  — объявления ПОКУПАТЕЛЕЙ USDT → пользователь ПРОДАЁТ USDT
                   (лучшая цена = максимальная).

bapi блокирует дата-центровые IP (403 из песочницы, проверено 21.09.2026),
поэтому запросы идут через пул резидентных AR-прокси (PROXY_LIST) с ротацией UA.
"""
from __future__ import annotations

from dataclasses import dataclass

URL = "https://p2p.binance.com/bapi/ads/v1/public/ads/search"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


@dataclass(frozen=True)
class P2PAd:
    price: float                    # ARS за 1 USDT
    min_amount: float | None        # ARS
    max_amount: float | None        # ARS
    available: float | None         # USDT
    methods: tuple[str, ...]        # способы оплаты
    advertiser: str
    completion_rate: float | None   # 0..1


def build_payload(
    trade_type: str, page: int = 1, rows: int = 10, asset: str = "USDT", fiat: str = "ARS"
) -> dict:
    return {
        "page": page,
        "rows": rows,
        "asset": asset,
        "fiat": fiat,
        "tradeType": trade_type,
        "payTypes": [],
        "publisherType": None,
    }


def _f(value) -> float | None:
    try:
        f = float(value)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def parse_ads(payload: dict) -> list[P2PAd]:
    """Разбор ответа bapi; битые записи пропускаются."""
    ads: list[P2PAd] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        adv = item.get("adv") or {}
        advr = item.get("advertiser") or {}
        price = _f(adv.get("price"))
        if price is None:
            continue
        methods = tuple(
            m.get("name") for m in (adv.get("tradeMethods") or []) if m.get("name")
        )
        completion = _f(advr.get("monthFinishRate"))
        if completion is not None and completion > 1:
            completion = completion / 100.0  # иногда приходит в процентах
        ads.append(
            P2PAd(
                price=price,
                min_amount=_f(adv.get("minSingleTransAmount")),
                max_amount=_f(adv.get("maxSingleTransAmount")),
                available=_f(adv.get("surplusAmount")),
                methods=methods,
                advertiser=(advr.get("nickName") or "")[:24],
                completion_rate=completion,
            )
        )
    return ads
