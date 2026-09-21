"""CriptoYa: агрегатор цен USDT/ARS по ~35 площадкам (биржи + P2P).

ask/totalAsk — цена покупки USDT (площадка продаёт вам USDT);
bid/totalBid — цена продажи USDT (площадка покупает у вас USDT).
total* — цена с учётом комиссий площадки: используем именно её (честнее для пользователя).

Условия использования CriptoYa: атрибуция (есть в каждом сообщении бота)
и кэширование не менее 60 секунд — обеспечивает RatesService.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

URL_TEMPLATE = "https://criptoya.com/api/USDT/ARS/{volume}"

VENUE_NAMES = {
    "binancep2p": "Binance P2P",
    "binance": "Binance",
    "okexp2p": "OKX P2P",
    "bybitp2p": "Bybit P2P",
    "bybit": "Bybit",
    "huobip2p": "HTX P2P",
    "bingxp2p": "BingX P2P",
    "bitgetp2p": "Bitget P2P",
    "kucoinp2p": "KuCoin P2P",
    "mexcp2p": "MEXC P2P",
    "eldoradop2p": "El Dorado P2P",
    "weexp2p": "Weex P2P",
    "lemoncash": "Lemon",
    "lemoncashp2p": "Lemon P2P",
    "belo": "Belo",
    "ripio": "Ripio",
    "ripioexchange": "Ripio Exchange",
    "buenbit": "Buenbit",
    "satoshitango": "SatoshiTango",
    "letsbit": "LetsBit",
    "fiwind": "Fiwind",
    "decrypto": "Decrypto",
    "tiendacrypto": "TiendaCrypto",
    "universalcoins": "UniversalCoins",
    "vitawallet": "Vita Wallet",
    "bitsoalpha": "Bitso α",
    "cryptomktpro": "CryptoMKT",
    "cocoscrypto": "Cocos Crypto",
    "eluter": "Eluter",
    "astropay": "AstroPay",
    "nexo": "Nexo",
    "mexc": "MEXC",
    "peanut": "Peanut",
    "saldo": "Saldo",
    "wallbit": "Wallbit",
}


@dataclass(frozen=True)
class VenueQuote:
    key: str
    name: str
    ask: float | None       # цена покупки USDT (с комиссией)
    bid: float | None       # цена продажи USDT (с комиссией)
    time: datetime | None   # UTC, время котировки площадки


def _num(value: object) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def parse(payload: dict, fetched_at: datetime) -> list[VenueQuote]:
    quotes: list[VenueQuote] = []
    for key, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        ask = _num(raw.get("totalAsk")) or _num(raw.get("ask"))
        bid = _num(raw.get("totalBid")) or _num(raw.get("bid"))
        ts = raw.get("time")
        try:
            time = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else None
        except (OverflowError, OSError, ValueError):
            time = None
        quotes.append(
            VenueQuote(
                key=key,
                name=VENUE_NAMES.get(key, key.capitalize()),
                ask=ask,
                bid=bid,
                time=time or fetched_at,
            )
        )
    return quotes
