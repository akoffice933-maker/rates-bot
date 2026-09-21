"""Тесты сервисного слоя: методология, фильтр выбросов, кэш, отказоустойчивость."""
from datetime import datetime, timezone

import pytest

from app.service import RatesService, build_market
from app.sources.criptoya import VenueQuote

from .fixtures import load

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

BLUELYTICS = load("bluelytics.json")
DOLARAPI = load("dolarapi.json")
CRIPTOYA = load("criptoya_usdt_ars.json")


class FakeClient:
    """Подставной HTTP-клиент: отдаёт фикстуры по подстроке в URL, умеет «падать»."""

    def __init__(self, bluelytics=None, dolarapi=None, criptoya=None, fail=()):
        self.fixtures = {"bluelytics": bluelytics, "dolarapi": dolarapi, "criptoya": criptoya}
        self.fail = set(fail)
        self.calls: list[str] = []

    async def get_json(self, url: str):
        self.calls.append(url)
        for name in self.fail:
            if name in url:
                raise RuntimeError(f"source {name} unavailable")
        for name, payload in self.fixtures.items():
            if name in url:
                if payload is None:
                    raise RuntimeError(f"no fixture for {name}")
                return payload
        raise AssertionError(f"unexpected url: {url}")


def make_service(client: FakeClient, **kwargs) -> RatesService:
    kwargs.setdefault("cache_ttl_seconds", 60)
    kwargs.setdefault("force_min_interval_seconds", 0)
    return RatesService(client, **kwargs)


async def test_snapshot_from_live_fixtures():
    service = make_service(FakeClient(bluelytics=BLUELYTICS, dolarapi=DOLARAPI, criptoya=CRIPTOYA))
    snap = await service.get_snapshot()

    assert snap.blue and snap.oficial
    assert snap.mep and snap.ccl
    assert snap.usdt and snap.usdt.asks and snap.usdt.bids
    assert snap.source_errors == ()

    # выбросы отфильтрованы: HTX (1930/1122 при рынке ~1596) не должен попасть
    assert "huobip2p" not in {q.key for q in snap.usdt.asks}
    assert "huobip2p" not in {q.key for q in snap.usdt.bids}

    # лучшая покупка USDT = минимальный ask из отфильтрованных
    assert snap.usdt.asks[0].ask == min(q.ask for q in snap.usdt.asks)
    # лучшая продажа USDT = максимальный bid из отфильтрованных
    assert snap.usdt.bids[0].bid == max(q.bid for q in snap.usdt.bids)

    # спреды в разумных пределах
    ss, sb = snap.spread_sell_pct(), snap.spread_buy_pct()
    assert ss is not None and -50 < ss < 100
    assert sb is not None and -50 < sb < 100


async def test_spread_math_synthetic():
    bl = {
        "oficial": {"value_buy": 100, "value_sell": 102},
        "blue": {"value_buy": 100, "value_sell": 102},
    }
    ct = {
        "a": {"totalAsk": 110, "totalBid": 105, "time": 1789990000},
        "b": {"totalAsk": 112, "totalBid": 103, "time": 1789990000},
        "c": {"totalAsk": 500, "totalBid": 50, "time": 1789990000},  # выброс
    }
    service = make_service(FakeClient(bluelytics=bl, criptoya=ct))
    snap = await service.get_snapshot()

    # медианы после фильтра выброса c
    assert snap.usdt.median_ask == pytest.approx(111)
    assert snap.usdt.median_bid == pytest.approx(104)

    # sell: (104 - 100) / 100 = +4%
    assert snap.spread_sell_pct() == pytest.approx(4.0)
    # buy: (111 - 102) / 102
    assert snap.spread_buy_pct() == pytest.approx((111 - 102) / 102 * 100)

    # лучшие предложения и исключение выброса
    assert snap.usdt.asks[0].key == "a"
    assert snap.usdt.bids[0].key == "a"
    assert {q.key for q in snap.usdt.asks} == {"a", "b"}
    assert {q.key for q in snap.usdt.bids} == {"a", "b"}


def test_build_market_filtering_unit():
    quotes = [
        VenueQuote("a", "A", 100, 99, None),
        VenueQuote("b", "B", 101, 100, None),
        VenueQuote("c", "C", 102, 101, None),
        VenueQuote("d", "D", 300, 50, None),  # выброс в обе стороны
    ]
    m = build_market(quotes)
    assert [q.key for q in m.asks] == ["a", "b", "c"]        # по возрастанию
    assert [q.key for q in m.bids] == ["c", "b", "a"]        # по убыванию
    assert m.median_ask == pytest.approx(101)
    assert m.median_bid == pytest.approx(100)


async def test_cache():
    client = FakeClient(bluelytics=BLUELYTICS, dolarapi=DOLARAPI, criptoya=CRIPTOYA)
    service = make_service(client)
    await service.get_snapshot()
    await service.get_snapshot()  # из кэша, новых запросов нет
    assert len(client.calls) == 3
    await service.get_snapshot(force=True)  # принудительное обновление
    assert len(client.calls) == 6


async def test_volume_specific_criptoya_cache():
    """USD-часть кэшируется общая, criptoya — отдельно на каждый объём."""
    client = FakeClient(bluelytics=BLUELYTICS, dolarapi=DOLARAPI, criptoya=CRIPTOYA)
    service = make_service(client)

    s100 = await service.get_snapshot(volume=100)
    await service.get_snapshot(volume=100)      # кэш
    s1000 = await service.get_snapshot(volume=1000)  # новый объём → новый запрос criptoya

    assert s100.usdt and s1000.usdt
    assert len([u for u in client.calls if "bluelytics" in u]) == 1
    assert len([u for u in client.calls if "dolarapi" in u]) == 1
    assert len([u for u in client.calls if "criptoya" in u]) == 2
    assert any("/1000" in u for u in client.calls)


async def test_all_sources_fail_returns_last_good():
    client = FakeClient(bluelytics=BLUELYTICS, dolarapi=DOLARAPI, criptoya=CRIPTOYA)
    service = make_service(client)
    snap1 = await service.get_snapshot()
    assert snap1.blue

    client.fail = {"bluelytics", "dolarapi", "criptoya"}
    snap2 = await service.get_snapshot(force=True)
    # отдали предыдущий (stale) снапшот, а не пустоту
    assert snap2.fetched_at == snap1.fetched_at
    assert snap2.blue


async def test_partial_failure():
    client = FakeClient(bluelytics=BLUELYTICS, criptoya=CRIPTOYA, fail={"dolarapi"})
    service = make_service(client)
    snap = await service.get_snapshot()
    assert snap.blue and snap.usdt
    assert "dolarapi" in snap.source_errors
    assert snap.mep is None and snap.ccl is None
