"""История курсов: RateHistoryStore (интервал записи, чтение) + веб-эндпоинты."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.service import RatesService, Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote
from app.storage import RateHistoryStore
from app.web import create_app, history_chart_svg

from .fixtures import load

NOW = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)

BLUELYTICS = load("bluelytics.json")
DOLARAPI = load("dolarapi.json")
CRIPTOYA_ARS = load("criptoya_usdt_ars.json")
CRIPTOYA_USD = load("criptoya_usdt_usd.json")


class FakeClient:
    async def get_json(self, url: str):
        if "USDT/USD" in url:
            return CRIPTOYA_USD
        if "bluelytics" in url:
            return BLUELYTICS
        if "dolarapi" in url:
            return DOLARAPI
        if "criptoya" in url:
            return CRIPTOYA_ARS
        raise AssertionError(f"unexpected url: {url}")


def make_snap(ts: datetime, usdt_usd: bool = True) -> Snapshot:
    market = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=ts),),
        bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=ts),),
        median_ask=1593.25, median_bid=1595.41,
    )
    usd_market = None
    if usdt_usd:
        usd_market = UsdtMarket(
            all_venues=(),
            asks=(VenueQuote(key="xapo", name="Xapo", ask=1.0014, bid=None, time=ts),),
            bids=(VenueQuote(key="ripio", name="Ripio", ask=None, bid=1.0386, time=ts),),
            median_ask=1.0014, median_bid=1.0386,
        )
    return Snapshot(
        fetched_at=ts,
        blue=RatePair(buy=1517.0, sell=1550.0),
        oficial=RatePair(buy=1483.0, sell=1534.0),
        mep=RatePair(buy=1531.0, sell=1536.0),
        ccl=RatePair(buy=1595.0, sell=1596.0),
        usdt=market,
        usdt_usd=usd_market,
    )


def fresh_store() -> RateHistoryStore:
    return RateHistoryStore(os.path.join(tempfile.mkdtemp(), "history.db"))


# ---------- RateHistoryStore ----------

def test_maybe_record_interval_gating():
    store = fresh_store()
    snap1 = make_snap(NOW)
    assert store.maybe_record(snap1, min_interval_seconds=900) is True
    # слишком рано — пропускаем
    snap2 = make_snap(NOW + timedelta(seconds=300))
    assert store.maybe_record(snap2, 900) is False
    # прошло достаточно — пишем
    snap3 = make_snap(NOW + timedelta(seconds=900))
    assert store.maybe_record(snap3, 900) is True
    rows = store.get_history(0)
    assert len(rows) == 2
    assert rows[0]["blue_sell"] == 1550.0
    assert rows[0]["usdt_ask"] == 1593.25
    assert rows[0]["usdtusd_ask"] == 1.0014 and rows[0]["usdtusd_bid"] == 1.0386


def test_record_without_usdtusd():
    store = fresh_store()
    store.maybe_record(make_snap(NOW, usdt_usd=False), 0)
    rows = store.get_history(0)
    assert rows[0]["usdtusd_ask"] is None and rows[0]["usdtusd_bid"] is None
    assert rows[0]["usdt_bid"] == 1595.41


def test_get_history_window():
    store = fresh_store()
    store.maybe_record(make_snap(NOW - timedelta(hours=3)), 0)
    store.maybe_record(make_snap(NOW - timedelta(hours=2)), 0)
    store.maybe_record(make_snap(NOW - timedelta(hours=1)), 0)
    since = int((NOW - timedelta(minutes=150)).timestamp())  # 2,5 часа
    assert len(store.get_history(since)) == 2   # 1ч и 2ч назад
    assert len(store.get_history(0)) == 3


# ---------- SVG-график ----------

def test_chart_svg_content():
    store = fresh_store()
    for i in range(5):
        store.maybe_record(make_snap(NOW - timedelta(hours=5 - i)), 0)
    rows = store.get_history(0)
    svg = history_chart_svg(rows, "usdtusd", "ru")
    assert svg.startswith("<svg")
    assert "polyline" in svg and "#4ade80" in svg and "#f87171" in svg
    assert "Покупка USDT/USD" in svg
    # метрика blue — другая подпись
    assert "Blue продажа" in history_chart_svg(rows, "blue", "ru")


def test_chart_svg_not_enough_points():
    store = fresh_store()
    store.maybe_record(make_snap(NOW), 0)
    assert history_chart_svg(store.get_history(0), "usdt", "es") is None


# ---------- веб-эндпоинты ----------

def make_web_client(store: RateHistoryStore) -> TestClient:
    service = RatesService(FakeClient(), cache_ttl_seconds=60)
    return TestClient(create_app(service=service, history=store))


def test_web_records_with_interval_gating():
    """Веб пишет историю на запросах, но не чаще HISTORY_INTERVAL_SECONDS."""
    store = fresh_store()
    with make_web_client(store) as c:
        assert c.get("/api/rates").status_code == 200
        assert c.get("/api/rates").status_code == 200
        assert c.get("/").status_code == 200
    rows = store.get_history(0)
    assert len(rows) == 1                     # интервал 900с — дубли не пишутся
    point = rows[0]
    assert point["blue_sell"] and point["usdt_ask"]
    assert point["usdtusd_ask"] == 1.0014 and point["usdtusd_bid"] == 1.0386


def test_web_serves_prefilled_history():
    """Отдача предзаполненной истории: JSON, SVG, usdt_usd в /api/rates."""
    store = fresh_store()
    for i in range(3):
        store.maybe_record(make_snap(NOW - timedelta(hours=3 - i)), 0)
    with make_web_client(store) as c:
        hist = c.get("/api/history", params={"hours": 24}).json()
        assert hist["hours"] == 24 and len(hist["points"]) == 3

        r = c.get("/chart.svg", params={"hours": 24, "metric": "usdtusd", "lang": "ru"})
        assert r.status_code == 200
        assert "image/svg+xml" in r.headers["content-type"]
        assert "<svg" in r.text and "polyline" in r.text

        assert c.get("/chart.svg", params={"metric": "nope"}).status_code == 422
        assert c.get("/api/history", params={"hours": 0}).status_code == 422

        rates = c.get("/api/rates").json()
        assert rates["usdt_usd"]["best_ask"]["venue"] == "Xapo"
        assert rates["usdt_usd"]["best_bid"]["venue"] == "Ripio"


def test_web_no_history_store():
    """Без history (юнит-режим) эндпоинты не падают."""
    service = RatesService(FakeClient(), cache_ttl_seconds=60)
    with TestClient(create_app(service=service)) as c:
        assert c.get("/api/history").json() == {"hours": 24, "points": []}
        assert c.get("/chart.svg").status_code == 404
