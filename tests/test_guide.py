"""Тесты мастера обмена: выбор лучшего курса по сценарию, шаги, предупреждения."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.guide import SCENARIOS, guide_menu_text, guide_text
from app.keyboards import guide_kb, scenario_kb, screen_kb
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_snap() -> Snapshot:
    """blue 100/102, MEP 99/101, oficial 98/103; площадки: asks 110/112, bids 105/103."""
    a = VenueQuote("a", "A", 110.0, 105.0, NOW)
    b = VenueQuote("b", "B", 112.0, 103.0, NOW)
    usdt = UsdtMarket(
        all_venues=(a, b),
        asks=tuple(sorted((a, b), key=lambda q: q.ask)),
        bids=tuple(sorted((a, b), key=lambda q: q.bid, reverse=True)),
        median_ask=111.0,
        median_bid=104.0,
    )
    return Snapshot(
        fetched_at=NOW,
        blue=RatePair(buy=100.0, sell=102.0),
        oficial=RatePair(buy=98.0, sell=103.0),
        mep=RatePair(buy=99.0, sell=101.0),
        usdt=usdt,
    )


def test_scenarios_registry():
    assert SCENARIOS == ("buy_usdt", "sell_usdt", "buy_usd", "sell_usd")
    with pytest.raises(ValueError):
        guide_text(make_snap(), "diagonal", "ru")


def test_buy_usdt_picks_cheapest_ask():
    text = guide_text(make_snap(), "buy_usdt", "es")
    assert text is not None
    assert "Comprar USDT" in text
    assert "A" in text and "110,00" in text          # лучший ask = 110 (площадка A)
    assert "9,0909" in text                          # 1000/110 USDT за 1.000 ARS
    assert "+8,82 %" in text                         # (111-102)/102 — переплата к blue (по медиане)
    assert "escrow" in text or "escrow".lower() in text.lower()
    assert "1️⃣" in text and "6️⃣" in text             # пошаговый блок
    assert "Lemon" in text                           # альтернативы


def test_sell_usdt_picks_best_bid():
    text = guide_text(make_snap(), "sell_usdt", "ru")
    assert text is not None
    assert "Продать USDT" in text
    assert "105,00" in text                          # лучший bid
    assert "105 000,00" in text                      # за 1.000 USDT
    assert "+4,00 %" in text                         # (104-100)/100 — выгода к blue (по медиане)
    assert "НА ВАШ счёт" in text   # ключевой шаг: проверка зачисления


def test_buy_usd_compares_and_recommends_mep():
    text = guide_text(make_snap(), "buy_usd", "ru")
    assert text is not None
    # все три курса покупки: MEP 101 (лучший), blue 102, oficial 103
    assert "101,00" in text and "102,00" in text and "103,00" in text
    assert "Выгоднее всего: MEP" in text
    assert "биржа, легально" in text
    assert "InvertirOnline" in text                  # шаги MEP
    assert "cueva" in text.lower()                   # альтернативы


def test_sell_usd_compares_and_recommends_blue():
    text = guide_text(make_snap(), "sell_usd", "es")
    assert text is not None
    # курсы продажи: blue compra 100 (лучший), MEP 99, oficial 98
    assert "Lo más conveniente: Blue" in text
    assert "efectivo" in text
    assert "cueva" in text.lower()


def test_guide_no_data():
    empty = Snapshot(fetched_at=NOW)
    for scenario in SCENARIOS:
        assert guide_text(empty, scenario, "ru") is None


def test_guide_menu_and_keyboards():
    assert "Как обменять" in guide_menu_text("ru")
    assert "Cómo cambiar" in guide_menu_text("es")
    cbs = {b.callback_data for row in guide_kb("ru").inline_keyboard for b in row}
    assert {f"gw:{s}" for s in SCENARIOS} <= cbs
    sc = {b.callback_data for row in scenario_kb("ru").inline_keyboard for b in row}
    assert "gw:menu" in sc and "menu:main" in sc


def test_screen_kb_links_to_guide():
    rates_cbs = {b.callback_data for row in screen_kb("ru", "rates").inline_keyboard for b in row}
    usdt_cbs = {b.callback_data for row in screen_kb("ru", "usdt", "direct", 100).inline_keyboard for b in row}
    assert "gw:buy_usd" in rates_cbs      # с экрана доллара — к покупке USD
    assert "gw:buy_usdt" in usdt_cbs      # с экрана USDT — к покупке USDT
