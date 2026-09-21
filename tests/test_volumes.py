"""Тесты фичи объёмов: экран /usdt с объёмом, клавиатура, рендер."""
from __future__ import annotations

from datetime import datetime, timezone

from app import render
from app.keyboards import VOL_PRESETS, screen_kb
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def make_snap() -> Snapshot:
    quotes = [
        VenueQuote("a", "A", 110.0, 105.0, NOW),
        VenueQuote("b", "B", 112.0, 103.0, NOW),
    ]
    usdt = UsdtMarket(
        all_venues=tuple(quotes),
        asks=tuple(sorted(quotes, key=lambda q: q.ask)),
        bids=tuple(sorted(quotes, key=lambda q: q.bid, reverse=True)),
        median_ask=111.0,
        median_bid=104.0,
    )
    return Snapshot(fetched_at=NOW, blue=RatePair(buy=100.0, sell=102.0), usdt=usdt)


def test_usdt_screen_shows_volume():
    snap = make_snap()
    text_es = render.usdt_text(snap, "es", now=NOW, volume=1000)
    assert "Volumen de cálculo: 1.000 USDT" in text_es
    text_ru = render.usdt_text(snap, "ru", now=NOW, volume=5000)
    assert "Объём расчёта: 5 000 USDT" in text_ru
    # без объёма — строки нет
    text_plain = render.usdt_text(snap, "es", now=NOW)
    assert "Volumen" not in text_plain


def test_usdt_screen_volume_inverse_mode():
    snap = make_snap()
    text = render.usdt_text(snap, "ru", now=NOW, inverse=True, volume=500)
    assert "Объём расчёта: 500 USDT" in text


def test_screen_kb_volume_buttons():
    kb = screen_kb("ru", "usdt", "direct", volume=100)
    flat = [(b.text, b.callback_data) for row in kb.inline_keyboard for b in row]
    texts = [t for t, _ in flat]
    assert f"✅ 100" in texts and "💵 5000" in texts
    assert ("vol:1000",) in [(cd,) for _, cd in flat]
    # на экране курсов кнопок объёма нет
    kb_rates = screen_kb("ru", "rates", "direct")
    assert not any(cd.startswith("vol:") for _, cd in
                   [(b.text, b.callback_data) for row in kb_rates.inline_keyboard for b in row])


def test_screen_kb_all_volume_presets_present():
    kb = screen_kb("es", "usdt", "direct", volume=1000)
    callbacks = {b.callback_data for row in kb.inline_keyboard for b in row}
    assert {f"vol:{v}" for v in VOL_PRESETS} <= callbacks
