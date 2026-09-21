"""Тесты дайджеста: подписки, отправка раз в день, дельты, рендер."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from app.digest import AR_TZ, DigestManager, digest_text
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.storage import BotStorage

UTC = timezone.utc


def fresh_storage() -> BotStorage:
    td = tempfile.mkdtemp()
    return BotStorage(os.path.join(td, "digest.db"))


class CollectBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent.append((chat_id, text))


class FailingBot:
    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        raise RuntimeError("chat blocked")


def make_snap(blue_sell=1550.0, median_bid=1578.0, median_ask=1610.0) -> Snapshot:
    usdt = UsdtMarket(
        all_venues=(), asks=(), bids=(), median_ask=median_ask, median_bid=median_bid
    )
    return Snapshot(
        fetched_at=datetime(2026, 9, 21, 13, 0, tzinfo=UTC),
        blue=RatePair(buy=1517.0, sell=blue_sell),
        oficial=RatePair(buy=1484.0, sell=1536.0),
        usdt=usdt,
    )


def ar_time(y, m, d, h, minute=5):
    return datetime(y, m, d, h, minute, tzinfo=AR_TZ).astimezone(UTC)


# ---------- хранилище ----------

def test_digest_subscription_crud(tmp_path):
    st = BotStorage(str(tmp_path / "d.db"))
    assert st.digest_sub(1) is None
    st.digest_subscribe(1, 9)
    assert st.digest_sub(1) == 9
    st.digest_subscribe(1, 18)          # смена часа
    assert st.digest_sub(1) == 18
    assert st.digest_due(18, "2026-09-21") == [1]
    st.digest_mark_sent(1, "2026-09-21")
    assert st.digest_due(18, "2026-09-21") == []    # сегодня уже отправлено
    assert st.digest_due(18, "2026-09-22") == [1]   # завтра снова
    st.digest_unsubscribe(1)
    assert st.digest_sub(1) is None
    assert st.digest_due(18, "2026-09-22") == []


def test_digest_hour_change_keeps_last_sent(tmp_path):
    st = BotStorage(str(tmp_path / "d2.db"))
    st.digest_subscribe(1, 9)
    st.digest_mark_sent(1, "2026-09-21")
    st.digest_subscribe(1, 21)                       # смена часа после отправки
    assert st.digest_due(21, "2026-09-21") == []     # без дубля в день смены
    assert st.digest_due(21, "2026-09-22") == [1]


def test_digest_history_snapshots(tmp_path):
    st = BotStorage(str(tmp_path / "h.db"))
    assert st.get_digest_snapshot("2026-09-21") is None
    st.save_digest_snapshot("2026-09-21", {"blue_sell": 1550.0})
    st.save_digest_snapshot("2026-09-20", {"blue_sell": 1500.0})
    st.save_digest_snapshot("2026-09-19", {"blue_sell": 1490.0})
    assert st.get_digest_snapshot("2026-09-21") == {"blue_sell": 1550.0}
    # последний снимок ДО даты
    assert st.last_digest_snapshot_before("2026-09-21") == {"blue_sell": 1500.0}
    assert st.last_digest_snapshot_before("2026-09-19") is None


# ---------- менеджер ----------

async def test_digest_sends_once_per_day():
    st = fresh_storage()
    st.set_lang(1, "ru")
    st.digest_subscribe(1, 10)
    manager = DigestManager(st)
    snap = make_snap()

    bot = CollectBot()
    sent = await manager.check(bot, snap, now=ar_time(2026, 9, 21, 10, 5))
    assert sent == 1 and len(bot.sent) == 1
    assert "Дайджест" in bot.sent[0][1]

    # повторно в тот же день — тишина
    bot2 = CollectBot()
    sent = await manager.check(bot2, snap, now=ar_time(2026, 9, 21, 10, 45))
    assert sent == 0 and bot2.sent == []

    # снимок дня записан
    assert st.get_digest_snapshot("2026-09-21") is not None


async def test_digest_wrong_hour_not_sent():
    st = fresh_storage()
    st.set_lang(1, "ru")
    st.digest_subscribe(1, 9)
    manager = DigestManager(st)
    bot = CollectBot()
    sent = await manager.check(bot, make_snap(), now=ar_time(2026, 9, 21, 14, 5))
    assert sent == 0 and bot.sent == []


async def test_digest_delta_uses_yesterday_snapshot():
    st = fresh_storage()
    st.set_lang(1, "ru")
    st.digest_subscribe(1, 10)
    # «вчерашний» снимок
    st.save_digest_snapshot("2026-09-20", {"blue_sell": 1500.0, "usdt_median_bid": 1530.0})

    manager = DigestManager(st)
    bot = CollectBot()
    await manager.check(bot, make_snap(blue_sell=1550.0), now=ar_time(2026, 9, 21, 10, 5))
    text = bot.sent[0][1]
    assert "1 550,00" in text
    assert "↑ +3,33 %" in text          # (1550-1500)/1500


async def test_digest_delivery_failure_marks_sent():
    st = fresh_storage()
    st.set_lang(1, "ru")
    st.digest_subscribe(1, 10)
    manager = DigestManager(st)
    sent = await manager.check(FailingBot(), make_snap(), now=ar_time(2026, 9, 21, 10, 5))
    assert sent == 1                     # попытка была
    assert st.digest_due(10, "2026-09-21") == []  # но день помечен — без ретраев


# ---------- рендер ----------

def test_digest_text_no_prev_no_arrows():
    text = digest_text(make_snap(), None, "es", datetime(2026, 9, 21, 10, 0, tzinfo=AR_TZ))
    assert "Digesta" in text
    assert "↑" not in text and "↓" not in text
    assert "Blue" in text and "1.550,00" in text
    assert "/digest" in text


def test_digest_text_with_prev():
    prev = {"blue_sell": 1500.0, "usdt_median_bid": 1600.0}
    text = digest_text(make_snap(blue_sell=1550.0, median_bid=1578.0), prev, "ru",
                       datetime(2026, 9, 21, 10, 0, tzinfo=AR_TZ))
    assert "↑ +3,33 %" in text     # blue sell вырос
    assert "↓ -1,38 %" in text     # медиана bid упала: (1578-1600)/1600
    # спреды присутствуют
    assert "Выгода продажи" in text
