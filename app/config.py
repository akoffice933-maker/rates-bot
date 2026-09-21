"""Конфигурация из переменных окружения (.env)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "es")          # es | ru
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
# Объём USDT по умолчанию, для которого CriptoYa считает цены с комиссиями
USDT_VOLUME_DEFAULT = int(os.getenv("USDT_VOLUME_DEFAULT", os.getenv("CRIPTOYA_VOLUME", "100")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Алерты
ALERT_POLL_SECONDS = int(os.getenv("ALERT_POLL_SECONDS", "60"))
ALERT_COOLDOWN_MINUTES = int(os.getenv("ALERT_COOLDOWN_MINUTES", "30"))
ALERT_HYSTERESIS_PCT = float(os.getenv("ALERT_HYSTERESIS_PCT", "0.2"))

# Binance P2P (прямые объявления).
# ВАЖНО: bapi блокирует дата-центровые IP (403 из песочницы — проверено 21.09.2026),
# для работы нужны резидентные AR-прокси в PROXY_LIST.
PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]
BINANCE_P2P_MIN_COMPLETION = float(os.getenv("BINANCE_P2P_MIN_COMPLETION", "0.90"))
BINANCE_P2P_PAGES = int(os.getenv("BINANCE_P2P_PAGES", "2"))
BINANCE_P2P_ROWS = int(os.getenv("BINANCE_P2P_ROWS", "10"))
