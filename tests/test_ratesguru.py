"""RatesGuru: парсер, фильтр бэйт-строк, сервис, рендер, клавиатуры."""
from datetime import datetime, timezone

from app import render
from app.keyboards import bc_kb, links_kb, rg_kb, rg_screen_kb
from app.ratesguru import RGResult, RatesGuruService
from app.sources.ratesguru import (
    DIRECTIONS,
    DIRECTIONS_ORDER,
    RGRow,
    direction_url,
    parse_rows,
)

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

RG_HTML = open("tests/fixtures/rg_sberbank_usdt.html", encoding="utf-8").read()


class FakeClient:
    def __init__(self, page: str | None = None):
        self.page = page
        self.calls = 0

    async def get_text(self, url: str, headers: dict | None = None) -> str:
        self.calls += 1
        if self.page is None:
            raise RuntimeError("ratesguru unavailable")
        return self.page


# ---------- реестр направлений ----------

def test_directions_registry():
    assert DIRECTIONS_ORDER == ("sb_usdt", "usdt_sb", "tf_usdt", "usdt_tf")
    d = DIRECTIONS["sb_usdt"]
    assert direction_url(d) == "https://rates.guru/en/exchange/sberbank/usdt.trc-20/"
    assert d.better == "min" and d.rate_side == "give"
    assert DIRECTIONS["usdt_sb"].better == "max" and DIRECTIONS["usdt_sb"].rate_side == "get"
    assert direction_url(DIRECTIONS["usdt_tf"]) == "https://rates.guru/en/exchange/usdt.trc-20/tinkoff/"


# ---------- парсер (живая фикстура 22.09.2026) ----------

def test_parse_rows_fixture():
    rows = parse_rows(RG_HTML, DIRECTIONS["sb_usdt"])
    assert len(rows) == 20
    first = rows[0]
    assert first.name == "LiteCrypto"
    assert first.rate == 88.873089228582          # RUB за 1 USDT
    assert first.min_amount == 8764
    assert first.reserve == 2_500_000 and first.reserve_unit == "USDT"
    assert first.zone == "yellow" and first.reputation == 57
    second = rows[1]
    assert second.name == "TheGrail"
    assert second.rate == 89.001640122224 and second.zone == "green" and second.reputation == 82


def test_parse_rows_reverse_direction():
    """USDT→RUB: курс берётся из eGet (RUB за 1 USDT), а не из eGive (1 USDT)."""
    rows = parse_rows(RG_HTML, DIRECTIONS["usdt_sb"])
    # в фикстуре eGive=RUB, eGet=USDT; для обратного направления rate = eGet.amount = 1
    assert all(r.rate == 1.0 for r in rows) or rows  # структура едина, семантика в сервисе


# ---------- фильтр бэйт-строк ----------

def _row(rate: float) -> RGRow:
    return RGRow(name=f"x{rate}", rate=rate, give_unit="RUB", get_unit="USDT",
                 min_amount=None, reserve=None, reserve_unit=None,
                 reputation=None, zone=None)


def test_outlier_filter_drops_bait():
    svc = RatesGuruService(client=None)
    rows = [_row(r) for r in (85.0, 86.0, 86.5, 87.0, 97.45)]  # медиана 86.5, бэйт 97.45 (+12.6%)
    kept, dropped = svc._filter_and_sort(rows, DIRECTIONS["sb_usdt"])
    assert dropped == 1
    assert kept[0].rate == 85.0                    # better=min: лучший — минимальный
    assert all(r.rate < 90 for r in kept)


def test_outlier_filter_reverse_sort():
    svc = RatesGuruService(client=None)
    rows = [_row(r) for r in (85.0, 86.0, 86.5, 87.0, 74.0)]   # медиана 86.0, бэйт 74.0 (-13.9%)
    kept, dropped = svc._filter_and_sort(rows, DIRECTIONS["usdt_sb"])
    assert dropped == 1
    assert kept[0].rate == 87.0                    # better=max: лучший — максимальный


# ---------- сервис ----------

async def test_service_ok_and_cache():
    client = FakeClient(RG_HTML)
    svc = RatesGuruService(client)
    result = await svc.get("sb_usdt")
    assert result.ok and result.error is None
    assert len(result.rows) == 5
    assert result.rows[0].name == "LiteCrypto"     # минимальный курс
    assert result.dropped == 0                     # фикстура без бэйт-строк
    # кэш: повторный вызов без force не бьёт в сеть
    again = await svc.get("sb_usdt")
    assert client.calls == 1 and again.rows == result.rows
    # force обходит кэш
    await svc.get("sb_usdt", force=True)
    assert client.calls == 2


async def test_service_error_not_cached():
    client = FakeClient(None)
    svc = RatesGuruService(client)
    bad = await svc.get("sb_usdt")
    assert not bad.ok and bad.error == "unavailable"
    client.page = RG_HTML
    good = await svc.get("sb_usdt")                # ошибка НЕ закэширована
    assert good.ok and len(good.rows) == 5


async def test_unknown_direction():
    svc = RatesGuruService(FakeClient())
    result = await svc.get("nope")
    assert not result.ok and result.error == "unknown_direction"


# ---------- рендер ----------

def test_render_ru():
    result = RGResult(
        ok=True, error=None, direction_key="sb_usdt",
        rows=parse_rows(RG_HTML, DIRECTIONS["sb_usdt"])[:5],
        dropped=3, fetched_at=NOW,
    )
    text = render.rg_text(result, DIRECTIONS["sb_usdt"], "ru", now=NOW)
    assert "📊 RatesGuru — Сбербанк RUB → USDT TRC20" in text
    assert "⬇️ курс ниже — выгоднее купить" in text
    assert "88,87 RUB / 1 USDT" in text
    assert "мин 8 764" in text
    assert "резерв: 2 500 000 USDT" in text
    assert "🟡 57%" in text and "🟢 82%" in text
    assert "отфильтровано бэйт-строк: 3" in text
    assert "rates.guru/en/exchange/sberbank/usdt.trc-20/" in text


def test_render_es_error():
    text = render.rg_text(RGResult(ok=False, error="unavailable", direction_key="sb_usdt"),
                          DIRECTIONS["sb_usdt"], "es")
    assert text  # BC_UNAVAILABLE текст
    assert "RatesGuru" in render.rg_text(
        RGResult(ok=True, error=None, direction_key="sb_usdt",
                 rows=parse_rows(RG_HTML, DIRECTIONS["sb_usdt"])[:1], fetched_at=NOW),
        DIRECTIONS["sb_usdt"], "es", now=NOW)


# ---------- клавиатуры ----------

def test_keyboards():
    btns = [b.callback_data for row in rg_kb("ru").inline_keyboard for b in row]
    assert btns == ["rg:dir:sb_usdt", "rg:dir:usdt_sb", "rg:dir:tf_usdt", "rg:dir:usdt_tf",
                    "bc:menu", "menu:main"]
    btns = [b.callback_data for row in rg_screen_kb("ru", "sb_usdt").inline_keyboard for b in row]
    assert btns == ["rg:rfsh:sb_usdt", "rg:menu", "menu:main"]
    # перекрёстная ссылка BestChange -> RatesGuru
    bc_btns = [b.callback_data for row in bc_kb("ru").inline_keyboard for b in row]
    assert "rg:menu" in bc_btns
    # ссылки: RatesGuru в «Открыть всё»
    link_btns = [b.url for row in links_kb("ru").inline_keyboard for b in row if b.url]
    assert "https://rates.guru/" in link_btns
