"""Экран /usdtusd: безнал (CriptoYa USDT/USD) + наличный кросс через blue."""
from datetime import datetime, timezone

import pytest

from app import render
from app.alerts import AlertManager, METRICS, fired_text
from app.storage import Alert
from app.keyboards import main_menu, uu_kb
from app.service import RatesService, Snapshot, UsdtMarket, UsdtUsdView, build_market
from app.sources import criptoya
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote

from .fixtures import load

NOW = datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc)

BLUELYTICS = load("bluelytics.json")
DOLARAPI = load("dolarapi.json")
CRIPTOYA_ARS = load("criptoya_usdt_ars.json")
CRIPTOYA_USD = load("criptoya_usdt_usd.json")


class FakeClient:
    """Как FakeClient в test_service, но различает пары CriptoYa по URL."""

    def __init__(self, usd=None, ars=None, fail_usd=False):
        self.usd, self.ars, self.fail_usd = usd, ars, fail_usd

    async def get_json(self, url: str):
        if "USDT/USD" in url:
            if self.fail_usd:
                raise RuntimeError("criptoya usdt/usd unavailable")
            if self.usd is None:
                raise RuntimeError("no usd fixture")
            return self.usd
        if "USDT/ARS" in url:
            return self.ars
        if "bluelytics" in url:
            return BLUELYTICS
        if "dolarapi" in url:
            return DOLARAPI
        raise AssertionError(f"unexpected url: {url}")


def make_view(usd=CRIPTOYA_USD) -> UsdtUsdView:
    """View с ручным снапшотом: blue 1517/1550 + лучшие USDT/ARS 1593,25/1595,41."""
    market = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=NOW),),
        bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=NOW),),
        median_ask=1593.25,
        median_bid=1595.41,
    )
    snap = Snapshot(fetched_at=NOW, blue=RatePair(buy=1517.0, sell=1550.0), usdt=market)
    return UsdtUsdView(snap=snap, usd=build_market(criptoya.parse(usd, NOW)) if usd else None)


# ---------- парсинг и порядок ----------

def test_usd_pair_venue_names():
    quotes = criptoya.parse(CRIPTOYA_USD, NOW)
    names = {q.key: q.name for q in quotes}
    assert names["xapo"] == "Xapo"
    assert names["banexcoin"] == "Banexcoin"
    assert names["x4t"] == "X4T"


def test_usd_market_best_prices():
    m = build_market(criptoya.parse(CRIPTOYA_USD, NOW))
    # лучший ask = минимальный (Xapo почти паритет), лучший bid = максимальный
    assert m.asks[0].name == "Xapo"
    assert m.asks[0].ask == min(q.ask for q in m.asks)
    assert m.bids[0].bid == max(q.bid for q in m.bids)
    # kucoinp2p отдаёт bid=0 -> должен выпасть из bids
    assert "kucoinp2p" not in {q.key for q in m.bids}


# ---------- наличный кросс ----------

def test_cash_cross_math():
    text = render.usdtusd_text(make_view(), "ru", now=NOW)
    # купить: 1593,25 / 1517 (blue compra) = 1,0503 (+5,0%)
    assert "1,0503 USD" in text
    assert "+5,0 %" in text
    # продать: 1595,41 / 1550 (blue venta) = 1,0293 (+2,9%)
    assert "1,0293 USD" in text
    assert "+2,9 %" in text
    # путь и площадки
    assert "1 517/1 550" in text
    assert "MEXC P2P / SatoshiTango" in text
    # подсказка про cuevas
    assert "cuevas" in text


def test_cash_cross_es():
    text = render.usdtusd_text(make_view(), "es", now=NOW)
    assert "💵 USDT ⇄ USD — Argentina" in text
    assert "1,0503 USD" in text
    assert "1.517/1.550" in text
    assert "cuevas" in text


# ---------- полный экран ----------

def test_full_screen_cashless():
    text = render.usdtusd_text(make_view(), "ru", now=NOW)
    assert "💵 USDT ⇄ USD — Аргентина" in text
    assert "💳 Безнал — CriptoYa (13 площадок)" in text
    assert "Купить USDT (дешевле — лучше):" in text
    assert "Продать USDT (дороже — лучше):" in text
    assert "Xapo" in text and "1,0014" in text
    # атрибуция обоих источников
    assert "criptoya.com" in text and "bluelytics.com.ar" in text
    # кликабельные ссылки площадок
    assert 'href="https://xapo.com/"' in text


def test_cashless_only_without_blue():
    """Если blue/USDT-ARS недоступны, безнальная часть всё равно рендерится."""
    snap = Snapshot(fetched_at=NOW)
    text = render.usdtusd_text(UsdtUsdView(snap=snap, usd=build_market(criptoya.parse(CRIPTOYA_USD, NOW))), "ru", now=NOW)
    assert text is not None
    assert "Xapo" in text
    assert "Наличные" not in text


def test_no_data():
    text = render.usdtusd_text(UsdtUsdView(snap=Snapshot(fetched_at=NOW)), "ru", now=NOW)
    assert text is None


# ---------- сервис ----------

async def test_service_view_and_failure():
    service = RatesService(FakeClient(usd=CRIPTOYA_USD, ars=CRIPTOYA_ARS), cache_ttl_seconds=60)
    view = await service.get_usdtusd_view()
    assert view.snap.usdt and view.snap.blue
    assert view.usd and view.usd.asks[0].name == "Xapo"

    # сбой USDT/USD: экран живёт на наличном кроссе
    svc2 = RatesService(FakeClient(usd=None, ars=CRIPTOYA_ARS, fail_usd=True), cache_ttl_seconds=60)
    view2 = await svc2.get_usdtusd_view()
    assert view2.usd is None
    text = render.usdtusd_text(view2, "ru", now=NOW)
    assert text is not None and "Наличные" in text


# ---------- клавиатуры ----------

def test_menu_has_usdtusd_button():
    for lang in ("ru", "es"):
        buttons = [b for row in main_menu(lang).inline_keyboard for b in row]
        assert any(b.callback_data == "uu:scr" for b in buttons)


def test_uu_kb_callbacks():
    buttons = [b for row in uu_kb("ru").inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["uu:rfsh", "scr:links", "menu:main"]


# ---------- арбитражный цикл ----------

def test_arb_block():
    """Продать по лучшему bid (Ripio) -> купить обратно по лучшему ask (Xapo): +3,72%."""
    text = render.usdtusd_text(make_view(), "ru", now=NOW)
    assert "♻️ Арбитраж: цикл USD → USDT → USD" in text
    assert "продать USDT: Ripio по 1,0386" in text
    assert "купить обратно: Xapo по 1,0014" in text
    assert "+3,71 %" in text


def test_arb_block_es():
    text = render.usdtusd_text(make_view(), "es", now=NOW)
    assert "♻️ Arbitraje: ciclo USD → USDT → USD" in text
    assert "vender USDT: Ripio a 1,0386" in text


# ---------- метрики алертов USDT⇄USD ----------

def _arb_snap() -> Snapshot:
    market = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=NOW),),
        bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=NOW),),
        median_ask=1593.25,
        median_bid=1595.41,
    )
    return Snapshot(
        fetched_at=NOW,
        blue=RatePair(buy=1517.0, sell=1550.0),
        usdt=market,
        usdt_usd=build_market(criptoya.parse(CRIPTOYA_USD, NOW)),
    )


def test_metrics_eval_usdtusd():
    snap = _arb_snap()
    assert METRICS["usdtusd_sell"].eval(snap) == pytest.approx(1.0386)   # Ripio bid
    assert METRICS["usdtusd_buy"].eval(snap) == pytest.approx(1.0014)   # Xapo ask
    assert METRICS["usdtusd_cash_sell"].eval(snap) == pytest.approx(1595.41 / 1550.0)
    assert METRICS["usdtusd_cash_buy"].eval(snap) == pytest.approx(1593.25 / 1517.0)
    # без данных метрика просто не определена — алерт не проверяется
    for key in ("usdtusd_sell", "usdtusd_buy", "usdtusd_cash_sell", "usdtusd_cash_buy"):
        assert METRICS[key].eval(Snapshot(fetched_at=NOW)) is None


def test_hysteresis_for_usd_pairs():
    manager = AlertManager(None)
    uu = Alert(id=1, chat_id=1, metric="usdtusd_sell", kind="abs", threshold=1.03,
               direction="above", enabled=True, active=False, last_fired_at=None)
    assert manager._hysteresis(uu) == pytest.approx(0.00103)   # ~0,1%, а не 0,5 ARS
    ars = Alert(id=2, chat_id=1, metric="blue_buyusd", kind="abs", threshold=1500.0,
                direction="above", enabled=True, active=False, last_fired_at=None)
    assert manager._hysteresis(ars) == pytest.approx(1.5)      # прежнее поведение ARS


def test_fired_text_usdtusd():
    alert = Alert(id=3, chat_id=1, metric="usdtusd_sell", kind="abs", threshold=1.03,
                  direction="above", enabled=True, active=False, last_fired_at=None)
    text = fired_text(alert, 1.0386, _arb_snap(), "ru")
    assert "$1,0386" in text and "⩾ $1,03" in text
    assert "Ripio" in text and "Xapo" in text      # обе стороны безнала в контексте
    assert "нал, расчёт" in text                   # + наличный расчёт


async def test_snapshot_full_separate_from_plain():
    """Обычный снапшот не платит запросом USDT/USD; полный — содержит рынок."""
    service = RatesService(FakeClient(usd=CRIPTOYA_USD, ars=CRIPTOYA_ARS), cache_ttl_seconds=60)
    plain = await service.get_snapshot()
    assert plain.usdt_usd is None
    full = await service.get_snapshot_full()
    assert full.usdt_usd and full.usdt_usd.asks[0].name == "Xapo"
    # и тот же рынок доезжает до экрана
    view = await service.get_usdtusd_view()
    assert view.usd is not None and view.usd.bids[0].name == "Ripio"
