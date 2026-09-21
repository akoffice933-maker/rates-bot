"""Санити-тесты словарей локализации."""
from __future__ import annotations

from app.i18n import STRINGS, t


def test_es_ru_keys_parity():
    """Наборы ключей es и ru должны совпадать — иначе где-то будет испанский текст."""
    assert set(STRINGS["es"]) == set(STRINGS["ru"])


def test_t_fallback_and_format():
    assert t("ru", "BTN_REFRESH") == "🔄 Обновить"
    assert t("es", "BTN_REFRESH") == "🔄 Actualizar"
    # неизвестный язык -> es
    assert t("xx", "BTN_REFRESH") == "🔄 Actualizar"
    # подстановка параметров
    assert t("ru", "BTN_SWAP", pair="ARS/USD") == "🔁 ARS/USD"
    assert "30" in t("ru", "ALERT_HOW", poll=60, cooldown=30)
