"""Веб: en-локаль, CSV-экспорт истории, страница и JSON /compare."""
import os
import tempfile
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import formatting as fmt
from app.bestchange import BestChangeResult
from app.p2p import P2PResult
from app.service import RatesService, Snapshot, UsdtMarket
from app.sources.criptoya import VenueQuote
from app.storage import RateHistoryStore
from app.web import compare_payload, create_app

from .fixtures import load

NOW = datetime(2026, 9, 22, 19, 0, tzinfo=timezone.utc)

BLUELYTICS = load("bluelytics.json")
DOLARAPI = load("dolarapi.json")
CRIPTOYA_ARS = load("criptoya_usdt_ars.json")


class FakeClient:
    async def get_json(self, url: str):
        if "bluelytics" in url:
            return BLUELYTICS
        if "dolarapi" in url:
            return DOLARAPI
        if "criptoya" in url:
            return CRIPTOYA_ARS
        raise AssertionError(f"unexpected url: {url}")


class FakeBestChange:
    """usdt_mp/mp_usdt -> один и тот же «обменник»."""

    def __init__(self, ok: bool = True):
        self.ok = ok

    async def get(self, key: str, force: bool = False):
        if not self.ok:
            return BestChangeResult(ok=False, error="unavailable", direction_key=key)
        from app.sources.bestchange import ExchangerRow
        give = 1600.0 if key == "mp_usdt" else None
        return BestChangeResult(
            ok=True, error=None, direction_key=key,
            rows=(ExchangerRow(
                name="TestEx", click_url="https://www.bestchange.com/click.php?id=1",
                give=give if give else 1.0, give_unit="ARS MP" if give else "USDT",
                receive=1563.82 if not give else 1.0,
                receive_unit="USDT" if not give else "USDT TRC20",
                min_amount=100.0, max_amount=None, reserve=1e6, reviews=42,
            ),),
        )


class FakeP2P:
    def __init__(self, ok: bool = True):
        self.ok = ok

    async def get(self, force: bool = False):
        if not self.ok:
            return P2PResult(ok=False, error="blocked")
        from app.sources.binance_p2p import P2PAd
        return P2PResult(
            ok=True, error=None,
            sell_ads=(P2PAd(price=1590.0, min_amount=100.0, max_amount=9000.0, available=500.0,
                            methods=("Mercado Pago",), advertiser="WebTrader", completion_rate=0.98),),
            buy_ads=(P2PAd(price=1598.5, min_amount=100.0, max_amount=8000.0, available=300.0,
                           methods=("Mercado Pago",), advertiser="WebBuyer", completion_rate=0.96),),
        )


def make_client(**deps) -> TestClient:
    service = RatesService(FakeClient(), cache_ttl_seconds=60)
    return TestClient(create_app(service=service, **deps))


# ---------- en-локаль ----------

def test_en_locale_page():
    with make_client() as c:
        body = c.get("/", params={"lang": "en"}).text
        assert "Exchange rates in Argentina" in body
        assert ">Buy<" in body and ">Sell<" in body
        # en-формат чисел: 1,517.00 (запятая — тысячи, точка — десятичный)
        assert "1,517.00" in body


def test_fmt_en():
    assert fmt.money(1550.5, "en") == "1,550.50"
    assert fmt.money(1550.5, "es") == "1.550,50"
    assert fmt.money(1550.5, "ru") == "1 550,50"
    assert fmt.pct(3.7, "en") == "+3.70 %"


# ---------- CSV ----------

def test_history_csv():
    store = RateHistoryStore(os.path.join(tempfile.mkdtemp(), "h.db"))
    snap = Snapshot(
        fetched_at=NOW,
        usdt=UsdtMarket(
            all_venues=(),
            asks=(VenueQuote(key="a", name="A", ask=1593.25, bid=None, time=NOW),),
            bids=(VenueQuote(key="b", name="B", ask=None, bid=1595.41, time=NOW),),
            median_ask=1593.25, median_bid=1595.41,
        ),
    )
    store.maybe_record(snap, 0)
    with make_client(history=store) as c:
        r = c.get("/api/history.csv", params={"hours": 24})
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers.get("content-disposition", "")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("ts_utc,blue_buy,blue_sell")
        assert len(lines) == 2
        assert "1593.25" in lines[1]
        assert c.get("/api/history.csv", params={"hours": 0}).status_code == 422


# ---------- /compare ----------

def test_compare_page_es():
    with make_client(bestchange=FakeBestChange(), p2p=FakeP2P()) as c:
        r = c.get("/compare")
        assert r.status_code == 200
        body = r.text
        assert "comparación de fuentes" in body
        assert "TestEx" in body and "WebTrader" in body
        assert 'href="https://www.bestchange.com/click.php?id=1"' in body
        assert 'href="/"' in body  # навигация назад


def test_compare_page_en():
    with make_client(bestchange=FakeBestChange(), p2p=FakeP2P()) as c:
        body = c.get("/compare", params={"lang": "en"}).text
        assert "source comparison" in body
        assert "Sell USDT" in body


def test_compare_page_p2p_blocked():
    with make_client(bestchange=FakeBestChange(), p2p=FakeP2P(ok=False)) as c:
        body = c.get("/compare", params={"lang": "en"}).text
        assert "unavailable right now" in body
        assert "TestEx" in body  # остальные источники живут


async def test_api_compare_payload():
    from app.sources.bluelytics import RatePair

    snap = Snapshot(
        fetched_at=NOW, blue=RatePair(buy=1517.0, sell=1550.0),
        usdt=UsdtMarket(
            all_venues=(),
            asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=NOW),),
            bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=NOW),),
            median_ask=1593.25, median_bid=1595.41,
        ),
    )
    data = compare_payload(snap, None, None, await FakeP2P().get())  # без BestChange
    # без BestChange: criptoYa + p2p
    sources_sell = {e["source"] for e in data["sell"]}
    assert sources_sell == {"criptoya", "binance_p2p"}
    # продажа: лучший = максимум; покупка: лучший = минимум
    assert data["best_sell"] == 1598.5
    assert data["best_buy"] == 1590.0
    assert data["fetched_at"].startswith("2026-09-22")


def test_api_compare_endpoint():
    with make_client(bestchange=FakeBestChange(), p2p=FakeP2P()) as c:
        data = c.get("/api/compare").json()
        sell_sources = {e["source"] for e in data["sell"]}
        assert sell_sources == {"criptoya", "bestchange", "binance_p2p"}
        assert data["best_sell"] == max(e["price"] for e in data["sell"] if e["price"])
        assert data["best_buy"] == min(e["price"] for e in data["buy"] if e["price"])


def test_compare_page_no_deps():
    """Без bestchange/p2p страница живёт на одном CriptoYa."""
    with make_client() as c:
        r = c.get("/compare")
        assert r.status_code == 200
        assert "MEXC P2P" in r.text or "SatoshiTango" in r.text
