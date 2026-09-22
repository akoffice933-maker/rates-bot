"""Точка входа: long polling (публичный IP и вебхуки не нужны) + фоновый воркер
(алерты каждые ALERT_POLL_SECONDS + отправка дайджестов).

Запуск: BOT_TOKEN=... python -m app.main
"""
from __future__ import annotations

import asyncio
import logging
import sys

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from . import config
from .alerts import AlertManager, alert_worker
from .bestchange import BestChangeService
from .ratesguru import RatesGuruService
from .digest import DigestManager
from .handlers import router
from .http_client import AiohttpClient
from .p2p import BinanceP2PService
from .service import RatesService
from .storage import BotStorage, RateHistoryStore


BOT_COMMANDS: dict[str, dict[str, str]] = {
    "start":     {"es": "Menú principal",                          "ru": "Главное меню"},
    "rates":     {"es": "Cotizaciones del dólar",                  "ru": "Котировки доллара"},
    "usdt":      {"es": "Mejores precios USDT/ARS",                "ru": "Лучшие цены USDT/ARS"},
    "usdtusd":   {"es": "USDT ⇄ USD (efectivo/sin efectivo)",      "ru": "USDT ⇄ USD (нал/безнал)"},
    "compare":   {"es": "Comparar fuentes USDT/ARS",               "ru": "Сравнить источники USDT/ARS"},
    "p2p":       {"es": "Binance P2P en vivo",                     "ru": "Binance P2P вживую"},
    "spread":    {"es": "Brecha USDT vs Blue",                     "ru": "Спред USDT к Blue"},
    "alert":     {"es": "Alertas de brecha y cotización",          "ru": "Алерты: спред и курсы"},
    "digest":    {"es": "Resumen diario",                          "ru": "Ежедневный дайджест"},
    "how":       {"es": "Cómo cambiar / как обменять",             "ru": "Как обменять / cómo cambiar"},
    "bestchange": {"es": "Intercambiadores BestChange",            "ru": "Обменники BestChange"},
    "ratesguru": {"es": "Intercambiadores RatesGuru (RUB/USDT)",   "ru": "Обменники RatesGuru (RUB/USDT)"},
    "history":   {"es": "Dinámica 24h/7d/30d",                     "ru": "Динамика 24ч/7д/30д"},
    "calc":      {"es": "Calculadora de cambio",                   "ru": "Калькулятор обмена"},
    "lang":      {"es": "Idioma / язык",                           "ru": "Язык / idioma"},
    "help":      {"es": "Ayuda",                                   "ru": "Справка"},
}


def build_bot_commands(lang: str) -> list[BotCommand]:
    return [BotCommand(command=c, description=spec[lang]) for c, spec in BOT_COMMANDS.items()]


async def set_bot_commands(bot: Bot) -> None:
    """Локализованное меню команд: русский — по умолчанию, испанский — для es-клиентов.

    Telegram показывает список под язык клиента (language_code="es"),
    остальным — дефолтный (ru).
    """
    await bot.set_my_commands(build_bot_commands("ru"))
    await bot.set_my_commands(build_bot_commands("es"), language_code="es")


async def run() -> None:
    storage = BotStorage(config.DB_PATH)
    session = aiohttp.ClientSession()
    client = AiohttpClient(session, timeout=config.HTTP_TIMEOUT)
    service = RatesService(
        client,
        cache_ttl_seconds=config.CACHE_TTL_SECONDS,
        default_volume=config.USDT_VOLUME_DEFAULT,
    )
    p2p = BinanceP2PService(
        client,
        proxies=config.PROXY_LIST,
        min_completion_rate=config.BINANCE_P2P_MIN_COMPLETION,
        pages=config.BINANCE_P2P_PAGES,
        rows=config.BINANCE_P2P_ROWS,
    )
    history = RateHistoryStore(config.HISTORY_DB_PATH)
    alerts = AlertManager(
        storage,
        cooldown_minutes=config.ALERT_COOLDOWN_MINUTES,
        hysteresis_pct=config.ALERT_HYSTERESIS_PCT,
    )
    digest = DigestManager(storage)

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp["service"] = service
    dp["storage"] = storage
    dp["p2p"] = p2p
    dp["bestchange"] = BestChangeService(client)
    dp["ratesguru"] = RatesGuruService(client)
    dp["history"] = history
    dp.include_router(router)

    await set_bot_commands(bot)
    worker = asyncio.create_task(
        alert_worker(
            bot, service, alerts, digest, config.ALERT_POLL_SECONDS,
            history=history, history_interval_seconds=config.HISTORY_INTERVAL_SECONDS,
        )
    )
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info(
            "старт long polling (алерты каждые %s c; binance p2p: %s)",
            config.ALERT_POLL_SECONDS,
            f"{len(config.PROXY_LIST)} прокси" if config.PROXY_LIST else "без прокси (ожидаем 403)",
        )
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        await bot.session.close()
        await session.close()


def main() -> int:
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not config.BOT_TOKEN:
        print(
            "BOT_TOKEN не задан. Скопируй .env.example в .env и укажи токен от @BotFather.",
            file=sys.stderr,
        )
        return 2
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logging.info("бот остановлен")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
