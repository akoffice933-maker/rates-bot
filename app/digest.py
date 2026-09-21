"""Дайджест дня: ежедневная сводка курсов в подписанные чаты.

Время отправки — аргентинское (America/Argentina/Buenos_Aires, UTC−3).
Воркер проверяет подписки раз в ALERT_POLL_SECONDS; срабатывание — один раз
в день при первом совпадении текущего часа с часом подписки.
Дельты считаются против снимка предыдущего дня (таблица digest_history).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from . import formatting as fmt
from .i18n import t
from .service import Snapshot
from .storage import BotStorage

log = logging.getLogger(__name__)

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DIGEST_HOURS = (9, 12, 18, 21)  # пресеты времени (час, AR)

_WEEKDAYS = {
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "ru": ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
}


class Sender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...


def snapshot_data(snap: Snapshot) -> dict:
    """Ключевые значения дня для истории (сравнение дельт в дайджестах)."""
    return {
        "oficial_sell": snap.oficial.sell if snap.oficial else None,
        "blue_buy": snap.blue.buy if snap.blue else None,
        "blue_sell": snap.blue.sell if snap.blue else None,
        "mep_sell": snap.mep.sell if snap.mep else None,
        "ccl_sell": snap.ccl.sell if snap.ccl else None,
        "usdt_median_ask": snap.usdt.median_ask if snap.usdt else None,
        "usdt_median_bid": snap.usdt.median_bid if snap.usdt else None,
        "spread_sell": snap.spread_sell_pct(),
        "spread_buy": snap.spread_buy_pct(),
    }


def _delta_suffix(key: str, current: float | None, prev: dict | None, lang: str) -> str:
    if not prev:
        return ""
    old = prev.get(key)
    if not current or not old:
        return ""
    pct = (current - old) / old * 100
    arrow = "↑" if pct >= 0 else "↓"
    return f" ({arrow} {fmt.pct(pct, lang, 2)})"


def digest_text(snap: Snapshot, prev: dict | None, lang: str, now_ar: datetime) -> str:
    weekday = _WEEKDAYS.get(lang, _WEEKDAYS["es"])[now_ar.weekday()]
    date_str = now_ar.strftime("%d.%m.%Y")

    lines = [f"<b>{t(lang, 'DIGEST_TITLE', date=f'{weekday}, {date_str}')}</b>", ""]

    lines.append(f"<b>{t(lang, 'DIGEST_DOLLAR')}</b>")
    if snap.oficial:
        lines.append(
            f"🇦🇷 {t(lang, 'ROW_OFICIAL')}: {fmt.money(snap.oficial.buy, lang)} / "
            f"{fmt.money(snap.oficial.sell, lang)}"
            f"{_delta_suffix('oficial_sell', snap.oficial.sell, prev, lang)}"
        )
    if snap.blue:
        lines.append(
            f"🔵 {t(lang, 'ROW_BLUE')}: {fmt.money(snap.blue.buy, lang)} / "
            f"{fmt.money(snap.blue.sell, lang)}"
            f"{_delta_suffix('blue_sell', snap.blue.sell, prev, lang)}"
        )
    if snap.mep:
        lines.append(f"📈 {t(lang, 'ROW_MEP')}: {fmt.money(snap.mep.buy, lang)} / {fmt.money(snap.mep.sell, lang)}")
    if snap.ccl:
        lines.append(f"🏦 {t(lang, 'ROW_CCL')}: {fmt.money(snap.ccl.buy, lang)} / {fmt.money(snap.ccl.sell, lang)}")

    if snap.usdt:
        lines.append("")
        lines.append(f"<b>{t(lang, 'SPREAD_USDT_MEDIAN')}</b>")
        if snap.usdt.median_ask is not None:
            best = snap.usdt.asks[0] if snap.usdt.asks else None
            extra = (
                f" · {t(lang, 'DIGEST_BEST')}: {best.name} ${fmt.money(best.ask, lang)}"
                if best
                else ""
            )
            lines.append(
                f"• {t(lang, 'DIGEST_USDT_BUY')}: ${fmt.money(snap.usdt.median_ask, lang)}"
                f"{extra}{_delta_suffix('usdt_median_ask', snap.usdt.median_ask, prev, lang)}"
            )
        if snap.usdt.median_bid is not None:
            best = snap.usdt.bids[0] if snap.usdt.bids else None
            extra = (
                f" · {t(lang, 'DIGEST_BEST')}: {best.name} ${fmt.money(best.bid, lang)}"
                if best
                else ""
            )
            lines.append(
                f"• {t(lang, 'DIGEST_USDT_SELL')}: ${fmt.money(snap.usdt.median_bid, lang)}"
                f"{extra}{_delta_suffix('usdt_median_bid', snap.usdt.median_bid, prev, lang)}"
            )

        ss, sb = snap.spread_sell_pct(), snap.spread_buy_pct()
        if ss is not None or sb is not None:
            lines.append("")
            lines.append(f"<b>{t(lang, 'SPREAD_TITLE')}</b>")
            if ss is not None:
                lines.append(t(lang, "SPREAD_SELL_RESULT", pct=fmt.pct(ss, lang)))
            if sb is not None:
                lines.append(t(lang, "SPREAD_BUY_RESULT", pct=fmt.pct(sb, lang)))

    lines.append("")
    lines.append(t(lang, "DIGEST_FOOTER"))
    return "\n".join(lines)


class DigestManager:
    def __init__(self, storage: BotStorage) -> None:
        self._storage = storage

    async def check(self, bot: Sender, snap: Snapshot, now: datetime | None = None) -> int:
        """Отправить дайджесты, чей час наступил; вернуть число отправок."""
        now_utc = now or datetime.now(timezone.utc)
        now_ar = now_utc.astimezone(AR_TZ)
        today = now_ar.date().isoformat()
        hour = now_ar.hour

        if self._storage.get_digest_snapshot(today) is None:
            self._storage.save_digest_snapshot(today, snapshot_data(snap))
        prev = self._storage.last_digest_snapshot_before(today)

        sent = 0
        for chat_id in self._storage.digest_due(hour, today):
            lang = self._storage.get_lang(chat_id)
            try:
                await bot.send_message(chat_id, digest_text(snap, prev, lang, now_ar))
            except Exception:
                log.exception("дайджест не доставлен в чат %s", chat_id)
            finally:
                # даже при ошибке доставки помечаем день — не спамим ретраями
                self._storage.digest_mark_sent(chat_id, today)
            sent += 1
        return sent
