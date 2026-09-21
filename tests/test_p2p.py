"""Тесты Binance P2P: пул прокси, парсер, сервис (фильтры/сортировка/кэш), рендер."""
from __future__ import annotations

from datetime import datetime, timezone

from app import render
from app.p2p import BinanceP2PService
from app.proxy_pool import ProxyPool
from app.service import Snapshot, UsdtMarket
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote
from app.sources.binance_p2p import build_payload, parse_ads

from .fixtures import load

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
SELL_FIXTURE = load("binance_p2p_sell.json")
BUY_FIXTURE = load("binance_p2p_buy.json")


# ---------- пул прокси ----------

def test_proxy_pool_rotation():
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    assert [pool.next(), pool.next(), pool.next()] == [
        "http://p1:8080",
        "http://p2:8080",
        "http://p1:8080",
    ]


def test_proxy_pool_failure_skip_and_reset():
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    for _ in range(3):
        pool.report_failure("http://p1:8080")
    # p1 помечен сбойным — выдаём только p2
    assert all(pool.next() == "http://p2:8080" for _ in range(5))
    # после успеха счётчик сбрасывается
    pool.report_success("http://p1:8080")
    assert pool.next() == "http://p1:8080"


def test_proxy_pool_empty_means_direct():
    pool = ProxyPool(None)
    assert pool.next() is None
    pool.report_failure(None)  # не падает и не влияет
    assert pool.next() is None


# ---------- парсер ----------

def test_parse_ads():
    ads = parse_ads(SELL_FIXTURE)
    assert len(ads) == 3
    first = ads[0]
    assert first.price == 1590.0
    assert first.methods == ("Mercado Pago", "Transferencia bancaria")
    assert first.completion_rate == 0.97
    assert first.min_amount == 100000 and first.max_amount == 5000000
    assert first.advertiser == "TraderOne"


def test_parse_ads_tolerates_garbage():
    payload = {
        "code": "000000",
        "data": [
            {"adv": {"price": "abc"}, "advertiser": {}},              # битая цена — пропуск
            {"adv": {"price": "100"}, "advertiser": {}},              # без методов/лимитов — ок
            "мусор",
        ],
    }
    ads = parse_ads(payload)
    assert len(ads) == 1
    assert ads[0].price == 100.0
    assert ads[0].methods == ()
    assert ads[0].completion_rate is None


def test_build_payload():
    p = build_payload("SELL", page=2, rows=20)
    assert p["tradeType"] == "SELL" and p["asset"] == "USDT" and p["fiat"] == "ARS"
    assert p["page"] == 2 and p["rows"] == 20


# ---------- сервис ----------

class FakeP2PClient:
    def __init__(self, fail_with: Exception | None = None):
        self.fail_with = fail_with
        self.calls: list[dict] = []

    async def post_json(self, url, payload, proxy=None, headers=None):
        self.calls.append({"payload": payload, "proxy": proxy})
        if self.fail_with:
            raise self.fail_with
        return SELL_FIXTURE if payload["tradeType"] == "SELL" else BUY_FIXTURE


def make_service(client, **kw) -> BinanceP2PService:
    kw.setdefault("min_completion_rate", 0.90)
    kw.setdefault("pages", 1)
    kw.setdefault("rows", 10)
    kw.setdefault("cache_ttl_seconds", 60)
    return BinanceP2PService(client, proxies=None, **kw)


async def test_service_filters_and_sorting():
    result = await make_service(FakeP2PClient()).get()
    assert result.ok and result.error is None
    # SELL (пользователь покупает): по возрастанию цены, низкий completion отфильтрован
    assert [a.price for a in result.sell_ads] == [1590.0, 1591.5]  # 1588 с rate 0.85 — мимо
    # BUY (пользователь продаёт): по убыванию цены, все три проходят
    assert [a.price for a in result.buy_ads] == [1589.0, 1587.5, 1586.0]
    assert result.fetched_at is not None


async def test_service_blocked_and_cache():
    client = FakeP2PClient(fail_with=RuntimeError("HTTP 403 Forbidden"))
    service = make_service(client)
    result = await service.get()
    assert result.ok is False
    assert result.error == "blocked"
    # кэшируем неудачу — не дёргаем endpoint на каждое нажатие
    await service.get()
    assert len(client.calls) == 4  # 2 стороны × 2 попытки, второй вызов из кэша


async def test_service_unavailable_classification():
    service = make_service(FakeP2PClient(fail_with=RuntimeError("connection reset")))
    result = await service.get()
    assert result.ok is False and result.error == "unavailable"


async def test_service_force_refetch():
    client = FakeP2PClient()
    service = make_service(client)
    await service.get()
    await service.get()          # кэш
    assert len(client.calls) == 2
    await service.get(force=True)  # принудительно
    assert len(client.calls) == 4


# ---------- рендер ----------

def make_snap() -> Snapshot:
    bq = VenueQuote("binancep2p", "Binance P2P", 1596.0, 1590.0, NOW)
    usdt = UsdtMarket(all_venues=(bq,), asks=(), bids=(), median_ask=1610.0, median_bid=1578.0)
    return Snapshot(fetched_at=NOW, blue=RatePair(buy=1517.0, sell=1550.0), usdt=usdt)


async def test_render_p2p_ok():
    result = await make_service(FakeP2PClient()).get()
    text = render.p2p_text(result, make_snap(), "es", now=NOW)
    assert "Binance P2P" in text
    assert "1.590,00" in text and "Mercado Pago" in text
    assert "✓97%" in text and "TraderOne" in text
    assert "100.000–5.000.000 ARS" in text


async def test_render_p2p_fallback():
    result = await make_service(FakeP2PClient(fail_with=RuntimeError("HTTP 403"))).get()
    text = render.p2p_text(result, make_snap(), "ru", now=NOW)
    assert "PROXY_LIST" in text            # подсказка о прокси
    assert "1 590,00" in text              # агрегат CriptoYa как fallback (bid)
    assert "покупка" in text and "продажа" in text
