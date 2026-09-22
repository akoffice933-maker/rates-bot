"""Форматирование чисел и времени.

Числа: es-AR -> $1.503,50 ; ru-RU -> $1 503,50.
Время: хранение UTC, отображение America/Argentina/Buenos_Aires (UTC−3).
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .i18n import t

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def money(x: float | None, lang: str, decimals: int = 2) -> str:
    if x is None:
        return "—"
    s = f"{x:,.{decimals}f}"  # 1,503.50
    if lang == "es":
        return s.replace(",", "#").replace(".", ",").replace("#", ".")
    if lang == "en":
        return s
    return s.replace(",", " ").replace(".", ",")


def pct(x: float | None, lang: str, decimals: int = 2) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else "-"
    return f"{sign}{money(abs(x), lang, decimals)} %"


def per_thousand(price: float | None, lang: str, decimals: int = 4) -> str:
    """Обратная котировка: сколько базовой валюты (USD/USDT) дают за 1.000 ARS."""
    if price is None or price <= 0:
        return "—"
    return money(1000.0 / price, lang, decimals)


def ts_local(dt: datetime, lang: str) -> str:
    local = dt.astimezone(AR_TZ)
    hours = int(local.utcoffset().total_seconds() // 3600)  # сейчас -3
    sign = "+" if hours >= 0 else "-"
    return local.strftime("%d.%m %H:%M") + f" (UTC{sign}{abs(hours)})"


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def ago(dt: datetime, lang: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return t(lang, "JUST_NOW")
    minutes = round(seconds / 60)
    if minutes < 60:
        if lang == "ru":
            word = plural_ru(minutes, "минуту", "минуты", "минут")
            return f"{minutes} {word} назад"
        if lang == "en":
            return f"{minutes} min ago"
        return f"hace {minutes} min"
    hours, mins = divmod(minutes, 60)
    if lang == "ru":
        h_word = plural_ru(hours, "час", "часа", "часов")
        core = f"{hours} {h_word}"
        if mins:
            core += f" {mins} мин"
        return core + " назад"
    if lang == "en":
        return f"{hours} h {mins} min ago" if mins else f"{hours} h ago"
    return f"hace {hours} h {mins} min" if mins else f"hace {hours} h"
