"""Калькулятор обмена: парсер сумм, математика всех режимов, клавиатуры."""
from datetime import datetime, timezone

from app.calc import MODES, calc_text, parse_amount
from app.keyboards import calc_modes_kb, calc_result_kb, main_menu
from app.service import Snapshot, UsdtMarket
from app.sources.criptoya import VenueQuote

NOW = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)


def make_snap() -> Snapshot:
    ars = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=NOW),),
        bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=NOW),),
        median_ask=1594.31, median_bid=1593.00,
    )
    usd = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="xapo", name="Xapo", ask=1.0014, bid=None, time=NOW),),
        bids=(VenueQuote(key="ripio", name="Ripio", ask=None, bid=1.0386, time=NOW),),
        median_ask=1.04, median_bid=1.03,
    )
    return Snapshot(fetched_at=NOW, usdt=ars, usdt_usd=usd)


# ---------- парсер сумм ----------

def test_parse_amount():
    assert parse_amount("1000") == 1000
    assert parse_amount("1 000") == 1000
    assert parse_amount("1500,5") == 1500.5
    assert parse_amount("1500.5") == 1500.5
    assert parse_amount("1,500") == 1500                 # тысячи
    assert parse_amount("1.500,50") == 1500.5
    assert parse_amount("1,500.50") == 1500.5
    assert parse_amount("1.500.000") == 1_500_000
    assert parse_amount("0,5") == 0.5
    assert parse_amount("abc") is None
    assert parse_amount("-5") is None
    assert parse_amount("0") is None
    assert parse_amount("") is None


# ---------- режимы ----------

def test_calc_buy_ars():
    text = calc_text("buy_ars", 150_000, make_snap(), "ru")
    assert "Купить USDT за 150 000,00 ARS" in text
    assert "MEXC P2P по 1 593,25 → <b>94,15 USDT</b>" in text      # 150000/1593.25      # 150000/1593.25
    assert "По медиане (1 594,31)" in text
    assert "объёма ~100 USDT" in text


def test_calc_sell_ars():
    text = calc_text("sell_ars", 500, make_snap(), "ru")
    assert "Продать 500,00 USDT → ARS" in text
    assert "SatoshiTango по 1 595,41 → <b>$797 705,00 ARS</b>" in text
    assert "По медиане (1 593,00)" in text


def test_calc_buy_usd():
    text = calc_text("buy_usd", 1000, make_snap(), "ru")
    assert "Купить USDT за 1 000,00 USD" in text
    assert "Xapo по 1,0014 → <b>998,60 USDT</b>" in text            # 1000/1.0014


def test_calc_sell_usd():
    text = calc_text("sell_usd", 500, make_snap(), "ru")
    assert "Продать 500,00 USDT → USD" in text
    assert "Ripio по 1,0386 → <b>$519,30 USD</b>" in text           # 500*1.0386


def test_calc_arb():
    text = calc_text("arb", 1000, make_snap(), "ru")
    assert "Арбитражный цикл с 1 000,00 USDT" in text
    assert "1) продать: Ripio по 1,0386 → 1 038,60 USD" in text
    assert "2) купить обратно: Xapo по 1,0014 → 1 037,15 USDT" in text
    assert "Брутто: +37,15 USDT (+3,71 %)" in text
    assert "Минус комиссии" in text


def test_calc_arb_es():
    text = calc_text("arb", 1000, make_snap(), "es")
    assert "Ciclo de arbitraje con 1.000,00 USDT" in text
    assert "1) vender: Ripio a 1,0386 → 1.038,60 USD" in text


def test_calc_no_data():
    empty = Snapshot(fetched_at=NOW)
    for mode in MODES:
        assert calc_text(mode, 100, empty, "ru") is None
    # без usdt_usd доступны только ARS-режимы
    only_ars = Snapshot(fetched_at=NOW, usdt=make_snap().usdt)
    assert calc_text("buy_ars", 100, only_ars, "ru") is not None
    assert calc_text("arb", 100, only_ars, "ru") is None
    assert calc_text("unknown", 100, make_snap(), "ru") is None


# ---------- клавиатуры ----------

def test_calc_keyboards():
    btns = [b.callback_data for row in calc_modes_kb("ru").inline_keyboard for b in row]
    assert btns == [f"calc:mode:{m}" for m in MODES] + ["menu:main"]
    btns = [b.callback_data for row in calc_result_kb("ru", "arb").inline_keyboard for b in row]
    assert btns == ["calc:mode:arb", "menu:main"]
    menu = [b.callback_data for row in main_menu("ru").inline_keyboard for b in row]
    assert "calc:menu" in menu
