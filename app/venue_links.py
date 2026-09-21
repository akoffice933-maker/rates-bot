"""Ссылки на торговые интерфейсы площадок.

Все URL проверены живыми запросами 21.09.2026 (HTTP 200/202/403-bot-check).
Binance и MEXC отдают 202/403 на автоматические запросы (анти-бот), но
открываются в браузере; Bybit P2P гео-блокируется — ведём на главную.
decrypto, letsbit, universalcoins — домены не ответили, ссылки не ставим
(лучше без ссылки, чем мёртвая).
"""
from __future__ import annotations

import html

SOURCE_URLS: dict[str, str] = {
    "bluelytics": "https://bluelytics.com.ar/",
    "dolarapi": "https://dolarapi.com/",
    "ambito": "https://www.ambito.com/contenidos/dolar.html",
    "bna": "https://www.bna.com.ar/",
    "criptoya": "https://criptoya.com/",
    "bestchange": "https://www.bestchange.com/",
}

# Где купить/продать USD (проверено живыми запросами 21.09.2026):
# банк — курс oficial; брокеры и приложения — курс MEP (легально, выгоднее банка);
# blue — неформальный наличный рынок (cuevas), стабильных сайтов нет.
USD_URLS: dict[str, str] = {
    "bna": "https://www.bna.com.ar/",
    "iol": "https://iol.com.ar/",
    "balanz": "https://www.balanz.com/",
    "bullmarket": "https://bullmarketbrokers.com/",
    "personalpay": "https://www.personalpay.com.ar/",
    "uala": "https://uala.com.ar/",
    "cocos": "https://www.cocos.capital/",
}


VENUE_URLS: dict[str, str] = {
    # P2P-площадки
    "binancep2p": "https://p2p.binance.com/en/trade/USDT/ARS?fiat=ARS",
    "okexp2p": "https://www.okx.com/p2p-markets",
    "bybitp2p": "https://www.bybit.com/",
    "huobip2p": "https://www.htx.com/",
    "bitgetp2p": "https://www.bitget.com/p2p-trade",
    "kucoinp2p": "https://www.kucoin.com/",
    "bingxp2p": "https://www.bingx.com/",
    "mexcp2p": "https://www.mexc.com/",
    "weexp2p": "https://www.weex.com/",
    "eldoradop2p": "https://eldorado.io/",
    "lemoncashp2p": "https://lemon.me/",
    # биржи/спот
    "binance": "https://www.binance.com/en/trade/USDT_ARS",
    "bybit": "https://www.bybit.com/en/trade/spot/USDT/ARS",
    "mexc": "https://www.mexc.com/",
    # аргентинские платформы
    "lemoncash": "https://lemon.me/",
    "belo": "https://belo.app/",
    "ripio": "https://www.ripio.com/ar/",
    "ripioexchange": "https://exchange.ripio.com/",
    "buenbit": "https://buenbit.com/",
    "satoshitango": "https://satoshitango.com/",
    "fiwind": "https://fiwind.io/",
    "tiendacrypto": "https://tiendacrypto.com/",
    "vitawallet": "https://vitawallet.io/",
    "bitsoalpha": "https://bitso.com/",
    "cryptomktpro": "https://cryptomkt.com/",
    "cocoscrypto": "https://cocoscrypto.com/",
    "eluter": "https://eluter.com/",
    "astropay": "https://astropay.com/",
    "nexo": "https://nexo.com/",
    "peanut": "https://peanut.to/",
    "saldo": "https://www.saldo.com.ar/",
    "wallbit": "https://wallbit.io/",
    # площадки пары USDT/USD (проверено 21.09.2026, 200 OK)
    "xapo": "https://xapo.com/",
    "banexcoin": "https://banexcoin.com/",
    "x4t": "https://www.x4t.com/",
}


def venue_link(key: str, name: str) -> str:
    """HTML-ссылка на площадку, если URL известен; иначе просто имя."""
    url = VENUE_URLS.get(key)
    if url:
        return ext_link(name, url)
    return name


def ext_link(text: str, url: str) -> str:
    """HTML-ссылка с произвольным текстом (URL экранируется)."""
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'
