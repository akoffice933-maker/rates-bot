"""Dry-run без Telegram: живые данные, все экраны, демо P2P и дайджеста.

Запуск: python -m app.dryrun  (BOT_TOKEN не нужен)
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp

from . import config, render
from .alerts import AlertManager
from .digest import AR_TZ, DigestManager, digest_text
from .http_client import AiohttpClient
from .p2p import BinanceP2PService
from .service import RatesService
from .storage import BotStorage


def strip_html(text: str) -> str:
    """Убираем HTML-теги; ссылки показываем как «текст (url)»."""
    text = re.sub(r'<a href="([^"]+)">(.*?)</a>', r"\2 [\1]", text)
    return text.replace("<b>", "").replace("</b>", "")


class PrintBot:
    """Вместо Telegram — печатаем сообщения в консоль."""

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        print(f"[→ chat {chat_id}]")
        print(strip_html(text))
        print()


async def main() -> None:
    session = aiohttp.ClientSession()
    try:
        client = AiohttpClient(session, timeout=config.HTTP_TIMEOUT)
        service = RatesService(
            client,
            cache_ttl_seconds=config.CACHE_TTL_SECONDS,
            default_volume=config.USDT_VOLUME_DEFAULT,
        )
        snap = await service.get_snapshot(force=True)
        print(f"# fetched_at={snap.fetched_at.isoformat()} errors={list(snap.source_errors)}")
        print()

        # ---- /p2p: живой запрос Binance (из песочницы ожидаем 403 → fallback) ----
        print("=" * 60)
        print("[demo] /p2p — Binance P2P (прямые объявления, без прокси)")
        print("=" * 60)
        p2p = BinanceP2PService(client, proxies=config.PROXY_LIST, pages=1, rows=10)
        result = await p2p.get()
        print(f"# ok={result.ok} error={result.error}")
        print(strip_html(render.p2p_text(result, snap, "ru") or "нет данных"))
        print()

        # ---- дайджест: рендер текущего + с дельтой ко «вчера» ----
        print("=" * 60)
        print("[demo] дайджест дня (ru)")
        print("=" * 60)
        now_ar = datetime.now(timezone.utc).astimezone(AR_TZ)
        print(strip_html(digest_text(snap, None, "ru", now_ar)))
        print()
        print("-- с дельтами (вчера blue sell = 1500, медиана bid = 1530):")
        prev = {
            "blue_sell": 1500.0,
            "oficial_sell": 1530.0,
            "usdt_median_bid": 1530.0,
            "usdt_median_ask": 1560.0,
        }
        print(strip_html(digest_text(snap, prev, "ru", now_ar)))
        print()

        # ---- дайджест: отправка по подписке (имитация времени) ----
        print("=" * 60)
        print("[demo] проверка подписок дайджеста (подписка на текущий час)")
        print("=" * 60)
        with tempfile.TemporaryDirectory() as td:
            storage = BotStorage(os.path.join(td, "demo.db"))
            storage.set_lang(1, "ru")
            storage.digest_subscribe(1, now_ar.hour)
            manager = DigestManager(storage)
            sent = await manager.check(PrintBot(), snap, now=datetime.now(timezone.utc))
            print(f"# отправлено: {sent} (ожидалось 1)")
            sent2 = await manager.check(PrintBot(), snap, now=datetime.now(timezone.utc))
            print(f"# повторная проверка в тот же день: {sent2} (ожидалось 0 — без дублей)")
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
