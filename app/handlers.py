"""Хендлеры команд и callback-кнопок."""
from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from . import config, formatting as fmt, render
from .alerts import METRICS
from .i18n import t
from .keyboards import (
    ALERT_PRESETS,
    alert_categories_kb,
    alert_direction_kb,
    alert_kb,
    alert_threshold_label,
    alert_value_kb,
    bc_kb,
    bc_screen_kb,
    digest_kb,
    guide_kb,
    lang_kb,
    scenario_kb,
    links_kb,
    main_menu,
    screen_kb,
    uu_kb,
    cmp_kb,
)
from .service import RatesService
from .digest import DIGEST_HOURS
from .p2p import BinanceP2PService
from .guide import SCENARIOS, guide_menu_text, guide_text
from .bestchange import BestChangeService
from .sources.bestchange import DIRECTIONS
from .storage import Alert, BotStorage

router = Router()

_ACTIONS = ("rates", "usdt", "spread")
_SWAPPABLE = ("rates", "usdt")
_DIRECTIONS = ("above", "below")
_SPREAD_MIN, _SPREAD_MAX = 0.5, 20.0
_ABS_MIN, _ABS_MAX = 100.0, 1_000_000.0
_UU_MIN, _UU_MAX = 0.8, 1.5          # пороги USDT/USD, USD за 1 USDT


class AlertCustom(StatesGroup):
    """FSM: ждём от пользователя порог/значение (после выбора метрики)."""

    waiting_threshold = State()


# ---------- вспомогательные ----------

async def _screen_text(
    service: RatesService,
    action: str,
    lang: str,
    direction: str,
    volume: int | None = None,
    force: bool = False,
) -> str | None:
    use_volume = volume if action == "usdt" else None
    snap = await service.get_snapshot(volume=use_volume, force=force)
    return render.screen(action, snap, lang, inverse=(direction == "inverse"), volume=use_volume)


async def _send_screen(
    message: Message, service: RatesService, action: str, lang: str, direction: str,
    volume: int | None = None,
) -> None:
    text = await _screen_text(service, action, lang, direction, volume)
    if text is None:
        await message.answer(t(lang, "NO_DATA"))
        return
    await message.answer(text, reply_markup=screen_kb(lang, action, direction, volume))


async def _edit(cb: CallbackQuery, text: str, kb) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def _is_uu(metric: str) -> bool:
    """Метрика пары USDT/USD (порог ~1 USD, а не ~1500 ARS)."""
    return metric.startswith("usdtusd")


def _abs_presets(current: float, direction: str, step: float = 50.0) -> list[float]:
    """Пресеты значений вокруг текущего курса: для above — вверх, для below — вниз.

    Шаг зависит от метрики: ARS-курсы — 50, USD-пары USDT/USD — 0,01.
    """
    if direction == "above":
        base = math.ceil(current / step) * step
        return [base, base + step, base + 2 * step]
    base = math.floor(current / step) * step
    return [base, base - step, base - 2 * step]


# ---------- экраны курсов ----------

@router.message(CommandStart())
async def cmd_start(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await message.answer(t(lang, "WELCOME"), reply_markup=main_menu(lang))


@router.message(Command("help"))
async def cmd_help(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await message.answer(t(lang, "HELP"))


@router.message(Command("rates"))
async def cmd_rates(message: Message, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    direction = storage.get_direction(message.chat.id)
    await _send_screen(message, service, "rates", lang, direction)


@router.message(Command("usdt"))
async def cmd_usdt(message: Message, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    direction = storage.get_direction(message.chat.id)
    volume = storage.get_volume(message.chat.id, config.USDT_VOLUME_DEFAULT)
    await _send_screen(message, service, "usdt", lang, direction, volume)


@router.message(Command("usdtusd"))
async def cmd_usdtusd(message: Message, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    view = await service.get_usdtusd_view()
    text = render.usdtusd_text(view, lang)
    if text is None:
        await message.answer(t(lang, "NO_DATA"))
        return
    await message.answer(text, reply_markup=uu_kb(lang))


@router.callback_query(F.data == "uu:scr")
async def cb_uu_scr(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    view = await service.get_usdtusd_view()
    text = render.usdtusd_text(view, lang) or t(lang, "NO_DATA")
    await _edit(cb, text, uu_kb(lang))
    await cb.answer()


@router.callback_query(F.data == "uu:rfsh")
async def cb_uu_rfsh(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    view = await service.get_usdtusd_view(force=True)
    text = render.usdtusd_text(view, lang)
    if text is None:
        await cb.answer(t(lang, "NO_DATA"), show_alert=True)
        return
    await _edit(cb, text, uu_kb(lang))
    await cb.answer("✅")


async def _compare_screen(message: Message, service: RatesService,
                         bestchange: BestChangeService, p2p: BinanceP2PService,
                         storage: BotStorage, force: bool = False) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    snap = await service.get_snapshot(force=force)
    bc_sell = await bestchange.get("usdt_mp", force=force)
    bc_buy = await bestchange.get("mp_usdt", force=force)
    p2p_res = await p2p.get(force=force)
    text = render.compare_text(snap, bc_sell, bc_buy, p2p_res, lang)
    if text is None:
        await message.answer(t(lang, "NO_DATA"))
        return
    await message.answer(text, reply_markup=cmp_kb(lang))


@router.message(Command("compare"))
async def cmd_compare(message: Message, service: RatesService, bestchange: BestChangeService,
                      p2p: BinanceP2PService, storage: BotStorage) -> None:
    await _compare_screen(message, service, bestchange, p2p, storage)


@router.callback_query(F.data == "cmp:scr")
async def cb_cmp_scr(cb: CallbackQuery, service: RatesService, bestchange: BestChangeService,
                     p2p: BinanceP2PService, storage: BotStorage) -> None:
    await _compare_screen(cb.message, service, bestchange, p2p, storage)
    await cb.answer()


@router.callback_query(F.data == "cmp:rfsh")
async def cb_cmp_rfsh(cb: CallbackQuery, service: RatesService, bestchange: BestChangeService,
                      p2p: BinanceP2PService, storage: BotStorage) -> None:
    await _compare_screen(cb.message, service, bestchange, p2p, storage, force=True)
    await cb.answer("✅")


@router.message(Command("spread"))
async def cmd_spread(message: Message, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await _send_screen(message, service, "spread", lang, "direct")


@router.message(Command("lang"))
async def cmd_lang(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await message.answer(t(lang, "LANG_PROMPT"), reply_markup=lang_kb(lang))


# ---------- алерты ----------

def _alert_menu(lang: str, alerts: list[Alert]) -> tuple[str, object]:
    if alerts:
        items = "\n".join(
            t(
                lang,
                "ALERT_ITEM",
                metric=t(lang, METRICS[a.metric].name_key),
                op="",
                th=alert_threshold_label(a, lang),
            )
            for a in alerts
            if a.metric in METRICS
        )
        body = f"{t(lang, 'ALERT_LIST')}\n{items}"
    else:
        body = t(lang, "ALERT_EMPTY")
    text = (
        f"<b>{t(lang, 'ALERT_TITLE')}</b>\n\n{body}\n\n"
        f"{t(lang, 'ALERT_HOW', poll=config.ALERT_POLL_SECONDS, cooldown=config.ALERT_COOLDOWN_MINUTES)}"
    )
    return text, alert_kb(lang, alerts)


@router.message(Command("alert"))
async def cmd_alert(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    text, kb = _alert_menu(lang, storage.list_alerts(message.chat.id))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "al:menu")
async def cb_alert_menu(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    text, kb = _alert_menu(lang, storage.list_alerts(cb.message.chat.id))
    await _edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "al:add")
async def cb_alert_add(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    snap = await service.get_snapshot_full()
    lines = [f"<b>{t(lang, 'ALERT_METRIC_PROMPT')}</b>", ""]
    for metric, spec in METRICS.items():
        value = spec.eval(snap)
        if spec.kind == "spread":
            shown = fmt.pct(value, lang)
        else:
            dec = 4 if _is_uu(metric) else 2
            shown = f"${fmt.money(value, lang, dec)}" if value is not None else "—"
        lines.append(f"{t(lang, spec.name_key)}: {shown}")
    await _edit(cb, "\n".join(lines), alert_categories_kb(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("al:cat:"))
async def cb_alert_category(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    metric = cb.data.split(":", 2)[2]
    spec = METRICS.get(metric)
    if spec is None:
        await cb.answer()
        return
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    snap = await service.get_snapshot_full()
    current = spec.eval(snap)

    if spec.kind == "spread":
        # сразу экран порогов в процентах
        cur_shown = fmt.pct(current, lang) if current is not None else "—"
        text = f"<b>{t(lang, 'ALERT_THRESHOLD_PROMPT')}</b>\n\n{t(lang, spec.name_key)}: {cur_shown}"
        presets = [(fmt.pct(v, lang, 0), v) for v in ALERT_PRESETS]
        kb = alert_value_kb(lang, presets, metric, "")
    else:
        # экран направления (выше/ниже)
        dec = 4 if _is_uu(metric) else 2
        cur_shown = f"${fmt.money(current, lang, dec)}" if current is not None else "—"
        text = f"<b>{t(lang, 'ALERT_DIR_PROMPT')}</b>\n\n{t(lang, spec.name_key)}: {cur_shown}"
        kb = alert_direction_kb(lang, metric)
    await _edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data.startswith("al:dir:"))
async def cb_alert_direction(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    # al:dir:<metric>:<direction>
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, _, metric, direction = parts
    spec = METRICS.get(metric)
    if spec is None or spec.kind != "abs" or direction not in _DIRECTIONS:
        await cb.answer()
        return
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    snap = await service.get_snapshot_full()
    current = spec.eval(snap)

    op = "⩾" if direction == "above" else "⩽"
    if current is None:
        await cb.answer(t(lang, "NO_DATA"), show_alert=True)
        return
    dec = 4 if _is_uu(metric) else 2
    step = 0.01 if _is_uu(metric) else 50.0
    text = (
        f"<b>{t(lang, 'ALERT_VALUE_PROMPT')}</b>\n\n"
        f"{t(lang, spec.name_key)}: ${fmt.money(current, lang, dec)}"
    )
    presets = [
        (f"{op} ${fmt.money(v, lang, dec)}", v) for v in _abs_presets(current, direction, step)
    ]
    await _edit(cb, text, alert_value_kb(lang, presets, metric, direction))
    await cb.answer()


@router.callback_query(F.data.startswith("al:pre:"))
async def cb_alert_preset(cb: CallbackQuery, storage: BotStorage) -> None:
    # al:pre:<metric>:<direction>:<value>  (direction может быть пустым для спреда)
    parts = cb.data.split(":")
    if len(parts) != 5:
        await cb.answer()
        return
    _, _, metric, direction, raw = parts
    spec = METRICS.get(metric)
    if spec is None:
        await cb.answer()
        return
    try:
        value = float(raw)
    except ValueError:
        await cb.answer()
        return
    direction = direction if spec.kind == "abs" else "above"

    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    added = storage.add_alert(
        chat_id, metric, spec.kind, round(value, 4 if _is_uu(metric) else 2), direction
    )
    text, kb = _alert_menu(lang, storage.list_alerts(chat_id))
    await _edit(cb, text, kb)
    await cb.answer("✅" if added else "⚠️")


@router.callback_query(F.data.startswith("al:cust:"))
async def cb_alert_custom(cb: CallbackQuery, state: FSMContext, storage: BotStorage) -> None:
    # al:cust:<metric>:<direction>
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, _, metric, direction = parts
    spec = METRICS.get(metric)
    if spec is None:
        await cb.answer()
        return
    direction = direction if spec.kind == "abs" else "above"
    await state.set_state(AlertCustom.waiting_threshold)
    await state.update_data(metric=metric, direction=direction)
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    if spec.kind == "spread":
        prompt = t(lang, "ALERT_CUSTOM_PROMPT")
    elif _is_uu(metric):
        prompt = t(lang, "ALERT_CUSTOM_PROMPT_USD")
    else:
        prompt = t(lang, "ALERT_CUSTOM_PROMPT_ABS")
    await cb.message.answer(prompt)
    await cb.answer()


@router.message(StateFilter(AlertCustom.waiting_threshold), F.text, ~F.text.startswith("/"))
async def alert_custom_input(message: Message, state: FSMContext, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    raw = message.text.strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        await message.answer(t(lang, "ALERT_CUSTOM_BAD"))
        return

    data = await state.get_data()
    metric = data.get("metric")
    direction = data.get("direction", "above")
    spec = METRICS.get(metric)
    if spec is None:
        await state.clear()
        await message.answer(t(lang, "NO_DATA"))
        return

    if spec.kind == "spread":
        ok = _SPREAD_MIN <= value <= _SPREAD_MAX
        bad_key = "ALERT_CUSTOM_BAD"
    elif _is_uu(metric):
        ok = _UU_MIN <= value <= _UU_MAX
        bad_key = "ALERT_CUSTOM_BAD_USD"
    else:
        ok = _ABS_MIN <= value <= _ABS_MAX
        bad_key = "ALERT_CUSTOM_BAD_ABS"
    if not ok:
        await message.answer(t(lang, bad_key))
        return

    added = storage.add_alert(
        message.chat.id, metric, spec.kind, round(value, 4 if _is_uu(metric) else 1), direction
    )
    await state.clear()

    await message.answer(t(lang, "ALERT_ADDED" if added else "ALERT_EXISTS"))
    text, kb = _alert_menu(lang, storage.list_alerts(message.chat.id))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("al:del:"))
async def cb_alert_delete(cb: CallbackQuery, storage: BotStorage) -> None:
    try:
        alert_id = int(cb.data.split(":", 2)[2])
    except ValueError:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    removed = storage.remove_alert(alert_id, chat_id)  # только свой алерт
    text, kb = _alert_menu(lang, storage.list_alerts(chat_id))
    await _edit(cb, text, kb)
    await cb.answer("🗑" if removed else "⚠️")


@router.callback_query(F.data.startswith("al:d:"))
async def cb_alert_delete_legacy(cb: CallbackQuery, storage: BotStorage) -> None:
    """Совместимость со старыми сообщениями (кнопки al:d:<id>)."""
    try:
        alert_id = int(cb.data.split(":", 2)[2])
    except ValueError:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    storage.remove_alert(alert_id, chat_id)
    text, kb = _alert_menu(lang, storage.list_alerts(chat_id))
    await _edit(cb, text, kb)
    await cb.answer("🗑")


# ---------- объём расчёта USDT ----------

@router.callback_query(F.data.startswith("vol:"))
async def cb_volume(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    try:
        volume = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer()
        return
    if not (1 <= volume <= 1_000_000):
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    direction = storage.get_direction(chat_id)
    storage.set_volume(chat_id, volume, lang)

    text = await _screen_text(service, "usdt", lang, direction, volume)
    if text is None:
        text = t(lang, "NO_DATA")
    await _edit(cb, text, screen_kb(lang, "usdt", direction, volume))
    await cb.answer("✅")


# ---------- остальные callback ----------

@router.callback_query(F.data == "menu:main")
async def cb_menu(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    await _edit(cb, t(lang, "WELCOME"), main_menu(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("scr:"))
async def cb_screen(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    action = cb.data.split(":", 1)[1]
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    if action == "lang":
        await _edit(cb, t(lang, "LANG_PROMPT"), lang_kb(lang))
        await cb.answer()
        return
    if action == "links":
        await _edit(cb, render.links_text(lang), links_kb(lang))
        await cb.answer()
        return
    if action not in _ACTIONS:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    direction = storage.get_direction(chat_id)
    volume = storage.get_volume(chat_id, config.USDT_VOLUME_DEFAULT) if action == "usdt" else None
    text = await _screen_text(service, action, lang, direction, volume)
    if text is None:
        await _edit(cb, t(lang, "NO_DATA"), screen_kb(lang, action, direction, volume))
    else:
        await _edit(cb, text, screen_kb(lang, action, direction, volume))
    await cb.answer()


@router.callback_query(F.data.startswith("rfsh:"))
async def cb_refresh(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    action = cb.data.split(":", 1)[1]
    if action not in _ACTIONS:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    direction = storage.get_direction(chat_id)
    volume = storage.get_volume(chat_id, config.USDT_VOLUME_DEFAULT) if action == "usdt" else None
    text = await _screen_text(service, action, lang, direction, volume, force=True)
    if text is None:
        await cb.answer(t(lang, "NO_DATA"), show_alert=True)
        return
    await _edit(cb, text, screen_kb(lang, action, direction, volume))
    await cb.answer("✅")


@router.callback_query(F.data.startswith("swap:"))
async def cb_swap(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    """Инверсия пары: USD/ARS ↔ ARS/USD, USDT/ARS ↔ ARS/USDT."""
    action = cb.data.split(":", 1)[1]
    if action not in _SWAPPABLE:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    direction = storage.get_direction(chat_id)
    new_direction = "inverse" if direction == "direct" else "direct"
    storage.set_direction(chat_id, new_direction, lang)

    volume = storage.get_volume(chat_id, config.USDT_VOLUME_DEFAULT) if action == "usdt" else None
    text = await _screen_text(service, action, lang, new_direction, volume)
    if text is None:
        text = t(lang, "NO_DATA")
    await _edit(cb, text, screen_kb(lang, action, new_direction, volume))
    await cb.answer()


@router.callback_query(F.data.startswith("setlang:"))
async def cb_setlang(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = cb.data.split(":", 1)[1]
    if lang not in ("es", "ru"):
        await cb.answer()
        return
    storage.set_lang(cb.message.chat.id, lang)
    await _edit(cb, f"{t(lang, 'LANG_SET')}\n\n{t(lang, 'WELCOME')}", main_menu(lang))
    await cb.answer()


# ---------- Binance P2P (прямые объявления) ----------

async def _p2p_screen(cb_or_msg, service: RatesService, p2p: BinanceP2PService, storage: BotStorage, edit: bool):
    chat_id = cb_or_msg.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    result = await p2p.get()
    snap = await service.get_snapshot()
    text = render.p2p_text(result, snap, lang) or t(lang, "NO_DATA")
    kb = screen_kb(lang, "p2p")
    if edit:
        await _edit(cb_or_msg, text, kb)
    else:
        await cb_or_msg.answer(text, reply_markup=kb)


@router.message(Command("p2p"))
async def cmd_p2p(message: Message, service: RatesService, p2p: BinanceP2PService, storage: BotStorage) -> None:
    await _p2p_screen(message, service, p2p, storage, edit=False)


@router.callback_query(F.data == "p2p:scr")
async def cb_p2p_scr(cb: CallbackQuery, service: RatesService, p2p: BinanceP2PService, storage: BotStorage) -> None:
    await _p2p_screen(cb.message, service, p2p, storage, edit=True)
    await cb.answer()


@router.callback_query(F.data == "p2p:rfsh")
async def cb_p2p_rfsh(cb: CallbackQuery, service: RatesService, p2p: BinanceP2PService, storage: BotStorage) -> None:
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    result = await p2p.get(force=True)
    snap = await service.get_snapshot()
    text = render.p2p_text(result, snap, lang) or t(lang, "NO_DATA")
    await _edit(cb, text, screen_kb(lang, "p2p"))
    await cb.answer("✅")


# ---------- дайджест дня ----------

def _digest_menu(lang: str, chat_id: int, storage: BotStorage) -> tuple[str, object]:
    hour = storage.digest_sub(chat_id)
    if hour is None:
        text = (
            f"<b>{t(lang, 'DIGEST_SUB_TITLE')}</b>\n\n"
            f"{t(lang, 'DIGEST_STATUS_OFF')}\n\n{t(lang, 'DIGEST_HOUR_PROMPT')}"
        )
        return text, digest_kb(lang, None)
    text = (
        f"<b>{t(lang, 'DIGEST_SUB_TITLE')}</b>\n\n"
        f"{t(lang, 'DIGEST_STATUS_ON', hour=hour)}"
    )
    return text, digest_kb(lang, hour)


@router.message(Command("digest"))
async def cmd_digest(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    text, kb = _digest_menu(lang, message.chat.id, storage)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "dg:menu")
async def cb_digest_menu(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    text, kb = _digest_menu(lang, cb.message.chat.id, storage)
    await _edit(cb, text, kb)
    await cb.answer()


@router.callback_query(F.data == "dg:pick")
async def cb_digest_pick(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    text = f"<b>{t(lang, 'DIGEST_SUB_TITLE')}</b>\n\n{t(lang, 'DIGEST_HOUR_PROMPT')}"
    await _edit(cb, text, digest_kb(lang, None))
    await cb.answer()


@router.callback_query(F.data.startswith("dg:sub:"))
async def cb_digest_sub(cb: CallbackQuery, storage: BotStorage) -> None:
    try:
        hour = int(cb.data.split(":", 2)[2])
    except ValueError:
        await cb.answer()
        return
    if hour not in DIGEST_HOURS:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    storage.digest_subscribe(chat_id, hour)
    await _edit(cb, t(lang, "DIGEST_ENABLED", hour=hour), digest_kb(lang, hour))
    await cb.answer()


@router.callback_query(F.data == "dg:off")
async def cb_digest_off(cb: CallbackQuery, storage: BotStorage) -> None:
    chat_id = cb.message.chat.id
    lang = storage.get_lang(chat_id, config.DEFAULT_LANG)
    storage.digest_unsubscribe(chat_id)
    text = (
        f"{t(lang, 'DIGEST_DISABLED')}\n\n{t(lang, 'DIGEST_SUB_TITLE')}\n\n"
        f"{t(lang, 'DIGEST_STATUS_OFF')}\n\n{t(lang, 'DIGEST_HOUR_PROMPT')}"
    )
    await _edit(cb, text, digest_kb(lang, None))
    await cb.answer()


# ---------- мастер обмена (🧭 как обменять) ----------

@router.message(Command("how"))
async def cmd_how(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await message.answer(guide_menu_text(lang), reply_markup=guide_kb(lang))


@router.callback_query(F.data == "gw:menu")
async def cb_guide_menu(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    await _edit(cb, guide_menu_text(lang), guide_kb(lang))
    await cb.answer()


@router.callback_query(F.data.startswith("gw:"))
async def cb_guide_scenario(cb: CallbackQuery, service: RatesService, storage: BotStorage) -> None:
    scenario = cb.data.split(":", 1)[1]
    if scenario not in SCENARIOS:
        await cb.answer()
        return
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    snap = await service.get_snapshot()
    text = guide_text(snap, scenario, lang)
    if text is None:
        text = t(lang, "NO_DATA")
    await _edit(cb, text, scenario_kb(lang))
    await cb.answer()


# ---------- BestChange (обменники) ----------

@router.message(Command("bestchange", "bc"))
async def cmd_bestchange(message: Message, storage: BotStorage) -> None:
    lang = storage.get_lang(message.chat.id, config.DEFAULT_LANG)
    await message.answer(
        f"<b>{t(lang, 'BC_DIR_PROMPT')}</b>", reply_markup=bc_kb(lang)
    )


@router.callback_query(F.data == "bc:menu")
async def cb_bc_menu(cb: CallbackQuery, storage: BotStorage) -> None:
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    await _edit(cb, f"<b>{t(lang, 'BC_DIR_PROMPT')}</b>", bc_kb(lang))
    await cb.answer()


async def _bc_screen(cb: CallbackQuery, bestchange: BestChangeService,
                     storage: BotStorage, key: str, force: bool = False) -> None:
    if key not in DIRECTIONS:
        await cb.answer()
        return
    lang = storage.get_lang(cb.message.chat.id, config.DEFAULT_LANG)
    result = await bestchange.get(key, force=force)
    text = render.bc_text(result, DIRECTIONS[key], lang)
    await _edit(cb, text, bc_screen_kb(lang, key))
    await cb.answer()


@router.callback_query(F.data.startswith("bc:dir:"))
async def cb_bc_dir(cb: CallbackQuery, bestchange: BestChangeService, storage: BotStorage) -> None:
    await _bc_screen(cb, bestchange, storage, cb.data.split(":", 2)[2])


@router.callback_query(F.data.startswith("bc:rfsh:"))
async def cb_bc_rfsh(cb: CallbackQuery, bestchange: BestChangeService, storage: BotStorage) -> None:
    await _bc_screen(cb, bestchange, storage, cb.data.split(":", 2)[2], force=True)
