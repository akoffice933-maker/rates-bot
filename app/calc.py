"""Калькулятор обмена: сумма → результат по лучшей площадке.

Режимы: buy_ars (ARS→USDT), sell_ars (USDT→ARS), buy_usd (USD→USDT),
sell_usd (USDT→USD), arb (арбитражный цикл USDT→USD→USDT).
Чистый модуль: (режим, сумма, снапшот) → текст.
"""
from __future__ import annotations

from . import formatting as fmt
from .i18n import t

MODES = ("buy_ars", "sell_ars", "buy_usd", "sell_usd", "arb")

MODE_LABEL_KEY = {
    "buy_ars": "CALC_MODE_BUY_ARS",
    "sell_ars": "CALC_MODE_SELL_ARS",
    "buy_usd": "CALC_MODE_BUY_USD",
    "sell_usd": "CALC_MODE_SELL_USD",
    "arb": "CALC_MODE_ARB",
}


def parse_amount(raw: str) -> float | None:
    """Разбор суммы: 1000 / 1 000 / 1500,5 / 1,500 / 1.500,50 / 1,500.50 / 1.500.000."""
    s = raw.strip().replace(" ", "").replace("\u00a0", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        if len(tail) == 3 and head.isdigit():
            s = s.replace(",", "")          # тысячи: 1,500
        else:
            s = s.replace(",", ".")         # десятичная: 1500,5
    elif s.count(".") > 1:
        s = s.replace(".", "")              # тысячи точками: 1.500.000
    try:
        value = float(s)
    except ValueError:
        return None
    return value if value > 0 else None


def _amt(x: float, lang: str, decimals: int = 2) -> str:
    return fmt.money(x, lang, decimals)


def calc_text(mode: str, amount: float, snap, lang: str) -> str | None:
    m_ars = snap.usdt
    m_usd = getattr(snap, "usdt_usd", None)

    if mode == "buy_ars":
        if not (m_ars and m_ars.asks):
            return None
        q = m_ars.asks[0]
        got = amount / q.ask
        lines = [f"<b>{t(lang, 'CALC_TITLE_BUY_ARS', amount=_amt(amount, lang))}</b>", ""]
        lines.append(t(lang, "CALC_BEST_LINE", venue=q.name, price=fmt.money(q.ask, lang),
                       result=f"{_amt(got, lang)} USDT"))
        if m_ars.median_ask:
            med = amount / m_ars.median_ask
            lines.append(t(lang, "CALC_VS_MEDIAN", median=fmt.money(m_ars.median_ask, lang),
                           result=f"{_amt(med, lang)} USDT", diff=f"+{_amt(got - med, lang)}"))
        lines.append("")
        lines.append(t(lang, "CALC_VOLUME_NOTE"))

    elif mode == "sell_ars":
        if not (m_ars and m_ars.bids):
            return None
        q = m_ars.bids[0]
        got = amount * q.bid
        lines = [f"<b>{t(lang, 'CALC_TITLE_SELL_ARS', amount=_amt(amount, lang))}</b>", ""]
        lines.append(t(lang, "CALC_BEST_LINE", venue=q.name, price=fmt.money(q.bid, lang),
                       result=f"${_amt(got, lang)} ARS"))
        if m_ars.median_bid:
            med = amount * m_ars.median_bid
            sign = "+" if got >= med else "-"
            lines.append(t(lang, "CALC_VS_MEDIAN", median=fmt.money(m_ars.median_bid, lang),
                           result=f"${_amt(med, lang)} ARS", diff=f"{sign}{_amt(abs(got - med), lang)}"))

    elif mode == "buy_usd":
        if not (m_usd and m_usd.asks):
            return None
        q = m_usd.asks[0]
        got = amount / q.ask
        lines = [f"<b>{t(lang, 'CALC_TITLE_BUY_USD', amount=_amt(amount, lang))}</b>", ""]
        lines.append(t(lang, "CALC_BEST_LINE", venue=q.name, price=fmt.money(q.ask, lang, 4),
                       result=f"{_amt(got, lang)} USDT"))
        if m_usd.median_ask:
            med = amount / m_usd.median_ask
            lines.append(t(lang, "CALC_VS_MEDIAN", median=fmt.money(m_usd.median_ask, lang, 4),
                           result=f"{_amt(med, lang)} USDT", diff=f"+{_amt(got - med, lang)}"))

    elif mode == "sell_usd":
        if not (m_usd and m_usd.bids):
            return None
        q = m_usd.bids[0]
        got = amount * q.bid
        lines = [f"<b>{t(lang, 'CALC_TITLE_SELL_USD', amount=_amt(amount, lang))}</b>", ""]
        lines.append(t(lang, "CALC_BEST_LINE", venue=q.name, price=fmt.money(q.bid, lang, 4),
                       result=f"${_amt(got, lang)} USD"))
        if m_usd.median_bid:
            med = amount * m_usd.median_bid
            sign = "+" if got >= med else "-"
            lines.append(t(lang, "CALC_VS_MEDIAN", median=fmt.money(m_usd.median_bid, lang, 4),
                           result=f"${_amt(med, lang)} USD", diff=f"{sign}{_amt(abs(got - med), lang)}"))

    elif mode == "arb":
        if not (m_usd and m_usd.asks and m_usd.bids):
            return None
        buy_q, sell_q = m_usd.asks[0], m_usd.bids[0]
        usd = amount * sell_q.bid
        back = usd / buy_q.ask
        profit = back - amount
        pct = profit / amount * 100
        lines = [f"<b>{t(lang, 'CALC_TITLE_ARB', amount=_amt(amount, lang))}</b>", ""]
        lines.append(t(lang, "CALC_ARB_STEPS",
                       sell_venue=sell_q.name, sell_price=fmt.money(sell_q.bid, lang, 4),
                       usd=_amt(usd, lang),
                       buy_venue=buy_q.name, buy_price=fmt.money(buy_q.ask, lang, 4),
                       usdt=_amt(back, lang)))
        lines.append("")
        lines.append(t(lang, "CALC_ARB_GROSS", profit=f"+{_amt(profit, lang)}", pct=fmt.pct(pct, lang, 2)))
        lines.append(t(lang, "CALC_ARB_FEES"))
    else:
        return None
    return "\n".join(lines)
