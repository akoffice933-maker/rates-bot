from datetime import datetime, timezone

from app.sources import bluelytics, criptoya, dolarapi

from .fixtures import load

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_bluelytics_parse():
    data = bluelytics.parse(load("bluelytics.json"), NOW)
    assert data.oficial.buy and data.oficial.sell
    assert data.blue.buy and data.blue.sell
    # compra < venta — инвариант рыночной котировки
    assert data.blue.buy < data.blue.sell
    assert 100 < data.blue.sell < 100_000


def test_dolarapi_parse():
    data = dolarapi.parse(load("dolarapi.json"), NOW)
    for key in ("oficial", "blue", "mep", "ccl"):
        assert key in data.rates, f"нет {key}"
    assert data.rates["mep"].sell  # bolsa -> mep
    assert data.rates["ccl"].sell  # contadoconliqui -> ccl


def test_criptoya_parse():
    quotes = criptoya.parse(load("criptoya_usdt_ars.json"), NOW)
    keys = {q.key for q in quotes}
    assert "binancep2p" in keys
    # мусорная площадка HTX присутствует в сырых данных (её отфильтрует сервис)
    assert "huobip2p" in keys
    for q in quotes:
        assert q.name, f"нет человекочитаемого имени для {q.key}"
        assert q.time is not None
    binance = next(q for q in quotes if q.key == "binancep2p")
    assert binance.name == "Binance P2P"
    assert binance.ask and binance.bid


def test_criptoya_names_fallback():
    quotes = criptoya.parse({"unknownvenue": {"ask": 100, "bid": 99, "time": 0}}, NOW)
    assert quotes[0].name == "Unknownvenue"
