"""Тесты ссылок на площадки."""
from __future__ import annotations

from datetime import datetime, timezone

from app import render
from app.keyboards import links_kb, screen_kb
from app.render import links_text
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote
from app.venue_links import SOURCE_URLS, VENUE_URLS, ext_link, venue_link

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_snap() -> Snapshot:
    quotes = [
        VenueQuote("binancep2p", "Binance P2P", 110.0, 105.0, NOW),
        VenueQuote("bybitp2p", "Bybit P2P", 112.0, 103.0, NOW),
        VenueQuote("unknownvenue", "Unknownvenue", 111.0, 104.0, NOW),
    ]
    usdt = UsdtMarket(
        all_venues=tuple(quotes),
        asks=(quotes[0], quotes[2], quotes[1]),
        bids=(quotes[0], quotes[1], quotes[2]),
        median_ask=111.0,
        median_bid=104.0,
    )
    return Snapshot(fetched_at=NOW, blue=RatePair(buy=100.0, sell=102.0), usdt=usdt)


def test_registry_sanity():
    assert VENUE_URLS["binancep2p"].endswith("fiat=ARS")
    for key, url in VENUE_URLS.items():
        assert url.startswith("https://"), key
        assert " " not in url, key


def test_venue_link():
    link = venue_link("binancep2p", "Binance P2P")
    assert link == '<a href="https://p2p.binance.com/en/trade/USDT/ARS?fiat=ARS">Binance P2P</a>'
    # неизвестная площадка — просто имя, без битой разметки
    assert venue_link("unknownvenue", "Unknownvenue") == "Unknownvenue"


def test_usdt_screen_contains_links():
    snap = make_snap()
    text = render.usdt_text(snap, "es", now=NOW)
    assert '<a href="https://p2p.binance.com/' in text
    assert ">Binance P2P</a>" in text
    # у неизвестной площадки ссылки нет, но имя есть
    assert "Unknownvenue" in text and "unknownvenue</a>" not in text


def test_usdt_screen_links_in_inverse_mode():
    snap = make_snap()
    text = render.usdt_text(snap, "ru", now=NOW, inverse=True, volume=100)
    assert '<a href="https://www.bybit.com/">Bybit P2P</a>' in text
    assert "Объём расчёта: 100 USDT" in text


# ---------- источники на /rates и экран «Открыть всё» ----------

def test_source_urls_sanity():
    assert SOURCE_URLS["ambito"] == "https://www.ambito.com/contenidos/dolar.html"
    for key, url in SOURCE_URLS.items():
        assert url.startswith("https://"), key


def test_ext_link_escapes():
    assert ext_link("A&B", "https://x.y/?a=1&b=2") == '<a href="https://x.y/?a=1&amp;b=2">A&B</a>'


def test_rates_screen_source_links():
    snap = make_snap()
    text = render.rates_text(snap, "ru", now=NOW)
    assert '<a href="https://bluelytics.com.ar/">Bluelytics</a>' in text
    assert '<a href="https://dolarapi.com/">DolarAPI</a>' in text
    assert '<a href="https://www.ambito.com/contenidos/dolar.html">Ámbito</a>' in text
    assert "Источники" in text


def test_usdt_criptoya_credit_linked():
    text = render.usdt_text(make_snap(), "es", now=NOW)
    assert '<a href="https://criptoya.com/">Datos: CriptoYa</a>' in text


def test_links_kb_url_buttons():
    kb = links_kb("ru")
    flat = [b for row in kb.inline_keyboard for b in row]
    url_btns = {b.text: b.url for b in flat if b.url}
    assert url_btns["📊 Bluelytics"] == "https://bluelytics.com.ar/"
    assert url_btns["⚙️ DolarAPI"] == "https://dolarapi.com/"
    assert url_btns["📰 Ámbito"] == "https://www.ambito.com/contenidos/dolar.html"
    assert url_btns["🏦 Banco Nación"] == "https://www.bna.com.ar/"
    assert url_btns["💰 CriptoYa"] == "https://criptoya.com/"
    # назад — callback-кнопка, не URL
    back = [b for b in flat if not b.url]
    assert back and back[0].callback_data == "menu:main"


def test_screen_kb_has_open_all():
    for action in ("rates", "usdt", "spread"):
        kb = screen_kb("es", action)
        cbs = {b.callback_data for row in kb.inline_keyboard for b in row}
        assert "scr:links" in cbs, action


def test_links_text():
    assert "Ссылки и источники" in links_text("ru")
    assert "Enlaces y fuentes" in links_text("es")
    assert "Где купить / продать USD" in links_text("ru")
    assert "Dónde comprar / vender USD" in links_text("es")
    assert "MEP" in links_text("ru")


def test_usd_urls_registry_sanity():
    from app.venue_links import USD_URLS

    for key, url in USD_URLS.items():
        assert url.startswith("https://"), key
    assert USD_URLS["iol"] == "https://iol.com.ar/"
    assert len(USD_URLS) >= 6


def test_links_kb_usd_buttons():
    kb = links_kb("es")
    flat = [b for row in kb.inline_keyboard for b in row]
    url_btns = {b.text: b.url for b in flat if b.url}
    assert url_btns["📈 InvertirOnline"] == "https://iol.com.ar/"
    assert url_btns["📈 Balanz"] == "https://www.balanz.com/"
    assert url_btns["📈 Bull Market"] == "https://bullmarketbrokers.com/"
    assert url_btns["💳 Personal Pay"] == "https://www.personalpay.com.ar/"
    assert url_btns["🪙 Cocos"] == "https://www.cocos.capital/"
    assert url_btns["💳 Ualá"] == "https://uala.com.ar/"
    # источники никуда не делись
    assert url_btns["💰 CriptoYa"] == "https://criptoya.com/"
