"""Локализованное меню команд: ru по умолчанию, es для испаноязычных клиентов."""
import re

from app.main import BOT_COMMANDS, build_bot_commands


def test_commands_have_both_languages():
    for cmd, spec in BOT_COMMANDS.items():
        assert re.fullmatch(r"[a-z0-9_]+", cmd), cmd
        assert spec.get("es") and spec.get("ru"), cmd
        assert len(spec["es"]) <= 256 and len(spec["ru"]) <= 256, cmd


def test_build_bot_commands():
    ru = build_bot_commands("ru")
    es = build_bot_commands("es")
    assert [c.command for c in ru] == [c.command for c in es]
    assert len(ru) == len(BOT_COMMANDS)
    ru_map = {c.command: c.description for c in ru}
    assert ru_map["start"] == "Главное меню"
    assert ru_map["help"] == "Справка"
    es_map = {c.command: c.description for c in es}
    assert es_map["start"] == "Menú principal"
    # оба списка — переводы друг друга, а не копии
    assert ru_map["rates"] != es_map["rates"]


def test_key_commands_present():
    for cmd in ("start", "rates", "usdt", "usdtusd", "compare", "p2p", "spread",
                "alert", "digest", "how", "bestchange", "ratesguru", "history",
                "calc", "lang", "help"):
        assert cmd in BOT_COMMANDS
