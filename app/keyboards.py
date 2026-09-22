"""Инлайн-клавиатуры."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import formatting as fmt
from .alerts import METRICS, METRICS_ORDER
from .digest import DIGEST_HOURS
from .i18n import t
from .storage import Alert
from .sources.bestchange import DIRECTIONS, DIRECTIONS_ORDER
from .sources.ratesguru import DIRECTIONS as RG_DIRECTIONS, DIRECTIONS_ORDER as RG_ORDER
from .venue_links import SOURCE_URLS, USD_URLS

# action -> (метка при direct, метка при inverse)
SWAP_TARGET = {
    "rates": ("ARS/USD", "USD/ARS"),
    "usdt": ("ARS/USDT", "USDT/ARS"),
}

ALERT_PRESETS = (3.0, 4.0, 5.0)          # пресеты спреда, %
VOL_PRESETS = (100, 500, 1000, 5000)     # пресеты объёма, USDT


def main_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "BTN_RATES"), callback_data="scr:rates"),
                InlineKeyboardButton(text=t(lang, "BTN_USDT"), callback_data="scr:usdt"),
                InlineKeyboardButton(text=t(lang, "BTN_USDTUSD"), callback_data="uu:scr"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "BTN_P2P"), callback_data="p2p:scr"),
                InlineKeyboardButton(text=t(lang, "BTN_SPREAD"), callback_data="scr:spread"),
                InlineKeyboardButton(text=t(lang, "BTN_BESTCHANGE"), callback_data="bc:menu"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "BTN_COMPARE"), callback_data="cmp:scr"),
                InlineKeyboardButton(text=t(lang, "BTN_ALERT"), callback_data="al:menu"),
                InlineKeyboardButton(text=t(lang, "BTN_LANG"), callback_data="scr:lang"),
            ],
            [InlineKeyboardButton(text=t(lang, "GUIDE_BTN"), callback_data="gw:menu")],
        ]
    )


def screen_kb(
    lang: str, action: str, direction: str = "direct", volume: int | None = None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if action == "usdt" and volume:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ {v}" if v == volume else f"💵 {v}",
                    callback_data=f"vol:{v}",
                )
                for v in VOL_PRESETS
            ]
        )
    refresh_cb = "p2p:rfsh" if action == "p2p" else f"rfsh:{action}"
    if action in SWAP_TARGET:
        # кнопка показывает пару, В КОТОРУЮ переключимся
        target = SWAP_TARGET[action][0 if direction == "direct" else 1]
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "BTN_SWAP", pair=target), callback_data=f"swap:{action}"
                ),
                InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data=refresh_cb),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data=refresh_cb)]
        )
    if action in ("rates", "usdt"):
        target = "gw:buy_usd" if action == "rates" else "gw:buy_usdt"
        rows.append([InlineKeyboardButton(text=t(lang, "GUIDE_BTN"), callback_data=target)])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_LINKS"), callback_data="scr:links")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cmp_kb(lang: str) -> InlineKeyboardMarkup:
    """Экран сравнения источников USDT/ARS."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data="cmp:rfsh")],
            [InlineKeyboardButton(text=t(lang, "BTN_LINKS"), callback_data="scr:links")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


def uu_kb(lang: str) -> InlineKeyboardMarkup:
    """Экран /usdtusd: обновить, источники, меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data="uu:rfsh")],
            [InlineKeyboardButton(text=t(lang, "BTN_LINKS"), callback_data="scr:links")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


def lang_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇪🇸 Español", callback_data="setlang:es"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="setlang:ru"),
            ],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


# ---------- алерты ----------

def alert_threshold_label(alert: Alert, lang: str) -> str:
    """«⩾ +3,5 %» для спреда, «⩾ $1.550» для абсолютного курса."""
    spec = METRICS[alert.metric]
    if spec.kind == "spread":
        return f"⩾ {fmt.pct(alert.threshold, lang, 1)}"
    op = "⩾" if alert.direction == "above" else "⩽"
    return f"{op} ${fmt.money(alert.threshold, lang)}"


def alert_kb(lang: str, alerts: list[Alert]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for a in alerts:
        spec = METRICS.get(a.metric)
        if spec is None:
            continue
        label = f"🗑 {t(lang, spec.name_key)} {alert_threshold_label(a, lang)}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"al:del:{a.id}")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_ALERT_ADD"), callback_data="al:add")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_DIGEST"), callback_data="dg:menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alert_categories_kb(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, METRICS[m].name_key), callback_data=f"al:cat:{m}")]
        for m in METRICS_ORDER
    ]
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="al:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def alert_direction_kb(lang: str, metric: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(lang, "ALERT_DIR_ABOVE"), callback_data=f"al:dir:{metric}:above"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(lang, "ALERT_DIR_BELOW"), callback_data=f"al:dir:{metric}:below"
                )
            ],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="al:menu")],
        ]
    )


def alert_value_kb(
    lang: str,
    presets: list[tuple[str, float]],
    metric: str,
    direction: str,
) -> InlineKeyboardMarkup:
    """presets — [(label, value), ...]; direction '' для спред-метрик."""
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"al:pre:{metric}:{direction}:{value}"
            )
            for label, value in presets
        ],
        [InlineKeyboardButton(text=t(lang, "BTN_CUSTOM"), callback_data=f"al:cust:{metric}:{direction}")],
        [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="al:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- дайджест ----------

def digest_kb(lang: str, current_hour: int | None) -> InlineKeyboardMarkup:
    """current_hour=None — подбор времени; иначе — статусное меню."""
    if current_hour is None:
        rows = [
            [
                InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"dg:sub:{h}")
                for h in DIGEST_HOURS
            ],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="al:menu")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text=t(lang, "DIGEST_BTN_CHANGE"), callback_data="dg:pick")],
            [InlineKeyboardButton(text=t(lang, "DIGEST_BTN_OFF"), callback_data="dg:off")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="al:menu")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- «Открыть всё» ----------

def links_kb(lang: str) -> InlineKeyboardMarkup:
    """Экран «Открыть всё»: источники котировок + где купить/продать USD."""

    def src_btn(text: str, key: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, url=SOURCE_URLS[key])

    def usd_btn(text: str, key: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, url=USD_URLS[key])

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [src_btn("📊 Bluelytics", "bluelytics"), src_btn("⚙️ DolarAPI", "dolarapi")],
            [src_btn("📰 Ámbito", "ambito"), src_btn("🏦 Banco Nación", "bna")],
            [src_btn("💰 CriptoYa", "criptoya")],
            [src_btn("💱 BestChange", "bestchange"), src_btn("📊 RatesGuru", "ratesguru")],
            # Где купить / продать USD
            [usd_btn("📈 InvertirOnline", "iol"), usd_btn("📈 Balanz", "balanz")],
            [usd_btn("📈 Bull Market", "bullmarket"), usd_btn("💳 Personal Pay", "personalpay")],
            [usd_btn("🪙 Cocos", "cocos"), usd_btn("💳 Ualá", "uala")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


# ---------- мастер обмена ----------

def guide_kb(lang: str) -> InlineKeyboardMarkup:
    """Выбор сценария обмена."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "GUIDE_SC_BUY_USDT"), callback_data="gw:buy_usdt"),
                InlineKeyboardButton(text=t(lang, "GUIDE_SC_SELL_USDT"), callback_data="gw:sell_usdt"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "GUIDE_SC_BUY_USD"), callback_data="gw:buy_usd"),
                InlineKeyboardButton(text=t(lang, "GUIDE_SC_SELL_USD"), callback_data="gw:sell_usd"),
            ],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


def scenario_kb(lang: str) -> InlineKeyboardMarkup:
    """Экран сценария: сменить направление / в меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "GUIDE_BTN"), callback_data="gw:menu")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


# ---------- BestChange ----------

def bc_kb(lang: str) -> InlineKeyboardMarkup:
    """Выбор направления обмена."""
    rows = [
        [InlineKeyboardButton(text=DIRECTIONS[k].name_ru if lang == "ru" else DIRECTIONS[k].name_es,
                              callback_data=f"bc:dir:{k}")]
        for k in DIRECTIONS_ORDER
    ]
    rows.append([InlineKeyboardButton(text="📊 RatesGuru", callback_data="rg:menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rg_kb(lang: str) -> InlineKeyboardMarkup:
    """Выбор направления RatesGuru (+ переход на BestChange)."""
    rows = [
        [InlineKeyboardButton(text=RG_DIRECTIONS[k].name_ru if lang == "ru" else RG_DIRECTIONS[k].name_es,
                              callback_data=f"rg:dir:{k}")]
        for k in RG_ORDER
    ]
    rows.append([InlineKeyboardButton(text="💱 BestChange", callback_data="bc:menu")])
    rows.append([InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rg_screen_kb(lang: str, key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data=f"rg:rfsh:{key}")],
            [InlineKeyboardButton(text="📊 RatesGuru", callback_data="rg:menu")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )


def bc_screen_kb(lang: str, key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "BTN_REFRESH"), callback_data=f"bc:rfsh:{key}")],
            [InlineKeyboardButton(text="💱 BestChange", callback_data="bc:menu")],
            [InlineKeyboardButton(text=t(lang, "BTN_BACK"), callback_data="menu:main")],
        ]
    )
