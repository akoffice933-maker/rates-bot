"""RatesGuru (kurs.expert): монитор обменников, второй источник RUB⇄USDT.

Страницы направлений отдают данные в машинно-читаемых атрибутах ячеек:
    <td class="eGive" unit="RUB" amount="88.87" minamount="8764">  — отдаёте;
    <td class="eGet"  unit="USDT" amount="1">                      — получаете;
    <td class="eFund" amount="2500000" unit="USDT">                — резерв;
    <td class="eRep"  title="57%">                                 — репутация;
    tr@rep_zone="green|yellow|red_zone"                            — зона доверия.

Курс направления — всегда «RUB за 1 USDT»: для RUB→USDT это eGive.amount,
для USDT→RUB — eGet.amount (поле rate_side в Direction).

Особенность: сортировка страницы — по курсу (лучшие сверху), но в топе бывают
бэйт-строки (живой пример: 97,45 RUB/USDT при кластере ~85–90). Отсев —
в сервисе (медианный фильтр, как в методологии бота).

Проверено живыми запросами 22.09.2026: страницы 200 OK, ~80–135 строк.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass

BASE = "https://rates.guru/en/exchange"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.5",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass(frozen=True)
class Direction:
    key: str
    path: str            # URL: {BASE}/{path}/
    name_ru: str
    name_es: str
    better: str          # "min" — ниже курс, выгоднее купить; "max" — выше, выгоднее продать
    rate_side: str       # откуда брать курс (RUB за 1 USDT): "give" | "get"


DIRECTIONS: dict[str, Direction] = {
    d.key: d
    for d in (
        Direction("sb_usdt", "sberbank/usdt.trc-20",
                  "Сбербанк RUB → USDT TRC20", "Sberbank RUB → USDT TRC20", "min", "give"),
        Direction("usdt_sb", "usdt.trc-20/sberbank",
                  "USDT TRC20 → Сбербанк RUB", "USDT TRC20 → Sberbank RUB", "max", "get"),
        Direction("tf_usdt", "tinkoff/usdt.trc-20",
                  "Т-Банк RUB → USDT TRC20", "T-Bank RUB → USDT TRC20", "min", "give"),
        Direction("usdt_tf", "usdt.trc-20/tinkoff",
                  "USDT TRC20 → Т-Банк RUB", "USDT TRC20 → T-Bank RUB", "max", "get"),
    )
}
DIRECTIONS_ORDER = ("sb_usdt", "usdt_sb", "tf_usdt", "usdt_tf")


@dataclass(frozen=True)
class RGRow:
    name: str
    rate: float                    # RUB за 1 USDT
    give_unit: str
    get_unit: str
    min_amount: float | None       # в валюте give
    reserve: float | None
    reserve_unit: str | None
    reputation: int | None         # % одобрения (0..100)
    zone: str | None               # green | yellow | red


_ROW_RE = re.compile(r'<tr class="eLine[^"]*".*?</tr>', re.S)
_NAME_RE = re.compile(r'<td class="eName[^"]*" name="([^"]+)"')
_ZONE_RE = re.compile(r'rep_zone="(\w+?)_zone"')
_REP_RE = re.compile(r'<td class="eRep" title="(\d+)%"')
_GIVE_RE = re.compile(
    r'<td class="eGive[^"]*"[^>]*?\sunit="(\w+)"[^>]*?\samount="([\d.]+)"(?:[^>]*?\sminamount="(\d+)")?[^>]*>'
)
_GET_RE = re.compile(r'<td class="eGet[^"]*"[^>]*?\sunit="(\w+)"[^>]*?\samount="([\d.]+)"')
_FUND_RE = re.compile(r'<td class="eFund[^"]*"[^>]*?\samount="([\d.]+)"[^>]*?\sunit="(\w+)"')


def parse_rows(page_html: str, direction: Direction) -> tuple[RGRow, ...]:
    rows: list[RGRow] = []
    for tr in _ROW_RE.findall(page_html):
        name_m = _NAME_RE.search(tr)
        give_m = _GIVE_RE.search(tr)
        get_m = _GET_RE.search(tr)
        if not (name_m and give_m and get_m):
            continue
        fund_m = _FUND_RE.search(tr)
        rep_m = _REP_RE.search(tr)
        zone_m = _ZONE_RE.search(tr)
        give_unit, give_amount = give_m.group(1), float(give_m.group(2))
        get_unit, get_amount = get_m.group(1), float(get_m.group(2))
        rate = give_amount if direction.rate_side == "give" else get_amount
        if rate <= 0:
            continue
        rows.append(
            RGRow(
                name=_html.unescape(name_m.group(1)),
                rate=rate,
                give_unit=give_unit,
                get_unit=get_unit,
                min_amount=float(give_m.group(3)) if give_m.group(3) else None,
                reserve=float(fund_m.group(1)) if fund_m else None,
                reserve_unit=fund_m.group(2) if fund_m else None,
                reputation=int(rep_m.group(1)) if rep_m else None,
                zone=zone_m.group(1) if zone_m else None,
            )
        )
    return tuple(rows)


def direction_url(direction: Direction) -> str:
    return f"{BASE}/{direction.path}/"
