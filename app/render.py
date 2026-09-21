"""Рендер сообщений бота (HTML).

Два направления пар:
  прямое (direct)  — USD/ARS, USDT/ARS: сколько ARS стоит 1 USD / 1 USDT;
  обратное (inverse) — ARS/USD, ARS/USDT: сколько USD/USDT дают за 1.000 ARS.

Семантика стрелок в обратном режиме:
  →  покупка базовой валюты (ARS → USD/USDT): 1000 / venta(ask);
  ←  продажа базовой валюты (USD/USDT → ARS): чтобы получить 1.000 ARS,
     нужно продать 1000 / compra(bid) базовой валюты.

Спред — величина в процентах и от направления не зависит.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import formatting as fmt
from .i18n import t
from .service import Snapshot, UsdtUsdView
from .venue_links import SOURCE_URLS, ext_link, venue_link

STALE_AFTER_SECONDS = 180        # снапшот старше 3×TTL помечаем как устаревший
VENUE_STALE_AFTER_SECONDS = 300  # котировка площадки старше 5 мин — с предупреждением
TOP_N = 5


def screen(
    action: str,
    snap: Snapshot,
    lang: str,
    now: datetime | None = None,
    inverse: bool = False,
    volume: int | None = None,
) -> str | None:
    if action == "rates":
        return rates_text(snap, lang, now, inverse)
    if action == "usdt":
        return usdt_text(snap, lang, now, inverse, volume)
    if action == "spread":
        return spread_text(snap, lang, now)
    raise ValueError(f"unknown action: {action}")


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _stale_banner(snap: Snapshot, lang: str, now: datetime) -> list[str]:
    if (now - snap.fetched_at).total_seconds() > STALE_AFTER_SECONDS:
        return [f"<b>{t(lang, 'STALE_BANNER')}</b>", ""]
    return []


def _tail(snap: Snapshot, lang: str, now: datetime, credit: str | None = None) -> list[str]:
    lines: list[str] = []
    if credit:
        lines.append(credit)
    lines.append(
        f"{t(lang, 'UPDATED')}: {fmt.ago(snap.fetched_at, lang, now)} · "
        f"{fmt.ts_local(snap.fetched_at, lang)}"
    )
    if snap.source_errors:
        lines.append(f"⚠️ {t(lang, 'PARTIAL')}")
    return lines


# ---------- /rates ----------

def _rate_rows(snap: Snapshot):
    return [
        ("🇦🇷", "ROW_OFICIAL", snap.oficial),
        ("🔵", "ROW_BLUE", snap.blue),
        ("📈", "ROW_MEP", snap.mep),
        ("🏦", "ROW_CCL", snap.ccl),
        ("💳", "ROW_TARJETA", snap.tarjeta),
    ]


def rates_text(snap: Snapshot, lang: str, now: datetime | None = None, inverse: bool = False) -> str | None:
    now = _now(now)
    rows = _rate_rows(snap)

    if inverse:
        body = []
        for icon, key, p in rows:
            if p and (p.buy is not None or p.sell is not None):
                body.append(
                    f"{icon} {t(lang, key)}: → {fmt.per_thousand(p.sell, lang)} / "
                    f"← {fmt.per_thousand(p.buy, lang)} USD"
                )
        if not body:
            return None
        lines = _stale_banner(snap, lang, now)
        lines += [f"<b>{t(lang, 'RATES_TITLE_INV')}</b>", "", *body, ""]
        lines.append(t(lang, "RATES_LEGEND_INV"))
    else:
        body = [
            f"{icon} {t(lang, key)}: {fmt.money(p.buy, lang)} / {fmt.money(p.sell, lang)}"
            for icon, key, p in rows
            if p and (p.buy is not None or p.sell is not None)
        ]
        if not body:
            return None
        lines = _stale_banner(snap, lang, now)
        lines += [f"<b>{t(lang, 'RATES_TITLE')}</b>", "", *body, ""]
        lines.append(t(lang, "PAIR_NOTE"))

    lines.append(
        f"{t(lang, 'SOURCES')}: "
        + " · ".join(
            ext_link(name, SOURCE_URLS[key])
            for key, name in (
                ("bluelytics", "Bluelytics"),
                ("dolarapi", "DolarAPI"),
                ("ambito", "Ámbito"),
            )
        )
    )
    lines += _tail(snap, lang, now)
    return "\n".join(lines)


# ---------- /usdt ----------

def _venue_lines(market, attr: str, lang: str, now: datetime, header_key: str, inverse: bool) -> list[str]:
    quotes = getattr(market, attr)
    if not quotes:
        return []
    lines = [f"<b>{t(lang, header_key)}</b>"]
    for i, q in enumerate(quotes[:TOP_N], 1):
        price = q.ask if attr == "asks" else q.bid
        if inverse:
            # asks: чем дешевле USDT, тем БОЛЬШЕ USDT за 1.000 ARS (порядок сохранён);
            # bids: чем дороже USDT, тем МЕНЬШЕ USDT за 1.000 ARS (порядок сохранён).
            shown = f"{fmt.per_thousand(price, lang)} USDT"
        else:
            shown = f"${fmt.money(price, lang)}"
        marker = "🥇 " if i == 1 else f"{i}. "
        stale = ""
        if q.time and (now - q.time).total_seconds() > VENUE_STALE_AFTER_SECONDS:
            stale = " ⚠️"
        lines.append(f"{marker}{venue_link(q.key, q.name)} — {shown}{stale}")
    return lines + [""]


def usdt_text(
    snap: Snapshot,
    lang: str,
    now: datetime | None = None,
    inverse: bool = False,
    volume: int | None = None,
) -> str | None:
    now = _now(now)
    m = snap.usdt
    if not m or (not m.asks and not m.bids):
        return None

    if inverse:
        title = t(lang, "USDT_TITLE_INV")
        buy_hdr, sell_hdr = "USDT_BUY_HEADER_INV", "USDT_SELL_HEADER_INV"
        note = t(lang, "USDT_NOTE_INV")
    else:
        title = t(lang, "USDT_TITLE")
        buy_hdr, sell_hdr = "USDT_BUY_HEADER", "USDT_SELL_HEADER"
        note = t(lang, "USDT_NOTE")

    lines = _stale_banner(snap, lang, now)
    lines += [f"<b>{title}</b>", ""]
    lines += _venue_lines(m, "asks", lang, now, buy_hdr, inverse)
    lines += _venue_lines(m, "bids", lang, now, sell_hdr, inverse)
    tail_parts = [note]
    if volume:
        tail_parts.append(t(lang, "USDT_VOLUME_NOTE", vol=fmt.money(volume, lang, 0)))
    tail_parts.append(ext_link(t(lang, "CRIPTOYA_CREDIT"), SOURCE_URLS["criptoya"]))
    lines.append(" · ".join(tail_parts))
    lines += _tail(snap, lang, now)
    return "\n".join(lines)


# ---------- /usdtusd ----------


def usdtusd_text(view: UsdtUsdView, lang: str, now: datetime | None = None) -> str | None:
    """USDT ⇄ USD в Аргентине: безнал (CriptoYa USDT/USD) + наличный расчёт через blue.

    Наличный кросс (2 шага): купить USDT = лучший ask USDT/ARS ÷ blue compra;
    продать USDT = лучший bid USDT/ARS ÷ blue venta. Прямой обмен в cuevas
    обычно выгоднее (~2–3% комиссии) — об этом подсказка в конце блока.
    """
    now = _now(now)
    snap = view.snap
    m = view.usd
    has_cashless = m is not None and bool(m.asks or m.bids)
    best_ask = snap.usdt.asks[0] if snap.usdt and snap.usdt.asks else None
    best_bid = snap.usdt.bids[0] if snap.usdt and snap.usdt.bids else None
    has_cash = snap.blue is not None and (best_ask or best_bid) is not None
    if not has_cashless and not has_cash:
        return None

    lines = _stale_banner(snap, lang, now)
    lines += [f"<b>{t(lang, 'USDTUSD_TITLE')}</b>", ""]

    if has_cashless:
        lines.append(f"<b>{t(lang, 'USDTUSD_CASHLESS', n=str(len(m.all_venues)))}</b>")
        lines.append("")
        if m.asks:
            lines.append(f"<b>{t(lang, 'USDTUSD_BUY_HDR')}</b>")
            for i, q in enumerate(m.asks[:TOP_N], 1):
                marker = "🥇 " if i == 1 else f"{i}. "
                stale = " ⚠️" if q.time and (now - q.time).total_seconds() > VENUE_STALE_AFTER_SECONDS else ""
                lines.append(f"{marker}{venue_link(q.key, q.name)} — {fmt.money(q.ask, lang, 4)} USD{stale}")
            lines.append("")
        if m.bids:
            lines.append(f"<b>{t(lang, 'USDTUSD_SELL_HDR')}</b>")
            for i, q in enumerate(m.bids[:TOP_N], 1):
                marker = "🥇 " if i == 1 else f"{i}. "
                stale = " ⚠️" if q.time and (now - q.time).total_seconds() > VENUE_STALE_AFTER_SECONDS else ""
                lines.append(f"{marker}{venue_link(q.key, q.name)} — {fmt.money(q.bid, lang, 4)} USD{stale}")
            lines.append("")

    if has_cash:
        lines.append(f"<b>{t(lang, 'USDTUSD_CASH_HDR')}</b>")
        if best_ask is not None and snap.blue.buy:
            price = best_ask.ask / snap.blue.buy
            lines.append(
                "• " + t(
                    lang, "USDTUSD_CASH_BUY",
                    price=fmt.money(price, lang, 4),
                    pct=fmt.pct((price - 1) * 100, lang, 1),
                )
            )
        if best_bid is not None and snap.blue.sell:
            price = best_bid.bid / snap.blue.sell
            lines.append(
                "• " + t(
                    lang, "USDTUSD_CASH_SELL",
                    price=fmt.money(price, lang, 4),
                    pct=fmt.pct((price - 1) * 100, lang, 1),
                )
            )
        venues = " / ".join(q.name for q in (best_ask, best_bid) if q is not None)
        lines.append(
            t(
                lang, "USDTUSD_CASH_PATH",
                blue=f"{fmt.money(snap.blue.buy, lang, 0)}/{fmt.money(snap.blue.sell, lang, 0)}",
                venues=venues,
            )
        )
        lines.append("")
        lines.append(t(lang, "USDTUSD_CUEVA"))
        lines.append("")

    credit = " · ".join(
        ext_link(t(lang, key), SOURCE_URLS[src_key])
        for key, src_key in (("CRIPTOYA_CREDIT", "criptoya"), ("BLUELYTICS_CREDIT", "bluelytics"))
    )
    lines.append(credit)
    lines += _tail(snap, lang, now)
    return "\n".join(lines)


# ---------- /spread ----------

def spread_text(snap: Snapshot, lang: str, now: datetime | None = None) -> str | None:
    now = _now(now)
    ss, sb = snap.spread_sell_pct(), snap.spread_buy_pct()
    if ss is None and sb is None:
        return None
    lines = _stale_banner(snap, lang, now)
    lines += [f"<b>{t(lang, 'SPREAD_TITLE')}</b>", ""]
    if ss is not None:
        lines += [
            f"<b>{t(lang, 'SPREAD_SELL_TITLE')}</b>",
            f"• {t(lang, 'SPREAD_USDT_MEDIAN')}: ${fmt.money(snap.usdt.median_bid, lang)}",
            f"• {t(lang, 'SPREAD_BLUE_BUY')}: ${fmt.money(snap.blue.buy, lang)}",
            t(lang, "SPREAD_SELL_RESULT", pct=fmt.pct(ss, lang)),
            "",
        ]
    if sb is not None:
        lines += [
            f"<b>{t(lang, 'SPREAD_BUY_TITLE')}</b>",
            f"• {t(lang, 'SPREAD_USDT_MEDIAN')}: ${fmt.money(snap.usdt.median_ask, lang)}",
            f"• {t(lang, 'SPREAD_BLUE_SELL')}: ${fmt.money(snap.blue.sell, lang)}",
            t(lang, "SPREAD_BUY_RESULT", pct=fmt.pct(sb, lang)),
            "",
        ]
    lines.append(t(lang, "SPREAD_NOTE"))
    lines += _tail(
        snap, lang, now, credit=ext_link(t(lang, "CRIPTOYA_CREDIT"), SOURCE_URLS["criptoya"])
    )


def links_text(lang: str) -> str:
    """Экран «Открыть всё»: источники + где купить/продать USD."""
    return (
        f"<b>{t(lang, 'LINKS_TITLE')}</b>\n\n{t(lang, 'LINKS_NOTE')}\n\n"
        f"<b>{t(lang, 'LINKS_USD_TITLE')}</b>\n{t(lang, 'LINKS_USD_NOTE')}"
    )


# ---------- /p2p (Binance P2P, прямые объявления) ----------

def _ad_line(i: int, ad, lang: str) -> str:
    marker = "🥇 " if i == 1 else f"{i}. "
    methods = ", ".join(ad.methods[:2]) or "—"
    if ad.max_amount and ad.min_amount:
        limits = f"{fmt.money(ad.min_amount, lang, 0)}–{fmt.money(ad.max_amount, lang, 0)} ARS"
    elif ad.max_amount:
        limits = f"⩽ {fmt.money(ad.max_amount, lang, 0)} ARS"
    elif ad.min_amount:
        limits = f"⩾ {fmt.money(ad.min_amount, lang, 0)} ARS"
    else:
        limits = ""
    parts = [f"{marker}${fmt.money(ad.price, lang)}", methods]
    if limits:
        parts.append(limits)
    line = " · ".join(parts)
    if ad.completion_rate:
        line += f" · ✓{round(ad.completion_rate * 100)}%"
    if ad.advertiser:
        line += f" · {ad.advertiser}"
    return line


def p2p_text(result, snap: Snapshot, lang: str, now: datetime | None = None) -> str | None:
    """Экран /p2p: прямые объявления Binance либо fallback на агрегат CriptoYa."""
    now = _now(now)

    if result.ok:
        if not result.sell_ads and not result.buy_ads:
            body = t(lang, "P2P_EMPTY")
        else:
            blocks: list[str] = []
            if result.sell_ads:
                blocks.append(f"<b>{t(lang, 'P2P_BUY_HEADER')}</b>")
                blocks += [_ad_line(i, ad, lang) for i, ad in enumerate(result.sell_ads, 1)]
                blocks.append("")
            if result.buy_ads:
                blocks.append(f"<b>{t(lang, 'P2P_SELL_HEADER')}</b>")
                blocks += [_ad_line(i, ad, lang) for i, ad in enumerate(result.buy_ads, 1)]
            body = "\n".join(blocks)
        lines = [f"<b>{t(lang, 'P2P_TITLE')}</b>", "", body, "", t(lang, "P2P_NOTE")]
        if result.fetched_at:
            lines.append(f"{t(lang, 'UPDATED')}: {fmt.ago(result.fetched_at, lang, now)}")
        return "\n".join(lines)

    # fallback: живые объявления недоступны (403/прокси) — агрегат CriptoYa
    lines = [f"<b>{t(lang, 'P2P_TITLE')}</b>", "", t(lang, "P2P_UNAVAILABLE"), ""]
    if snap.usdt:
        bq = next((q for q in snap.usdt.all_venues if q.key == "binancep2p"), None)
        if bq and (bq.ask or bq.bid):
            lines.append(
                t(
                    lang,
                    "P2P_FB_LINE",
                    ask=fmt.money(bq.ask, lang),
                    bid=fmt.money(bq.bid, lang),
                )
            )
            lines.append("")
    lines.append(f"{t(lang, 'UPDATED')}: {fmt.ago(snap.fetched_at, lang, now)}")
    return "\n".join(lines)


# ---------- /bestchange ----------

def _bc_row(i: int, row, lang: str) -> str:
    from .venue_links import ext_link

    marker = "🥇 " if i == 1 else f"{i}. "

    def amt(x: float) -> str:
        # целые — без копеек (1, 90, 100), дробные — 2 знака (89,58)
        return fmt.money(x, lang, 0 if abs(x - round(x)) < 1e-9 else 2)

    parts = [
        f"{marker}{ext_link(row.name, row.click_url)} — "
        f"{amt(row.give)} {row.give_unit} / {amt(row.receive)} {row.receive_unit}"
    ]
    if row.min_amount is not None or row.max_amount is not None:
        lo = f"{t(lang, 'BC_MIN')} {fmt.money(row.min_amount, lang, 0)}" if row.min_amount else ""
        hi = f"{t(lang, 'BC_MAX')} {fmt.money(row.max_amount, lang, 0)}" if row.max_amount else ""
        limits = " · ".join(x for x in (lo, hi) if x)
        parts.append(limits)
    if row.reserve is not None:
        parts.append(f"{t(lang, 'BC_RESERVE')}: {fmt.money(row.reserve, lang, 0)} {row.receive_unit}")
    if row.reviews:
        parts.append(f"✓{row.reviews}")
    return " · ".join(parts)


def bc_text(result, direction, lang: str, now: datetime | None = None) -> str:
    """Экран BestChange: топ обменников с кликабельными ссылками."""
    now = _now(now)
    name = direction.name_ru if lang == "ru" else direction.name_es
    title = t(lang, "BC_TITLE", direction=name)

    if not result.ok:
        lines = [f"<b>{title}</b>", "", t(lang, "BC_UNAVAILABLE")]
        return "\n".join(lines)

    lines = [f"<b>{title}</b>", ""]
    lines.append(t(lang, "BC_BETTER_MIN" if direction.better == "min" else "BC_BETTER_MAX"))
    lines.append("")
    if result.rows:
        lines += [_bc_row(i, row, lang) for i, row in enumerate(result.rows, 1)]
    else:
        lines.append(t(lang, "BC_EMPTY"))
    lines.append("")
    if result.fetched_at:
        lines.append(f"{t(lang, 'UPDATED')}: {fmt.ago(result.fetched_at, lang, now)}")
    lines.append(t(lang, "BC_FOOTER"))
    from .venue_links import SOURCE_URLS, ext_link

    lines.append(ext_link(t(lang, "BC_CREDIT"), SOURCE_URLS["bestchange"]))
    return "\n".join(lines)
