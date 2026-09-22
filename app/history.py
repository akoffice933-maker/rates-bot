"""История курсов для бота: дельты за период по таблице rate_history.

Точки пишут воркер алертов (каждые 15 мин) и веб (на запросах) —
см. RateHistoryStore. Здесь только чистая аналитика и текст.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import formatting as fmt
from .i18n import t

PERIODS = (24, 168, 720)          # часы: сутки / неделя / месяц

# (колонка, i18n-ключ, знаков после запятой)
_METRICS = (
    ("blue_sell", "WEB_CH_BLUE", 2),
    ("mep_sell", "WEB_CH_MEP", 2),
    ("ccl_sell", "HIST_CCL", 2),
    ("usdt_ask", "WEB_CH_USDT_ASK", 2),
    ("usdt_bid", "WEB_CH_USDT_BID", 2),
    ("usdtusd_ask", "WEB_CH_UU_ASK", 4),
    ("usdtusd_bid", "WEB_CH_UU_BID", 4),
)


def period_label(hours: int, lang: str) -> str:
    if hours >= 48:
        return t(lang, "HIST_DAYS", n=hours // 24)
    return t(lang, "HIST_HOURS", n=hours)


def arb_cycle(row: dict) -> float | None:
    """% арбитражного цикла USDT/USD по точке: (bid − ask) / ask."""
    ask, bid = row.get("usdtusd_ask"), row.get("usdtusd_bid")
    if ask and bid:
        return (bid - ask) / ask * 100
    return None


def _delta_str(old: float, new: float, lang: str, decimals: int) -> str:
    pct = (new - old) / old * 100
    arrow = "↑" if pct > 0.005 else ("↓" if pct < -0.005 else "→")
    return f"{fmt.money(old, lang, decimals)} → {fmt.money(new, lang, decimals)} ({arrow}{fmt.pct(pct, lang, 2)})"


def history_text(rows: list[dict], lang: str, hours: int,
                 now: datetime | None = None) -> str:
    """Текст экрана /history: было → стало по каждой метрике + цикл арбитража."""
    now = now or datetime.now(timezone.utc)
    if len(rows) < 2:
        return t(lang, "HIST_NO_DATA")
    latest = rows[-1]
    candidates = [r for r in rows if r["ts"] != latest["ts"]]
    if not candidates:
        return t(lang, "HIST_NO_DATA")
    target = latest["ts"] - hours * 3600
    base = min(candidates, key=lambda r: abs(r["ts"] - target))

    lines = [f"<b>{t(lang, 'HIST_TITLE', period=period_label(hours, lang))}</b>", ""]
    for col, key, decimals in _METRICS:
        old, new = base.get(col), latest.get(col)
        if old and new:
            lines.append(f"• {t(lang, key)}: {_delta_str(old, new, lang, decimals)}")
    old_cycle, new_cycle = arb_cycle(base), arb_cycle(latest)
    if old_cycle is not None and new_cycle is not None:
        lines.append(
            f"• {t(lang, 'HIST_ARB_CYCLE')}: "
            f"{fmt.pct(old_cycle, lang, 2)} → {fmt.pct(new_cycle, lang, 2)}"
        )
    lines.append("")
    since = fmt.ts_local(datetime.fromtimestamp(rows[0]["ts"], tz=timezone.utc), lang)
    lines.append(t(lang, "HIST_COVERAGE", points=str(len(rows)), since=since))
    return "\n".join(lines)
