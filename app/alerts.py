"""Алерты: спред USDT vs Blue и абсолютные курсы (blue, медианы USDT).

Метрики (METRICS):
  kind=spread — проценты (выгода продажи USDT, переплата за покупку);
  kind=abs    — ARS: blue compra/venta, медианы ask/bid USDT.

Направление (для abs): above — уведомить при значении ⩾ порога,
below — при значении ⩽ порога. У спред-метрик всегда above.

Логика edge-triggered с защитой от «дребезга»:
  * уведомление при ПЕРЕСЕЧЕНИИ порога (снизу вверх для above / сверху вниз для below);
  * пока условие выполняется — повторных уведомлений нет;
  * перевзвод после выхода за порог с запасом (гистерезис):
      spread — фиксированный, п.п.; abs — ~0,1 % от порога (мин. 0,5 ARS);
  * повторное срабатывание не чаще раза в cooldown; пересечение в cooldown
    остаётся «взведённым» и сработает после его истечения.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from . import formatting as fmt
from .i18n import t
from .service import Snapshot
from .storage import Alert, BotStorage

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricSpec:
    kind: str                                  # spread | abs
    name_key: str                              # i18n-ключ названия
    eval: Callable[[Snapshot], float | None]   # значение метрики по снапшоту
    hysteresis_min: float = 0.5                # минимум гистерезиса; для USD-пар — 0.001


def _uu_best_bid(s: Snapshot) -> float | None:
    """Лучший курс продажи USDT за USD — безнал (CriptoYa USDT/USD, лучший bid)."""
    m = s.usdt_usd
    return m.bids[0].bid if m and m.bids else None


def _uu_best_ask(s: Snapshot) -> float | None:
    """Лучший курс покупки USDT за USD — безнал (лучший ask)."""
    m = s.usdt_usd
    return m.asks[0].ask if m and m.asks else None


def _uu_cash_sell(s: Snapshot) -> float | None:
    """Продажа USDT за наличный USD (расчёт): лучший bid USDT/ARS ÷ blue venta."""
    if s.usdt and s.usdt.bids and s.blue and s.blue.sell:
        return s.usdt.bids[0].bid / s.blue.sell
    return None


def _uu_cash_buy(s: Snapshot) -> float | None:
    """Покупка USDT за наличный USD (расчёт): лучший ask USDT/ARS ÷ blue compra."""
    if s.usdt and s.usdt.asks and s.blue and s.blue.buy:
        return s.usdt.asks[0].ask / s.blue.buy
    return None


METRICS: dict[str, MetricSpec] = {
    "spread_sell": MetricSpec("spread", "ALERT_METRIC_SELL", lambda s: s.spread_sell_pct()),
    "spread_buy": MetricSpec("spread", "ALERT_METRIC_BUY", lambda s: s.spread_buy_pct()),
    "blue_buyusd": MetricSpec("abs", "M_BLUE_BUYUSD", lambda s: s.blue.sell if s.blue else None),
    "blue_sellusd": MetricSpec("abs", "M_BLUE_SELLUSD", lambda s: s.blue.buy if s.blue else None),
    "usdt_buy": MetricSpec("abs", "M_USDT_BUY", lambda s: s.usdt.median_ask if s.usdt else None),
    "usdt_sell": MetricSpec("abs", "M_USDT_SELL", lambda s: s.usdt.median_bid if s.usdt else None),
    # USDT ⇄ USD (арбитражный цикл: продать дорого → купить обратно дёшево)
    "usdtusd_sell": MetricSpec("abs", "M_USDTUSD_SELL", _uu_best_bid, 0.001),
    "usdtusd_buy": MetricSpec("abs", "M_USDTUSD_BUY", _uu_best_ask, 0.001),
    "usdtusd_cash_sell": MetricSpec("abs", "M_USDTUSD_CASH_SELL", _uu_cash_sell, 0.001),
    "usdtusd_cash_buy": MetricSpec("abs", "M_USDTUSD_CASH_BUY", _uu_cash_buy, 0.001),
}
METRICS_ORDER = tuple(METRICS)  # порядок кнопок = порядок объявления


class Sender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...


class AlertManager:
    def __init__(
        self,
        storage: BotStorage,
        cooldown_minutes: int = 30,
        hysteresis_pct: float = 0.2,
    ) -> None:
        self._storage = storage
        self._cooldown = timedelta(minutes=cooldown_minutes)
        self._hysteresis_pct = hysteresis_pct

    def _hysteresis(self, alert: Alert) -> float:
        spec = METRICS[alert.metric]
        if spec.kind == "spread":
            return self._hysteresis_pct
        # ~0,1 % от порога; минимум зависит от метрики (ARS — 0,5; USD-пары — 0,001)
        return max(alert.threshold * 0.001, spec.hysteresis_min)

    async def check(self, snap: Snapshot, bot: Sender | None = None) -> list[str]:
        """Проверить все активные алерты по снапшоту; вернуть отправленные тексты."""
        now = datetime.now(timezone.utc)
        fired: list[str] = []

        for alert in self._storage.list_alerts():
            spec = METRICS.get(alert.metric)
            if spec is None:
                continue
            value = spec.eval(snap)
            if value is None:
                continue

            hyst = self._hysteresis(alert)
            if alert.direction == "below":
                condition_met = value <= alert.threshold
                rearm = value > alert.threshold + hyst
            else:
                condition_met = value >= alert.threshold
                rearm = value < alert.threshold - hyst

            if condition_met:
                if alert.active:
                    continue  # условие уже выполнялось — уже уведомляли
                if alert.last_fired_at and (now - alert.last_fired_at) < self._cooldown:
                    continue  # cooldown: остаёмся взведённым, попробуем в следующем цикле

                lang = self._storage.get_lang(alert.chat_id)
                text = fired_text(alert, value, snap, lang)
                if bot is not None:
                    try:
                        await bot.send_message(alert.chat_id, text)
                    except Exception:
                        # чат недоступен (заблокирован бот и т.п.) — считаем потреблённым,
                        # чтобы не спамить ошибками каждый цикл
                        log.exception("не доставлен алерт %s в чат %s", alert.id, alert.chat_id)
                        self._storage.mark_fired(alert.id)
                        continue
                self._storage.mark_fired(alert.id)
                fired.append(text)

            elif alert.active and rearm:
                # выход за порог с запасом — взводим алерт заново
                self._storage.set_active(alert.id, False)

        return fired


def fired_text(alert: Alert, value: float, snap: Snapshot, lang: str) -> str:
    spec = METRICS[alert.metric]
    name = t(lang, spec.name_key)
    if spec.kind == "spread":
        title_key = (
            "ALERT_FIRED_SELL_TITLE" if alert.metric == "spread_sell" else "ALERT_FIRED_BUY_TITLE"
        )
        title = t(lang, title_key, pct=fmt.pct(value, lang))
        th = fmt.pct(alert.threshold, lang, 1)
        context = _spread_context(alert, snap, lang)
    else:
        dec = 4 if alert.metric.startswith("usdtusd") else 2
        title = t(lang, "ALERT_FIRED_ABS_TITLE", metric=name, value=f"${fmt.money(value, lang, dec)}")
        op = "⩾" if alert.direction == "above" else "⩽"
        th = f"{op} ${fmt.money(alert.threshold, lang, dec)}"
        if alert.metric.startswith("usdtusd"):
            context = _usdtusd_context(snap, lang)
        else:
            context = _abs_context(snap, lang)
    lines = [
        f"<b>{title}</b>",
        t(lang, "ALERT_THRESHOLD_NOTE", th=th),
        "",
        *context,
        "",
        t(lang, "ALERT_FIRED_FOOTER"),
    ]
    return "\n".join(lines)


def _spread_context(alert: Alert, snap: Snapshot, lang: str) -> list[str]:
    if alert.metric == "spread_sell":
        return [
            f"• {t(lang, 'SPREAD_USDT_MEDIAN')}: ${fmt.money(snap.usdt.median_bid, lang)}",
            f"• {t(lang, 'SPREAD_BLUE_BUY')}: ${fmt.money(snap.blue.buy, lang)}",
        ]
    return [
        f"• {t(lang, 'SPREAD_USDT_MEDIAN')}: ${fmt.money(snap.usdt.median_ask, lang)}",
        f"• {t(lang, 'SPREAD_BLUE_SELL')}: ${fmt.money(snap.blue.sell, lang)}",
    ]


def _abs_context(snap: Snapshot, lang: str) -> list[str]:
    lines: list[str] = []
    if snap.blue:
        lines.append(f"• {t(lang, 'SPREAD_BLUE_BUY')}: ${fmt.money(snap.blue.buy, lang)}")
        lines.append(f"• {t(lang, 'SPREAD_BLUE_SELL')}: ${fmt.money(snap.blue.sell, lang)}")
    if snap.usdt:
        if snap.usdt.median_ask is not None:
            lines.append(f"• {t(lang, 'M_USDT_BUY')}: ${fmt.money(snap.usdt.median_ask, lang)}")
        if snap.usdt.median_bid is not None:
            lines.append(f"• {t(lang, 'M_USDT_SELL')}: ${fmt.money(snap.usdt.median_bid, lang)}")
    return lines


def _usdtusd_context(snap: Snapshot, lang: str) -> list[str]:
    """Контекст для алертов USDT⇄USD: обе стороны безнала + наличный расчёт."""
    lines: list[str] = []
    m = snap.usdt_usd
    if m:
        if m.asks:
            q = m.asks[0]
            lines.append(f"• {t(lang, 'USDTUSD_CTX_BUY')}: ${fmt.money(q.ask, lang, 4)} — {q.name}")
        if m.bids:
            q = m.bids[0]
            lines.append(f"• {t(lang, 'USDTUSD_CTX_SELL')}: ${fmt.money(q.bid, lang, 4)} — {q.name}")
    if snap.usdt and snap.blue:
        if snap.usdt.asks and snap.blue.buy:
            lines.append(
                f"• {t(lang, 'USDTUSD_CTX_CASH_BUY')}: "
                f"${fmt.money(snap.usdt.asks[0].ask / snap.blue.buy, lang, 4)}"
            )
        if snap.usdt.bids and snap.blue.sell:
            lines.append(
                f"• {t(lang, 'USDTUSD_CTX_CASH_SELL')}: "
                f"${fmt.money(snap.usdt.bids[0].bid / snap.blue.sell, lang, 4)}"
            )
    return lines or _abs_context(snap, lang)


async def alert_worker(
    bot: Sender, service, manager: AlertManager, digest=None, interval_seconds: int = 60,
    history=None, history_interval_seconds: int = 900,
) -> None:
    """Фоновый цикл: тёплый кэш + запись истории + алерты + дайджесты."""
    while True:
        try:
            snap = await service.get_snapshot_full()
            if history is not None:
                try:
                    history.maybe_record(snap, history_interval_seconds)
                except Exception:
                    log.exception("не записана история курсов")
            await manager.check(snap, bot=bot)
            if digest is not None:
                await digest.check(bot, snap)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("ошибка в цикле проверки алертов")
        await asyncio.sleep(interval_seconds)
