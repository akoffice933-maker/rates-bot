"""Веб-часть ТЗ: FastAPI — главная таблица курсов + JSON API + OpenAPI.

Запуск: python -m app.web  (или uvicorn app.web:app)
Эндпоинты:
    GET /                — HTML-таблица курсов (lang=es|ru, по умолчанию es)
    GET /api/rates       — USD/ARS: oficial, blue, MEP, CCL, tarjeta + спреды
    GET /api/usdt        — рынок USDT/ARS: лучший ask/bid, медианы (volume=100)
    GET /health          — проверка живости
    GET /docs            — OpenAPI (генерируется FastAPI)

Методология та же, что у бота: фильтр выбросов ±10% от медианы, спреды
по медианам, totalAsk/totalBid с комиссиями (см. app/service.py).
"""
from __future__ import annotations

import html
from contextlib import asynccontextmanager
from typing import Any

import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from . import config, formatting as fmt
from .service import RatesService
from .storage import RateHistoryStore

LANGS = ("es", "ru")

_USD_ROWS = (
    ("oficial", "ROW_OFICIAL"),
    ("blue", "ROW_BLUE"),
    ("mep", "ROW_MEP"),
    ("ccl", "ROW_CCL"),
    ("tarjeta", "ROW_TARJETA"),
)

_PAGE_CSS = """
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;margin:0;
     background:#0f172a;color:#e2e8f0}
.wrap{max-width:720px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#94a3b8;font-size:13px;margin-bottom:20px}
table{width:100%;border-collapse:collapse;background:#1e293b;border-radius:10px;
      overflow:hidden;font-size:15px}
th,td{padding:10px 12px;text-align:left}
th{background:#334155;font-size:12px;text-transform:uppercase;letter-spacing:.4px;
   color:#cbd5e1}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr+tr{border-top:1px solid #334155}
.best{color:#4ade80;font-weight:600}
.tag{display:inline-block;background:#334155;border-radius:6px;padding:1px 8px;
     font-size:12px;margin-left:6px;color:#94a3b8}
a{color:#7dd3fc;text-decoration:none}
.spread{font-size:13px;color:#94a3b8;margin-top:14px}
.err{color:#fbbf24;font-size:13px;margin-top:10px}
.chart h2{font-size:15px;margin:24px 0 8px;color:#e2e8f0}
.chart svg{width:100%;height:auto;display:block}
footer{margin-top:28px;font-size:12px;color:#64748b;line-height:1.6}
"""


def _pair_dict(pair) -> dict[str, float | None] | None:
    if pair is None:
        return None
    return {"buy": pair.buy, "sell": pair.sell}


def rates_payload(snap) -> dict[str, Any]:
    return {
        "fetched_at": snap.fetched_at.isoformat(),
        "usd": {name: _pair_dict(getattr(snap, name)) for name, _ in _USD_ROWS},
        "spreads_pct": {
            "sell_usdt_vs_blue": snap.spread_sell_pct(),
            "buy_usdt_vs_blue": snap.spread_buy_pct(),
        },
        "usdt": {
            "median_ask": snap.usdt.median_ask if snap.usdt else None,
            "median_bid": snap.usdt.median_bid if snap.usdt else None,
            "best_ask": _venue_payload(snap.usdt.asks[0]) if snap.usdt and snap.usdt.asks else None,
            "best_bid": _venue_payload(snap.usdt.bids[0]) if snap.usdt and snap.usdt.bids else None,
        },
        "usdt_usd": {
            "best_ask": _venue_payload(snap.usdt_usd.asks[0])
            if getattr(snap, "usdt_usd", None) and snap.usdt_usd.asks else None,
            "best_bid": _venue_payload(snap.usdt_usd.bids[0])
            if getattr(snap, "usdt_usd", None) and snap.usdt_usd.bids else None,
        },
        "source_errors": list(snap.source_errors),
    }


def _venue_payload(q) -> dict[str, Any]:
    return {
        "venue": q.name,
        "price": q.ask if q.ask is not None else q.bid,
        "side": "ask" if q.ask is not None else "bid",
        "time": q.time.isoformat() if q.time else None,
    }


CHART_METRICS = {
    "usdt": (("WEB_CH_BLUE", "#60a5fa", "blue_sell"),
             ("WEB_CH_USDT_ASK", "#4ade80", "usdt_ask"),
             ("WEB_CH_USDT_BID", "#f87171", "usdt_bid")),
    "blue": (("WEB_CH_BLUE", "#60a5fa", "blue_sell"),
             ("WEB_CH_OFICIAL", "#a78bfa", "oficial_sell"),
             ("WEB_CH_MEP", "#fbbf24", "mep_sell")),
    "usdtusd": (("WEB_CH_UU_ASK", "#4ade80", "usdtusd_ask"),
                ("WEB_CH_UU_BID", "#f87171", "usdtusd_bid")),
}


def _fmt_axis(v: float) -> str:
    return f"{v:,.2f}" if v >= 100 else f"{v:.4f}"


def history_chart_svg(rows: list[dict], metric: str, lang: str,
                      width: int = 680, height: int = 200) -> str | None:
    """SVG-график истории (инлайн, без внешних библиотек).

    rows — точки из RateHistoryStore.get_history(); None-значения пропускаются.
    """
    from .i18n import t

    series = []
    for key, color, col in CHART_METRICS[metric]:
        pts = [(r["ts"], r[col]) for r in rows if r.get(col) is not None]
        if len(pts) >= 2:
            series.append((t(lang, key), color, pts))
    if not series:
        return None

    pad_l, pad_r, pad_t, pad_b = 52, 14, 30, 26
    vals = [v for _, _, pts in series for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + max(abs(lo) * 1e-3, 1e-9)
    ts_lo = min(ts for _, _, pts in series for ts, _ in pts)
    ts_hi = max(ts for _, _, pts in series for ts, _ in pts)
    if ts_hi - ts_lo < 1:
        ts_hi = ts_lo + 1

    def x(ts: float) -> float:
        return pad_l + (ts - ts_lo) / (ts_hi - ts_lo) * (width - pad_l - pad_r)

    def y(v: float) -> float:
        return pad_t + (1 - (v - lo) / (hi - lo)) * (height - pad_t - pad_b)

    from datetime import datetime

    from .formatting import AR_TZ

    def tlabel(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=AR_TZ).strftime("%d.%m %H:%M")

    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' role='img'>",
        f"<rect width='{width}' height='{height}' fill='#1e293b' rx='10'/>",
    ]
    for frac, val in ((0.0, hi), (0.5, (hi + lo) / 2), (1.0, lo)):
        gy = pad_t + frac * (height - pad_t - pad_b)
        parts.append(
            f"<line x1='{pad_l}' y1='{gy:.1f}' x2='{width - pad_r}' y2='{gy:.1f}' "
            f"stroke='#334155' stroke-width='1'/>"
        )
        parts.append(
            f"<text x='{pad_l - 6}' y='{gy + 4:.1f}' fill='#94a3b8' font-size='11' "
            f"text-anchor='end'>{_fmt_axis(val)}</text>"
        )
    for label, color, pts in series:
        coords = " ".join(f"{x(ts):.1f},{y(v):.1f}" for ts, v in pts)
        parts.append(
            f"<polyline points='{coords}' fill='none' stroke='{color}' "
            f"stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>"
        )
    lx = pad_l
    for label, color, _ in series:
        parts.append(f"<rect x='{lx}' y='8' width='12' height='4' fill='{color}' rx='2'/>")
        parts.append(
            f"<text x='{lx + 16}' y='14' fill='#cbd5e1' font-size='11'>"
            f"{html.escape(label)}</text>"
        )
        lx += 16 + 7 * len(label) + 18
    parts.append(
        f"<text x='{pad_l}' y='{height - 8}' fill='#64748b' font-size='11'>"
        f"{tlabel(ts_lo)}</text>"
    )
    parts.append(
        f"<text x='{width - pad_r}' y='{height - 8}' fill='#64748b' font-size='11' "
        f"text-anchor='end'>{tlabel(ts_hi)}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def index_html(snap, lang: str, history_rows: list[dict] | None = None) -> str:
    from .i18n import t

    def esc(x: str) -> str:
        return html.escape(x, quote=True)

    rows_html = []
    for attr, key in _USD_ROWS:
        pair = getattr(snap, attr)
        buy = f"${fmt.money(pair.buy, lang)}" if pair and pair.buy else "—"
        sell = f"${fmt.money(pair.sell, lang)}" if pair and pair.sell else "—"
        rows_html.append(
            f"<tr><td>{esc(t(lang, key))}</td>"
            f"<td class='num'>{buy}</td><td class='num'>{sell}</td></tr>"
        )

    usdt_rows = []
    if snap.usdt:
        if snap.usdt.asks:
            q = snap.usdt.asks[0]
            usdt_rows.append(
                f"<tr><td>{esc(t(lang, 'WEB_BEST_BUY'))} <span class='tag'>🥇</span></td>"
                f"<td>{esc(q.name)}</td><td class='num best'>${fmt.money(q.ask, lang)}</td></tr>"
            )
        if snap.usdt.bids:
            q = snap.usdt.bids[0]
            usdt_rows.append(
                f"<tr><td>{esc(t(lang, 'WEB_BEST_SELL'))} <span class='tag'>🥇</span></td>"
                f"<td>{esc(q.name)}</td><td class='num best'>${fmt.money(q.bid, lang)}</td></tr>"
            )
        for label_key, value in (("WEB_MEDIAN_ASK", snap.usdt.median_ask),
                                 ("WEB_MEDIAN_BID", snap.usdt.median_bid)):
            if value:
                usdt_rows.append(
                    f"<tr><td>{esc(t(lang, label_key))}</td><td>—</td>"
                    f"<td class='num'>${fmt.money(value, lang)}</td></tr>"
                )

    ss, sb = snap.spread_sell_pct(), snap.spread_buy_pct()
    spread_line = ""
    if ss is not None or sb is not None:
        spread_line = (
            f"<p class='spread'>{esc(t(lang, 'WEB_SPREAD'))}: "
            + (f"<b>{fmt.pct(ss, lang)}</b>" if ss is not None else "—") + " · "
            + (f"<b>{fmt.pct(sb, lang)}</b>" if sb is not None else "—")
            + "</p>"
        )

    errors = ""
    if snap.source_errors:
        listed = ", ".join(snap.source_errors)
        errors = f"<p class='err'>⚠️ {esc(t(lang, 'WEB_PARTIAL'))}: {esc(listed)}</p>"

    updated = fmt.ts_local(snap.fetched_at, lang)
    ago = fmt.ago(snap.fetched_at, lang)

    charts = ""
    if history_rows:
        chart_parts = []
        for title_key, metric in (("WEB_CH_ARS_TITLE", "usdt"), ("WEB_CH_UU_TITLE", "usdtusd")):
            svg = history_chart_svg(history_rows, metric, lang)
            if svg:
                chart_parts.append(
                    f"<h2>{esc(t(lang, title_key))}</h2>\n{svg}"
                )
        if chart_parts:
            charts = "<div class='chart'>" + "\n".join(chart_parts) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t(lang, 'WEB_TITLE'))}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>{esc(t(lang, 'WEB_TITLE'))}</h1>
  <p class="sub">{esc(t(lang, 'WEB_SUB'))}</p>

  <table>
    <tr><th>{esc(t(lang, 'WEB_USD_TABLE'))}</th>
        <th class='num'>{esc(t(lang, 'WEB_BUY'))}</th>
        <th class='num'>{esc(t(lang, 'WEB_SELL'))}</th></tr>
    {''.join(rows_html)}
  </table>

  <table style='margin-top:18px'>
    <tr><th>USDT/ARS</th><th>{esc(t(lang, 'WEB_VENUE'))}</th>
        <th class='num'>{esc(t(lang, 'WEB_PRICE'))}</th></tr>
    {''.join(usdt_rows)}
  </table>

  {spread_line}
  {errors}

  {charts}

  <p class="sub" style="margin-top:16px">{esc(t(lang, 'UPDATED'))}: {ago} · {updated}</p>

  <footer>
    {esc(t(lang, 'WEB_API_NOTE'))}: <a href="/api/rates">/api/rates</a> ·
    <a href="/api/usdt">/api/usdt</a> · <a href="/docs">/docs</a> (OpenAPI)<br>
    {esc(t(lang, 'WEB_CREDIT'))}
  </footer>
</div>
</body>
</html>"""


def create_app(service: RatesService | None = None, history=None) -> FastAPI:
    """Фабрика приложения. service=None → создаётся свой (live-данные, lifespan).

    history — RateHistoryStore (или None в тестах без истории).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import aiohttp

        from .http_client import AiohttpClient

        session = aiohttp.ClientSession()
        app.state.service = service or RatesService(AiohttpClient(session, timeout=15))
        app.state.history = history or RateHistoryStore(config.HISTORY_DB_PATH)
        yield
        await session.close()

    app = FastAPI(
        title="rates-bot",
        description="Cotizaciones del dólar y USDT en Argentina (bot @Parscurs77_bot)",
        version="1.1.0",
        lifespan=lifespan if service is None else None,
    )
    if history is not None:
        app.state.history = history

    def _record(snap) -> None:
        """Записать точку истории (не чаще HISTORY_INTERVAL_SECONDS)."""
        store = getattr(app.state, "history", None)
        if store is None:
            return
        try:
            store.maybe_record(snap, config.HISTORY_INTERVAL_SECONDS)
        except Exception:  # история не должна ронять выдачу
            import logging

            logging.getLogger(__name__).exception("не записана история курсов")

    def _history_rows(hours: int) -> list[dict]:
        store = getattr(app.state, "history", None)
        if store is None:
            return []
        return store.get_history(int(time.time()) - hours * 3600)

    @app.get("/", summary="Página principal: tabla de cotizaciones")
    async def index(lang: str = Query("es", pattern="^(es|ru)$")):
        snap = await _service_of(app, service).get_snapshot_full()
        _record(snap)
        return _html(index_html(snap, lang, history_rows=_history_rows(168)))

    @app.get("/api/rates", summary="USD/ARS: oficial, blue, MEP, CCL, tarjeta + spreads")
    async def api_rates():
        snap = await _service_of(app, service).get_snapshot_full()
        _record(snap)
        return rates_payload(snap)

    @app.get("/api/usdt", summary="Mercado USDT/ARS: mejor ask/bid y medianas")
    async def api_usdt(volume: int = Query(config.USDT_VOLUME_DEFAULT, ge=1, le=100_000)):
        snap = await _service_of(app, service).get_snapshot(volume=volume)
        if volume == config.USDT_VOLUME_DEFAULT:
            _record(snap)  # историю пишем только для дефолтного объёма
        payload = rates_payload(snap)
        payload["volume"] = volume
        return payload

    @app.get("/api/history", summary="Historial de cotizaciones (últimas horas)")
    async def api_history(hours: int = Query(24, ge=1, le=2160)):
        return {"hours": hours, "points": _history_rows(hours)}

    @app.get("/chart.svg", summary="Gráfico SVG del historial")
    async def chart_svg(
        hours: int = Query(24, ge=1, le=2160),
        metric: str = Query("usdt", pattern="^(usdt|blue|usdtusd)$"),
        lang: str = Query("es", pattern="^(es|ru)$"),
    ):
        svg = history_chart_svg(_history_rows(hours), metric, lang)
        if svg is None:
            raise HTTPException(status_code=404, detail="no history data yet")
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/health", summary="Health check")
    async def health():
        return {"status": "ok"}

    return app


def _service_of(app: FastAPI, service: RatesService | None) -> RatesService:
    return service or app.state.service


def _html(body: str):
    from fastapi.responses import HTMLResponse

    return HTMLResponse(body)


app = create_app()


def main() -> None:
    """Точка входа: python -m app.web"""
    import uvicorn

    uvicorn.run(
        "app.web:app",
        host="0.0.0.0",
        port=int(config.WEB_PORT),
        log_level=config.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
