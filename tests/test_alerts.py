"""Тесты алертов: метрики (спред + абсолютные), направления, гистерезис, cooldown, хранилище."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from app.alerts import AlertManager, METRICS, fired_text
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.storage import BotStorage

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def fresh_storage() -> BotStorage:
    td = tempfile.mkdtemp()
    return BotStorage(os.path.join(td, "alerts.db"))


def make_snap(median_bid: float = 104.0, median_ask: float = 111.0) -> Snapshot:
    """blue 100/102 фиксированы; спред продажи = (bid-100)/100, покупки = (ask-102)/102."""
    usdt = UsdtMarket(
        all_venues=(), asks=(), bids=(), median_ask=median_ask, median_bid=median_bid
    )
    return Snapshot(fetched_at=NOW, blue=RatePair(buy=100.0, sell=102.0), usdt=usdt)


def snap_with_sell_spread(pct: float) -> Snapshot:
    return make_snap(median_bid=100.0 * (1 + pct / 100))


# ---------- реестр метрик ----------

def test_metrics_registry_eval():
    snap = make_snap(median_bid=104.0, median_ask=111.0)
    assert METRICS["spread_sell"].eval(snap) == pytest.approx(4.0)
    assert METRICS["spread_buy"].eval(snap) == pytest.approx((111 - 102) / 102 * 100)
    assert METRICS["blue_buyusd"].eval(snap) == 102.0   # blue venta
    assert METRICS["blue_sellusd"].eval(snap) == 100.0  # blue compra
    assert METRICS["usdt_buy"].eval(snap) == 111.0      # медиана ask
    assert METRICS["usdt_sell"].eval(snap) == 104.0     # медиана bid
    # без данных — None
    empty = Snapshot(fetched_at=NOW)
    assert METRICS["blue_buyusd"].eval(empty) is None
    assert METRICS["usdt_buy"].eval(empty) is None


# ---------- спред-алерты (above) ----------

async def test_spread_alert_crossing():
    st = fresh_storage()
    st.add_alert(1, "spread_sell", "spread", 3.0, "above")
    manager = AlertManager(st, cooldown_minutes=30)

    assert await manager.check(snap_with_sell_spread(2.0)) == []
    fired = await manager.check(snap_with_sell_spread(4.0))
    assert len(fired) == 1
    assert "4,00 %" in fired[0] and "3,0 %" in fired[0]
    # всё ещё выше порога — тишина
    assert await manager.check(snap_with_sell_spread(4.5)) == []


async def test_spread_hysteresis_and_rearm():
    st = fresh_storage()
    st.add_alert(1, "spread_sell", "spread", 3.0, "above")
    manager = AlertManager(st, cooldown_minutes=0, hysteresis_pct=0.2)

    await manager.check(snap_with_sell_spread(4.0))
    await manager.check(snap_with_sell_spread(2.9))   # выше 2,8 — не перевзводится
    assert await manager.check(snap_with_sell_spread(4.0)) == []

    await manager.check(snap_with_sell_spread(2.7))   # глубокий провал — перевзвод
    fired = await manager.check(snap_with_sell_spread(4.0))
    assert len(fired) == 1


async def test_cooldown_blocks_and_retries():
    st = fresh_storage()
    st.add_alert(1, "spread_sell", "spread", 3.0, "above")
    hot = AlertManager(st, cooldown_minutes=30)

    assert len(await hot.check(snap_with_sell_spread(4.0))) == 1
    await hot.check(snap_with_sell_spread(2.0))                # перевзвод
    assert await hot.check(snap_with_sell_spread(4.0)) == []   # cooldown активен

    cold = AlertManager(st, cooldown_minutes=0)                # cooldown истёк
    fired = await cold.check(snap_with_sell_spread(4.2))
    assert len(fired) == 1 and "4,20 %" in fired[0]


# ---------- абсолютные алерты: above и below ----------

async def test_abs_alert_above():
    st = fresh_storage()
    # blue venta (покупка USD) дороже 105
    st.add_alert(1, "blue_buyusd", "abs", 105.0, "above")
    manager = AlertManager(st, cooldown_minutes=30)

    assert await manager.check(make_snap()) == []               # blue sell = 102 < 105

    snap_high = Snapshot(
        fetched_at=NOW, blue=RatePair(buy=103.0, sell=106.0), usdt=None
    )
    fired = await manager.check(snap_high)
    assert len(fired) == 1
    assert "106" in fired[0] and "105" in fired[0]


async def test_abs_alert_below_direction():
    st = fresh_storage()
    # медиана bid упадёт ниже 103 (сейчас 104)
    st.add_alert(1, "usdt_sell", "abs", 103.0, "below")
    manager = AlertManager(st, cooldown_minutes=30)

    assert await manager.check(make_snap(median_bid=104.0)) == []   # выше порога
    fired = await manager.check(make_snap(median_bid=102.0))        # упало ниже
    assert len(fired) == 1
    assert "102,00" in fired[0] and "⩽" in fired[0]
    # всё ещё ниже — тишина
    assert await manager.check(make_snap(median_bid=101.5)) == []


async def test_abs_hysteresis_rearm():
    st = fresh_storage()
    # порог 1550, гистерезис для abs = max(0.1% от порога, 0.5) = 1.55
    st.add_alert(1, "blue_buyusd", "abs", 1550.0, "above")
    manager = AlertManager(st, cooldown_minutes=0)

    high = lambda sell: Snapshot(  # noqa: E731
        fetched_at=NOW, blue=RatePair(buy=1500.0, sell=sell), usdt=None
    )
    assert len(await manager.check(high(1560.0))) == 1   # сработало
    await manager.check(high(1549.0))                   # выше 1548.45 — не перевзводится
    assert await manager.check(high(1560.0)) == []
    await manager.check(high(1540.0))                   # глубокий провал — перевзвод
    assert len(await manager.check(high(1560.0))) == 1  # снова сработало


# ---------- текст уведомлений ----------

def test_fired_text_abs():
    st = fresh_storage()
    st.add_alert(1, "usdt_buy", "abs", 1600.0, "above")
    alert = st.list_alerts()[0]

    snap = make_snap(median_ask=1610.0)
    text = fired_text(alert, 1610.0, snap, "ru")
    assert "USDT — покупка" in text
    assert "$1.610" in text or "1 610" in text
    assert "⩾" in text
    assert "/alert" in text


def test_fired_text_spread():
    st = fresh_storage()
    st.add_alert(1, "spread_sell", "spread", 3.5, "above")
    alert = st.list_alerts()[0]

    snap = snap_with_sell_spread(4.05)
    text = fired_text(alert, snap.spread_sell_pct(), snap, "ru")
    assert "+4,05 %" in text and "3,5 %" in text


# ---------- хранилище ----------

def test_storage_alerts_crud(tmp_path):
    st = BotStorage(str(tmp_path / "s.db"))
    assert st.list_alerts(1) == []

    assert st.add_alert(1, "spread_sell", "spread", 3.0, "above") is True
    assert st.add_alert(1, "spread_sell", "spread", 3.0, "above") is False   # дубликат
    assert st.add_alert(1, "spread_sell", "spread", 4.0, "above") is True    # другой порог
    assert st.add_alert(1, "usdt_buy", "abs", 1600.0, "above") is True
    assert st.add_alert(1, "usdt_buy", "abs", 1600.0, "below") is True       # другое направление — можно
    assert st.add_alert(2, "spread_sell", "spread", 3.0, "above") is True    # другой чат

    mine = st.list_alerts(1)
    assert len(mine) == 4
    assert all(a.chat_id == 1 for a in mine)

    # удаление: чужой чат не может удалить
    some_id = mine[0].id
    assert st.remove_alert(some_id, chat_id=999) is False
    assert st.remove_alert(some_id, chat_id=1) is True
    assert len(st.list_alerts(1)) == 3

    # mark_fired / set_active
    alert = st.list_alerts(1)[0]
    assert alert.active is False and alert.last_fired_at is None
    st.mark_fired(alert.id)
    alert = st.list_alerts(1)[0]
    assert alert.active is True and alert.last_fired_at is not None
    st.set_active(alert.id, False)
    assert st.list_alerts(1)[0].active is False


def test_storage_validation(tmp_path):
    st = BotStorage(str(tmp_path / "v.db"))
    with pytest.raises(ValueError):
        st.add_alert(1, "spread_sell", "spread", 3.0, "diagonal")
    with pytest.raises(ValueError):
        st.add_alert(1, "spread_sell", "quantum", 3.0, "above")


def test_storage_volume(tmp_path):
    st = BotStorage(str(tmp_path / "vol.db"))
    assert st.get_volume(1) == 100            # default
    assert st.get_volume(1, default=500) == 500
    st.set_volume(1, 1000, "es")
    assert st.get_volume(1) == 1000
    st.set_lang(1, "ru")                      # соседняя настройка не сломана
    st.set_volume(1, 5000, "ru")
    assert st.get_volume(1) == 5000
    assert st.get_lang(1) == "ru"
    with pytest.raises(ValueError):
        st.set_volume(1, 0)
    with pytest.raises(ValueError):
        st.set_volume(1, 2_000_000)


def test_migration_from_v12(tmp_path):
    """БД версии v1.2 (sell/buy + threshold_pct + was_above) мигрирует в v1.3."""
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE alerts (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               chat_id INTEGER NOT NULL,
               metric TEXT NOT NULL,
               threshold_pct REAL NOT NULL,
               enabled INTEGER NOT NULL DEFAULT 1,
               was_above INTEGER NOT NULL DEFAULT 0,
               created_at TEXT NOT NULL DEFAULT (datetime('now')),
               last_fired_at TEXT,
               UNIQUE (chat_id, metric, threshold_pct)
           )"""
    )
    conn.execute(
        "INSERT INTO alerts (chat_id, metric, threshold_pct, was_above) VALUES (7, 'sell', 3.5, 1)"
    )
    conn.execute(
        "INSERT INTO alerts (chat_id, metric, threshold_pct, was_above) VALUES (7, 'buy', 8.0, 0)"
    )
    conn.commit()
    conn.close()

    st = BotStorage(db)  # применяет миграцию
    alerts = st.list_alerts(7)
    assert len(alerts) == 2
    by_metric = {a.metric: a for a in alerts}
    assert by_metric["spread_sell"].kind == "spread"
    assert by_metric["spread_sell"].threshold == 3.5
    assert by_metric["spread_sell"].direction == "above"
    assert by_metric["spread_sell"].active is True      # was_above=1 перенесён
    assert by_metric["spread_buy"].active is False
    # новые алерты создаются без конфликтов
    assert st.add_alert(7, "blue_buyusd", "abs", 1600.0, "above") is True
