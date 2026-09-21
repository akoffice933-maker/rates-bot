"""Мастер обмена: направляет пользователя к лучшему курсу и объясняет, как совершить обмен.

Сценарии:
  buy_usdt  — купить USDT за песо  → лучший ask изCriptoYa + шаги Binance P2P (эскроу);
  sell_usdt — продать USDT за песо → лучший bid + шаги P2P;
  buy_usd   — купить наличный USD  → сравнение MEP/blue/oficial (лучший = минимальный);
  sell_usd  — продать наличный USD → сравнение blue/oficial/MEP (лучший = максимальный).

Живая часть (лучший курс, суммы) считается по снапшоту, шаги и предупреждения —
статический контент (i18n, es/ru).
"""
from __future__ import annotations

from . import formatting as fmt
from .i18n import t
from .service import Snapshot

SCENARIOS = ("buy_usdt", "sell_usdt", "buy_usd", "sell_usd")

# сценарий -> ключ заголовка в i18n
_TITLES = {
    "buy_usdt": "GUIDE_SC_BUY_USDT",
    "sell_usdt": "GUIDE_SC_SELL_USDT",
    "buy_usd": "GUIDE_SC_BUY_USD",
    "sell_usd": "GUIDE_SC_SELL_USD",
}

# сценарий -> (шаги, альтернативы, предупреждение)
_BLOCKS = {
    "buy_usdt": ("GUIDE_P2P_BUY_STEPS", "GUIDE_BUY_USDT_ALTS", "GUIDE_P2P_WARN"),
    "sell_usdt": ("GUIDE_P2P_SELL_STEPS", "GUIDE_SELL_USDT_ALTS", "GUIDE_P2P_WARN"),
    "buy_usd": ("GUIDE_MEP_STEPS", "GUIDE_BUY_USD_ALTS", "GUIDE_CASH_WARN"),
    "sell_usd": ("GUIDE_CUEVA_STEPS", "GUIDE_SELL_USD_ALTS", "GUIDE_CASH_WARN"),
}


def guide_menu_text(lang: str) -> str:
    return f"<b>{t(lang, 'GUIDE_TITLE')}</b>\n\n{t(lang, 'GUIDE_PROMPT')}"


def _head_usdt(snap: Snapshot, scenario: str, lang: str) -> str | None:
    m = snap.usdt
    if not m:
        return None
    if scenario == "buy_usdt":
        if not m.asks:
            return None
        best = m.asks[0]  # минимальный ask — где дешевле купить USDT
        spread = snap.spread_buy_pct()
        return t(
            lang,
            "GUIDE_BUY_USDT_HEAD",
            venue=best.name,
            price=fmt.money(best.ask, lang),
            per=fmt.per_thousand(best.ask, lang),
            pct=fmt.pct(spread, lang) if spread is not None else "—",
        )
    if not m.bids:
        return None
    best = m.bids[0]  # максимальный bid — где выгоднее продать USDT
    spread = snap.spread_sell_pct()
    return t(
        lang,
        "GUIDE_SELL_USDT_HEAD",
        venue=best.name,
        price=fmt.money(best.bid, lang),
        per=fmt.money(best.bid * 1000, lang),
        pct=fmt.pct(spread, lang) if spread is not None else "—",
    )


def _usd_rows(snap: Snapshot, lang: str, side: str) -> list[tuple[str, float, str]]:
    """Курсы USD по источникам: side='sell' для покупки USD, 'buy' для продажи."""
    rows: list[tuple[str, float, str]] = []
    for pair, name, src in (
        (snap.mep, "MEP", "GUIDE_SRC_MEP"),
        (snap.blue, "Blue", "GUIDE_SRC_BLUE"),
        (snap.oficial, "Oficial", "GUIDE_SRC_BANK"),
    ):
        value = getattr(pair, side, None) if pair else None
        if value is not None:
            rows.append((name, value, t(lang, src)))
    return rows


def _head_usd(snap: Snapshot, scenario: str, lang: str) -> tuple[str, str] | None:
    """(сравнительная таблица курсов, строка лучшего варианта) или None."""
    side = "sell" if scenario == "buy_usd" else "buy"
    rows = _usd_rows(snap, lang, side)
    if not rows:
        return None

    best = min(rows, key=lambda r: r[1]) if scenario == "buy_usd" else max(rows, key=lambda r: r[1])
    ordered = sorted(rows, key=lambda r: r[1], reverse=(scenario == "sell_usd"))

    lines = [t(lang, "GUIDE_BUY_USD_HEAD" if scenario == "buy_usd" else "GUIDE_SELL_USD_HEAD"), ""]
    for name, value, src in ordered:
        mark = " 🥇" if value == best[1] else ""
        lines.append(f"• {name} {src}: ${fmt.money(value, lang)}{mark}")
    best_line = t(lang, "GUIDE_BEST_LINE", name=best[0], price=fmt.money(best[1], lang))
    return "\n".join(lines), best_line


def guide_text(snap: Snapshot, scenario: str, lang: str) -> str | None:
    """Экран сценария: лучший курс сейчас + пошаговая инструкция + альтернативы + риски."""
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    if scenario in ("buy_usdt", "sell_usdt"):
        head = _head_usdt(snap, scenario, lang)
    else:
        result = _head_usd(snap, scenario, lang)
        head = f"{result[0]}\n\n{result[1]}" if result else None
    if head is None:
        return None

    steps_key, alts_key, warn_key = _BLOCKS[scenario]
    title = t(lang, _TITLES[scenario])
    return "\n".join(
        [
            f"<b>{title}</b>",
            "",
            head,
            "",
            t(lang, steps_key),
            "",
            t(lang, alts_key),
            "",
            t(lang, warn_key),
            "",
            t(lang, "GUIDE_FOOTER"),
        ]
    )
