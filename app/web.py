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

from fastapi import FastAPI, Query

from . import config, formatting as fmt
from .service import RatesService

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
        "source_errors": list(snap.source_errors),
    }


def _venue_payload(q) -> dict[str, Any]:
    return {
        "venue": q.name,
        "price": q.ask if q.ask is not None else q.bid,
        "side": "ask" if q.ask is not None else "bid",
        "time": q.time.isoformat() if q.time else None,
    }


def index_html(snap, lang: str) -> str:
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

  <p class="sub" style="margin-top:16px">{esc(t(lang, 'UPDATED'))}: {ago} · {updated}</p>

  <footer>
    {esc(t(lang, 'WEB_API_NOTE'))}: <a href="/api/rates">/api/rates</a> ·
    <a href="/api/usdt">/api/usdt</a> · <a href="/docs">/docs</a> (OpenAPI)<br>
    {esc(t(lang, 'WEB_CREDIT'))}
  </footer>
</div>
</body>
</html>"""


def create_app(service: RatesService | None = None) -> FastAPI:
    """Фабрика приложения. service=None → создаётся свой (live-данные, lifespan)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import aiohttp

        from .http_client import AiohttpClient

        session = aiohttp.ClientSession()
        app.state.service = service or RatesService(AiohttpClient(session, timeout=15))
        yield
        await session.close()

    app = FastAPI(
        title="rates-bot",
        description="Cotizaciones del dólar y USDT en Argentina (bot @Parscurs77_bot)",
        version="1.0.0",
        lifespan=lifespan if service is None else None,
    )

    @app.get("/", summary="Página principal: tabla de cotizaciones")
    async def index(lang: str = Query("es", pattern="^(es|ru)$")):
        snap = await _service_of(app, service).get_snapshot()
        return _html(index_html(snap, lang))

    @app.get("/api/rates", summary="USD/ARS: oficial, blue, MEP, CCL, tarjeta + spreads")
    async def api_rates():
        snap = await _service_of(app, service).get_snapshot()
        return rates_payload(snap)

    @app.get("/api/usdt", summary="Mercado USDT/ARS: mejor ask/bid y medianas")
    async def api_usdt(volume: int = Query(config.USDT_VOLUME_DEFAULT, ge=1, le=100_000)):
        snap = await _service_of(app, service).get_snapshot(volume=volume)
        payload = rates_payload(snap)
        payload["volume"] = volume
        return payload

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
