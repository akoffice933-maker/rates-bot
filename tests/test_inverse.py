"""Тесты инверсии пар (USD/ARS ↔ ARS/USD, USDT/ARS ↔ ARS/USDT) и хранилища направления."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from app import formatting as fmt
from app import render
from app.service import RatesService
from app.storage import BotStorage

from .test_service import FakeClient, BLUELYTICS, DOLARAPI

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

# синтетика с точной математикой: blue 100/102, площадки 110/105, 112/103, выброс 500/50
BL = {"oficial": {"value_buy": 100, "value_sell": 102}, "blue": {"value_buy": 100, "value_sell": 102}}
CT = {
    "a": {"totalAsk": 110, "totalBid": 105, "time": 1789990000},
    "b": {"totalAsk": 112, "totalBid": 103, "time": 1789990000},
    "c": {"totalAsk": 500, "totalBid": 50, "time": 1789990000},  # выброс
}


async def _snap(**kwargs):
    service = RatesService(FakeClient(bluelytics=BL, criptoya=CT), **kwargs)
    return await service.get_snapshot()


# ---------- форматирование ----------

def test_per_thousand():
    assert fmt.per_thousand(1593.67, "es") == "0,6275"   # 1000/1593.67
    assert fmt.per_thousand(1550, "ru") == "0,6452"
    assert fmt.per_thousand(None, "es") == "—"
    assert fmt.per_thousand(0, "es") == "—"


# ---------- /rates inverse ----------

async def test_rates_inverse_math():
    snap = await _snap(cache_ttl_seconds=60, force_min_interval_seconds=0)
    text = render.rates_text(snap, "es", now=NOW, inverse=True)
    assert text is not None
    assert "ARS/USD" in text
    # → покупка USD по venta 102: 1000/102 = 9,8039 USD за 1.000 ARS
    assert "→ 9,8039" in text
    # ← продажа USD по compra 100: 1000/100 = 10,0000 USD
    assert "← 10,0000" in text
    # в прямом режиме те же котировки выглядят иначе
    direct = render.rates_text(snap, "es", now=NOW)
    assert "100,00 / 102,00" in direct
    assert "USD/ARS" in direct


def test_rates_inverse_handles_missing_side():
    from app.sources.bluelytics import RatePair
    from app.service import Snapshot

    snap = Snapshot(
        fetched_at=NOW,
        blue=RatePair(buy=100, sell=None),  # нет venta
        oficial=RatePair(buy=None, sell=None),  # полностью пустая — не выводится
    )
    text = render.rates_text(snap, "ru", now=NOW, inverse=True)
    assert text is not None
    assert "→ —" in text          # compra есть, venta нет
    assert "← 10,0000" in text
    assert "Oficial" not in text  # пустая строка скрыта


# ---------- /usdt inverse ----------

async def test_usdt_inverse_math_and_order():
    snap = await _snap(cache_ttl_seconds=60, force_min_interval_seconds=0)
    text = render.usdt_text(snap, "es", now=NOW, inverse=True)
    assert text is not None
    assert "ARS/USDT" in text

    # покупка: лучший ask = 110 (площадка a) → больше USDT за 1.000 ARS: 1000/110
    assert "🥇 A — 9,0909 USDT" in text
    # продажа: лучший bid = 105 (площадка a) → меньше USDT за 1.000 ARS: 1000/105
    assert "🥇 A — 9,5238 USDT" in text

    # порядок в секции продажи инвертированного списка: 9,5238 (a) раньше 9,7087 (b)
    assert text.index("9,5238") < text.index("9,7087")  # b: 1000/103 = 9,7087

    # выброс c отфильтрован и здесь
    assert "C —" not in text

    # прямой режим для сравнения
    direct = render.usdt_text(snap, "es", now=NOW)
    assert "🥇 A — $110,00" in direct


# ---------- хранилище направления ----------

def test_storage_direction(tmp_path):
    st = BotStorage(str(tmp_path / "t.db"))
    assert st.get_direction(1) == "direct"  # default
    st.set_direction(1, "inverse", "es")
    assert st.get_direction(1) == "inverse"
    st.set_direction(1, "direct", "es")
    assert st.get_direction(1) == "direct"
    # язык не сломан
    st.set_lang(1, "ru")
    st.set_direction(1, "inverse", "ru")
    assert st.get_lang(1) == "ru"
    assert st.get_direction(1) == "inverse"
    # неуместное значение
    with pytest.raises(ValueError):
        st.set_direction(1, " diagonal ", "es")


def test_storage_direction_migration(tmp_path):
    """БД, созданная до появления direction, мигрирует автоматически."""
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE chat_settings (
               chat_id INTEGER PRIMARY KEY,
               lang TEXT NOT NULL,
               updated_at TEXT NOT NULL DEFAULT (datetime('now'))
           )"""
    )
    conn.execute("INSERT INTO chat_settings (chat_id, lang) VALUES (5, 'ru')")
    conn.commit()
    conn.close()

    st = BotStorage(db)  # применяет миграцию
    assert st.get_direction(5) == "direct"
    st.set_direction(5, "inverse", "ru")
    assert st.get_direction(5) == "inverse"
    assert st.get_lang(5) == "ru"  # старые данные не тронуты
