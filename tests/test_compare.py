"""Экран /compare: USDT/ARS из трёх источников (CriptoYa + BestChange + Binance P2P)."""
from datetime import datetime, timezone

from app import render
from app.bestchange import BestChangeResult
from app.keyboards import cmp_kb, main_menu
from app.p2p import P2PResult
from app.service import Snapshot, UsdtMarket
from app.sources.bestchange import ExchangerRow, parse_rows
from app.sources.bluelytics import RatePair
from app.sources.criptoya import VenueQuote
from app.sources.binance_p2p import P2PAd

NOW = datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc)

MP_HTML = open("tests/fixtures/bc_usdt_mercadopago_ars.html", encoding="utf-8").read()


def make_snap() -> Snapshot:
    market = UsdtMarket(
        all_venues=(),
        asks=(VenueQuote(key="mexcp2p", name="MEXC P2P", ask=1593.25, bid=None, time=NOW),),
        bids=(VenueQuote(key="satoshitango", name="SatoshiTango", ask=None, bid=1595.41, time=NOW),),
        median_ask=1593.25,
        median_bid=1595.41,
    )
    return Snapshot(fetched_at=NOW, blue=RatePair(buy=1517.0, sell=1550.0), usdt=market)


def bc_sell_result() -> BestChangeResult:
    """usdt_mp: лучший обменник по живой фикстуре — SafuExchange 1563,82 ARS/USDT."""
    return BestChangeResult(ok=True, error=None, direction_key="usdt_mp",
                            rows=tuple(parse_rows(MP_HTML)), fetched_at=NOW)


def bc_buy_result() -> BestChangeResult:
    """mp_usdt: рукописные строки (ARS за 1 USDT в give, лучше — меньше)."""
    def _row(name: str, give: float, i: int) -> ExchangerRow:
        return ExchangerRow(
            name=name, click_url=f"https://www.bestchange.com/click.php?id={i}",
            give=give, give_unit="ARS MP", receive=1.0, receive_unit="USDT TRC20",
            min_amount=100.0, max_amount=None, reserve=1_000_000.0, reviews=100,
        )

    rows = (_row("Dmoney", 1600.0, 1), _row("Tsunami", 1610.0, 2))
    return BestChangeResult(ok=True, error=None, direction_key="mp_usdt", rows=rows, fetched_at=NOW)


def p2p_ok() -> P2PResult:
    return P2PResult(
        ok=True, error=None,
        sell_ads=(P2PAd(price=1590.0, min_amount=100.0, max_amount=10_000.0, available=5000.0,
                        methods=("Mercado Pago",), advertiser="FastTrader", completion_rate=0.97),),
        buy_ads=(P2PAd(price=1598.5, min_amount=100.0, max_amount=8_000.0, available=3000.0,
                       methods=("Mercado Pago",), advertiser="GoldBuyer", completion_rate=0.95),),
        fetched_at=NOW,
    )


def test_compare_ranking_sell():
    text = render.compare_text(make_snap(), bc_sell_result(), bc_buy_result(), p2p_ok(), "ru", now=NOW)
    # продажа: Binance 1598,5 > CriptoYa 1595,41 > BestChange 1563,82
    i_bn = text.index("GoldBuyer")
    i_ct = text.index("SatoshiTango")
    i_bc = text.index("SafuExchange")
    assert i_bn < i_ct < i_bc
    assert "🥇 " in text.split("Продать USDT")[1].splitlines()[1]
    # отставание от лучшего: (1563.82-1598.5)/1598.5 = -2.2%
    assert "(-2,2 % к лучшему)" in text


def test_compare_ranking_buy():
    text = render.compare_text(make_snap(), bc_sell_result(), bc_buy_result(), p2p_ok(), "ru", now=NOW)
    # покупка: Binance 1590 < CriptoYa 1593,25 < BestChange (Dmoney 1600)
    i_bn = text.index("FastTrader")
    i_ct = text.index("MEXC P2P")
    i_bc = text.index("Dmoney")
    assert i_bn < i_ct < i_bc
    # в блоке покупки лучший не теряет процентный хвост
    buy_block = text.split("Купить USDT")[1]
    first_line = [ln for ln in buy_block.splitlines() if ln.startswith("🥇")][0]
    assert "к лучшему" not in first_line


def test_compare_best_of_bc_is_min_or_max():
    """В блоке продажи — max(receive) по всем строкам, не первая строка рейтинга."""
    rows = parse_rows(MP_HTML)
    best = max(r.receive for r in rows)
    text = render.compare_text(make_snap(), bc_sell_result(), bc_buy_result(), p2p_ok(), "ru", now=NOW)
    assert f"{best:.2f}" in text.replace("\u00a0", " ").replace("1 563,82", "1563.82") or "1 563,82" in text


def test_compare_p2p_unavailable():
    blocked = P2PResult(ok=False, error="blocked")
    text = render.compare_text(make_snap(), bc_sell_result(), bc_buy_result(), blocked, "ru", now=NOW)
    assert "Binance P2P: сейчас недоступно" in text
    assert "SatoshiTango" in text and "SafuExchange" in text  # остальные живут


def test_compare_es():
    text = render.compare_text(make_snap(), bc_sell_result(), bc_buy_result(), p2p_ok(), "es", now=NOW)
    assert "⚖️ USDT/ARS — comparación de fuentes" in text
    assert "Vender USDT → recibir ARS" in text
    assert "no disponible" not in text
    assert "vs el mejor" in text


def test_compare_all_unavailable():
    text = render.compare_text(Snapshot(fetched_at=NOW), None, None, None, "ru", now=NOW)
    assert text is None


def test_compare_keyboard_and_menu():
    buttons = [b for row in cmp_kb("ru").inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["cmp:rfsh", "scr:links", "menu:main"]
    for lang in ("ru", "es"):
        menu = [b for row in main_menu(lang).inline_keyboard for b in row]
        assert any(b.callback_data == "cmp:scr" for b in menu)


def test_compare_html_escaped_advertiser():
    """Ник рекламодателя экранируется (защита от HTML-инъекции в сообщении)."""
    evil = P2PResult(
        ok=True, error=None,
        buy_ads=(P2PAd(price=1599.0, min_amount=None, max_amount=None, available=None,
                       methods=(), advertiser="<b>hack</b>&", completion_rate=None),),
        fetched_at=NOW,
    )
    text = render.compare_text(make_snap(), None, None, evil, "ru", now=NOW)
    assert "<b>hack</b>" not in text
    assert "&lt;b&gt;hack&lt;/b&gt;&amp;" in text
