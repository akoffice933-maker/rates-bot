"""BestChange: лучшие обменники по популярным направлениям (парсинг HTML направлений).

Публичный XML-файл bc.bestchange закрыт (404, проверено 21.09.2026), но страницы
направлений открыты и серверно-рендерятся — парсим их.

Структура строки (проверено на живой странице sberbank-to-tether-trc20):
  <tr onclick="ccl(<id>, <from>, <to>, 0)">
    <a href="/click.php?id=..&from=..&to=..&city=0">   — официальная ссылка-переход на обменник
    <div class="ca">Name</div>
    <td class="bi"><div class="fs">89.5812 <small>RUB Sberbank</small></div>
        <div class="fm">min 50 000 / max 300 000</div></td>   — отдаёте (за 1 единицу получаемого)
    <td class="bi">1 <small>USDT TRC20</small></td>           — получаете
    <td class="ar">24 721 000</td>                            — резерв (в получаемой валюте)
    <td class="rw">...169...</td>                             — отзывы

Атрибуция BestChange обязательна (ссылка на источник в каждом сообщении).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BASE = "https://www.bestchange.com"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass(frozen=True)
class Direction:
    key: str
    slug: str            # URL: {slug}.html
    name_ru: str
    name_es: str
    better: str          # "min" — ниже курс, выгоднее купить; "max" — выше, выгоднее продать


DIRECTIONS: dict[str, Direction] = {
    d.key: d
    for d in (
        # --- Аргентина (ARS) ---
        Direction("usdt_mp", "tether-trc20-to-mercado-pago",
                  "USDT TRC20 → Mercado Pago ARS", "USDT TRC20 → Mercado Pago ARS", "max"),
        Direction("mp_usdt", "mercado-pago-to-tether-trc20",
                  "Mercado Pago ARS → USDT TRC20", "Mercado Pago ARS → USDT TRC20", "min"),
        Direction("usdt_card_ars", "tether-trc20-to-visa-mastercard-ars",
                  "USDT TRC20 → Карта ARS", "USDT TRC20 → Tarjeta ARS", "max"),
        Direction("usdt_wire_ars", "tether-trc20-to-wire-ars",
                  "USDT TRC20 → Перевод ARS", "USDT TRC20 → Transferencia ARS", "max"),
        Direction("usdt_prex", "tether-trc20-to-prex-ars",
                  "USDT TRC20 → Prex ARS", "USDT TRC20 → Prex ARS", "max"),
        Direction("usdt_cash_ars", "tether-trc20-to-ars-cash",
                  "USDT TRC20 → Наличные ARS", "USDT TRC20 → Efectivo ARS", "max"),
        Direction("usdt_wire_usd", "tether-trc20-to-wire-usd",
                  "USDT TRC20 → Перевод USD", "USDT TRC20 → Transferencia USD", "max"),
        Direction("wire_usd_usdt", "wire-usd-to-tether-trc20",
                  "Перевод USD → USDT TRC20", "Transferencia USD → USDT TRC20", "min"),
        # --- Россия (RUB) ---
        Direction("sb_usdt", "sberbank-to-tether-trc20",
                  "Сбербанк RUB → USDT TRC20", "Sberbank RUB → USDT TRC20", "min"),
        Direction("usdt_sb", "tether-trc20-to-sberbank",
                  "USDT TRC20 → Сбербанк RUB", "USDT TRC20 → Sberbank RUB", "max"),
        Direction("tf_usdt", "tinkoff-to-tether-trc20",
                  "Т-Банк RUB → USDT TRC20", "T-Bank RUB → USDT TRC20", "min"),
        Direction("usdt_tf", "tether-trc20-to-tinkoff",
                  "USDT TRC20 → Т-Банк RUB", "USDT TRC20 → T-Bank RUB", "max"),
        Direction("usdt_btc", "tether-trc20-to-bitcoin",
                  "USDT TRC20 → Bitcoin", "USDT TRC20 → Bitcoin", "max"),
    )
}
DIRECTIONS_ORDER = tuple(DIRECTIONS)


@dataclass(frozen=True)
class ExchangerRow:
    name: str
    click_url: str                  # официальный переход BestChange на сайт обменника
    give: float                     # отдаёте (в валюте give_unit) за 1 единицу receive_unit
    give_unit: str
    receive: float                  # получаете
    receive_unit: str
    min_amount: float | None        # в валюте give_unit
    max_amount: float | None
    reserve: float | None           # в валюте receive_unit
    reviews: int | None


def direction_url(direction: Direction) -> str:
    return f"{BASE}/{direction.slug}.html"


def _num(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


_ROW_RE = re.compile(r'<tr onclick="ccl\((\d+), \d+, \d+, \d+\)">(.*?)</tr>', re.S)
_NAME_RE = re.compile(r'<div class="ca"[^>]*>([^<]+)</div>')
_CLICK_RE = re.compile(r'<a rel="nofollow" target="_blank" href="(/click\.php\?[^"]+)"')
_BI_RE = re.compile(r'<td class="bi">(.*?)</td>', re.S)
_FS_RE = re.compile(r'<div class="fs">([\d\s.,\xa0]+)\s*(?:<small[^>]*>([^<]*)</small>)?')
_PLAIN_RE = re.compile(r'^\s*([\d\s.,\xa0]+)\s*(?:<small[^>]*>([^<]*)</small>)?')
_MIN_RE = re.compile(r'>\s*(?:min|мин)[\s.:]*([\d\s\u00a0]+)\s*<', re.I)
_MAX_RE = re.compile(r'>\s*(?:max|макс)[\s.:]*([\d\s\u00a0]+)\s*<', re.I)
_RESERVE_RE = re.compile(r'<td class="ar[^"]*"[^>]*>\s*([\d\s\u00a0]+?)\s*</td>')
_REVIEWS_RE = re.compile(r'class="rwan"[^>]*>\s*(\d+)\s*<')


def _parse_amount_cell(cell: str) -> tuple[float | None, str]:
    """Ячейка bi: либо с div.fs (курс + единица), либо плоская «1 USDT TRC20»."""
    m = _FS_RE.search(cell)
    if not m:
        m = _PLAIN_RE.match(cell.strip())
    if not m:
        return None, ""
    return _num(m.group(1)), (m.group(2) or "").strip()


def parse_rows(html: str) -> list[ExchangerRow]:
    rows: list[ExchangerRow] = []
    for _exchanger_id, row_html in _ROW_RE.findall(html):
        name_m = _NAME_RE.search(row_html)
        click_m = _CLICK_RE.search(row_html)
        if not name_m or not click_m:
            continue

        bi_cells = _BI_RE.findall(row_html)
        give, give_unit = _parse_amount_cell(bi_cells[0]) if bi_cells else (None, "")
        receive, receive_unit = _parse_amount_cell(bi_cells[1]) if len(bi_cells) > 1 else (None, "")
        if give is None or receive is None:
            continue

        min_m, max_m = _MIN_RE.search(row_html), _MAX_RE.search(row_html)
        reserve_m = _RESERVE_RE.search(row_html)
        reviews_m = _REVIEWS_RE.search(row_html)

        rows.append(
            ExchangerRow(
                name=name_m.group(1).strip(),
                click_url=BASE + click_m.group(1),
                give=give,
                give_unit=give_unit,
                receive=receive,
                receive_unit=receive_unit,
                min_amount=_num(min_m.group(1)) if min_m else None,
                max_amount=_num(max_m.group(1)) if max_m else None,
                reserve=_num(reserve_m.group(1)) if reserve_m else None,
                reviews=int(reviews_m.group(1)) if reviews_m else None,
            )
        )
    return rows
