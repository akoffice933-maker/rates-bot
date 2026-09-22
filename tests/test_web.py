"""Веб-часть ТЗ: FastAPI — таблица, JSON API, health, OpenAPI."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.service import RatesService
from app.web import create_app

from .fixtures import load

NOW = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)

BLUELYTICS = load("bluelytics.json")
DOLARAPI = load("dolarapi.json")
CRIPTOYA = load("criptoya_usdt_ars.json")


class FakeClient:
    async def get_json(self, url: str):
        if "bluelytics" in url:
            return BLUELYTICS
        if "dolarapi" in url:
            return DOLARAPI
        if "criptoya" in url:
            return CRIPTOYA
        raise AssertionError(f"unexpected url: {url}")


def make_client(**kwargs) -> TestClient:
    service = RatesService(FakeClient(), cache_ttl_seconds=60, **kwargs)
    return TestClient(create_app(service=service))


# ---------- JSON API ----------

def test_api_rates():
    with make_client() as c:
        r = c.get("/api/rates")
        assert r.status_code == 200
        data = r.json()
        assert data["usd"]["blue"]["buy"] and data["usd"]["blue"]["sell"]
        assert data["usd"]["oficial"]["sell"]
        assert data["usd"]["mep"]["sell"] and data["usd"]["ccl"]["sell"]
        assert data["usdt"]["median_ask"] and data["usdt"]["median_bid"]
        assert data["usdt"]["best_ask"]["side"] == "ask"
        assert data["usdt"]["best_ask"]["price"] == min(
            data["usdt"]["best_ask"]["price"], data["usdt"]["median_ask"]
        )
        # спреды по медианам (методология бота)
        assert data["spreads_pct"]["sell_usdt_vs_blue"] > 0
        assert data["source_errors"] == []
        assert "fetched_at" in data


def test_api_usdt_volume():
    with make_client() as c:
        r = c.get("/api/usdt", params={"volume": 500})
        assert r.status_code == 200
        assert r.json()["volume"] == 500


def test_api_usdt_volume_validation():
    with make_client() as c:
        assert c.get("/api/usdt", params={"volume": 0}).status_code == 422
        assert c.get("/api/usdt", params={"volume": 1_000_000}).status_code == 422


def test_health():
    with make_client() as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_openapi_docs():
    with make_client() as c:
        assert c.get("/docs").status_code == 200
        spec = c.get("/openapi.json").json()
        paths = set(spec["paths"])
        assert {"/", "/api/rates", "/api/usdt", "/health"} <= paths


# ---------- HTML ----------

def test_index_html_es():
    with make_client() as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        body = r.text
        assert "Cotizaciones en Argentina" in body
        assert "Blue" in body and "MEP" in body and "CCL" in body
        assert "<table" in body and "USDT/ARS" in body
        assert "/api/rates" in body and "/docs" in body


def test_index_html_ru():
    with make_client() as c:
        body = c.get("/", params={"lang": "ru"}).text
        assert "Котировки в Аргентине" in body
        assert "Покупка" in body and "Продажа" in body


def test_index_lang_validation():
    with make_client() as c:
        assert c.get("/", params={"lang": "en"}).status_code == 422
