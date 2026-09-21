"""Тесты BestChange: парсер, сервис (кэш/ошибки), рендер со ссылками на обменники."""
from __future__ import annotations

from datetime import datetime, timezone

from app import render
from app.bestchange import BestChangeResult, BestChangeService
from app.keyboards import bc_kb, bc_screen_kb
from app.sources.bestchange import DIRECTIONS, DIRECTIONS_ORDER, direction_url, parse_rows


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
HTML = open("tests/fixtures/bc_sberbank_usdt.html", encoding="utf-8").read()
D = DIRECTIONS["sb_usdt"]


# ---------- реестр направлений ----------

def test_directions_registry():
    assert DIRECTIONS_ORDER == (
        # Аргентина — первыми (целевая аудитория бота)
        "usdt_mp", "mp_usdt", "usdt_card_ars", "usdt_wire_ars", "usdt_prex", "usdt_cash_ars",
        "usdt_wire_usd", "wire_usd_usdt",
        # Россия
        "sb_usdt", "usdt_sb", "tf_usdt", "usdt_tf", "usdt_btc",
    )
    assert direction_url(D) == "https://www.bestchange.com/sberbank-to-tether-trc20.html"
    assert D.better == "min"           # покупка USDT: ниже курс — лучше
    assert DIRECTIONS["usdt_sb"].better == "max"
    assert direction_url(DIRECTIONS["usdt_mp"]) == "https://www.bestchange.com/tether-trc20-to-mercado-pago.html"
    assert DIRECTIONS["usdt_mp"].better == "max"   # продажа USDT: выше курс ARS — лучше
    assert DIRECTIONS["mp_usdt"].better == "min"


# ---------- парсер (живая страница, обрезана до 25 строк) ----------

def test_parse_rows_live_fixture():
    rows = parse_rows(HTML)
    assert len(rows) == 25
    first = rows[0]
    assert first.name == "Tsunami"
    assert first.click_url.startswith("https://www.bestchange.com/click.php?id=")
    assert first.give > 0 and first.receive == 1
    assert "RUB" in first.give_unit and "USDT" in first.receive_unit
    for r in rows:
        assert r.name and r.click_url
        assert r.give > 0


def test_parse_rows_wirebit_exact():
    rows = parse_rows(HTML)
    w = rows[2]
    assert w.name == "Wirebit"
    assert w.give == 89.5812
    assert w.min_amount == 50000 and w.max_amount == 300000
    assert w.reserve == 24721000
    assert w.reviews == 169


def test_parse_rows_empty_and_garbage():
    assert parse_rows("<html>нет таблицы</html>") == []
    assert parse_rows("") == []


# ---------- сервис ----------

class FakeBCClient:
    def __init__(self, html: str | None = None):
        self.html = html
        self.calls = 0

    async def get_text(self, url, headers=None):
        self.calls += 1
        if self.html is None:
            raise RuntimeError("HTTP 403")
        return self.html


async def test_service_ok_and_cache():
    client = FakeBCClient(HTML)
    svc = BestChangeService(client, cache_ttl_seconds=300, top_n=5)
    r1 = await svc.get("sb_usdt")
    assert r1.ok and len(r1.rows) == 5
    assert r1.rows[0].name == "Tsunami"      # порядок BestChange сохранён
    await svc.get("sb_usdt")                 # кэш
    assert client.calls == 1
    await svc.get("sb_usdt", force=True)     # принудительно
    assert client.calls == 2


async def test_service_error_not_cached_long():
    client = FakeBCClient(None)
    svc = BestChangeService(client, cache_ttl_seconds=300)
    r = await svc.get("sb_usdt")
    assert r.ok is False and r.error == "unavailable"
    await svc.get("sb_usdt")                 # ошибка не держится в кэше 5 минут
    assert client.calls == 2


async def test_service_unknown_direction():
    svc = BestChangeService(FakeBCClient())
    try:
        await svc.get("diagonal")
        assert False, "ожидали ValueError"
    except ValueError:
        pass


# ---------- рендер ----------

def test_render_bc_with_links():
    result = BestChangeResult(
        ok=True, error=None, direction_key="sb_usdt",
        rows=tuple(parse_rows(HTML)[:5]), fetched_at=NOW,
    )
    text = render.bc_text(result, D, "ru", now=NOW)
    assert "BestChange — Сбербанк RUB → USDT TRC20" in text
    assert "⬇️ курс ниже — выгоднее купить" in text
    assert 'href="https://www.bestchange.com/click.php?id=' in text   # ссылка на обменник
    assert ">Tsunami</a>" in text
    assert "89,58" in text and "USDT TRC20" in text
    assert "мин 50 000" in text and "резерв" in text
    assert "✓169" in text
    assert "Данные: BestChange" in text


def test_render_bc_unavailable():
    result = BestChangeResult(ok=False, error="unavailable", direction_key="sb_usdt", fetched_at=NOW)
    text = render.bc_text(result, D, "es", now=NOW)
    assert "no está disponible" in text


# ---------- клавиатуры ----------

def test_bc_keyboards():
    cbs = {b.callback_data for row in bc_kb("ru").inline_keyboard for b in row}
    assert {f"bc:dir:{k}" for k in DIRECTIONS_ORDER} <= cbs
    assert "menu:main" in cbs
    sc = {b.callback_data for row in bc_screen_kb("es", "sb_usdt").inline_keyboard for b in row}
    assert "bc:rfsh:sb_usdt" in sc and "bc:menu" in sc


def test_render_round_numbers_regression():
    """90 RUB не должно превращаться в «9» (баг rstrip в первой версии)."""
    from app.sources.bestchange import ExchangerRow

    row = ExchangerRow(
        name="X", click_url="https://www.bestchange.com/click.php?id=1&from=10&to=42&city=0",
        give=1.0, give_unit="USDT TRC20", receive=90.0, receive_unit="RUB Sberbank",
        min_amount=112, max_amount=557, reserve=19_891_775, reviews=18,
    )
    result = BestChangeResult(ok=True, error=None, direction_key="usdt_sb",
                              rows=(row,), fetched_at=NOW)
    text = render.bc_text(result, DIRECTIONS["usdt_sb"], "ru", now=NOW)
    assert "90 RUB Sberbank" in text
    assert "9 RUB Sberbank" not in text
    assert "1 USDT TRC20" in text


# ---------- ARS-направления (живая страница Mercado Pago, 21.09.2026) ----------

MP_HTML = open("tests/fixtures/bc_usdt_mercadopago_ars.html", encoding="utf-8").read()


def test_parse_rows_ars_fixture():
    rows = parse_rows(MP_HTML)
    assert len(rows) == 15
    first = rows[0]
    assert first.name == "SafuExchange"
    assert first.give == 1.0 and first.receive == 1563.82
    assert first.give_unit == "USDT TRC20" and "ARS" in first.receive_unit
    assert first.click_url.startswith("https://www.bestchange.com/click.php?id=")
    for r in rows:  # курсы в ARS, не RUB и не мусор
        assert 1000 < r.receive < 3000, r


def test_render_ars_direction():
    result = BestChangeResult(
        ok=True, error=None, direction_key="usdt_mp",
        rows=tuple(parse_rows(MP_HTML)[:5]), fetched_at=NOW,
    )
    text = render.bc_text(result, DIRECTIONS["usdt_mp"], "ru", now=NOW)
    assert "USDT TRC20 → Mercado Pago ARS" in text
    assert "⬆️ курс выше — выгоднее продать" in text
    assert "1 USDT TRC20 / 1 563,82 ARS MP" in text
    assert "SafuExchange" in text
    assert 'href="https://www.bestchange.com/click.php?id=' in text
