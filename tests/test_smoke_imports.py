"""Smoke-тесты: модули импортируются, имена в хендлерах реально определены.

Ловит класс багов «edit применился в один файл, но не в зависимый»:
NameError в рантайме вместо ошибки импорта.
"""
from __future__ import annotations


def test_import_all_modules():
    import app.alerts  # noqa: F401
    import app.handlers  # noqa: F401
    import app.keyboards  # noqa: F401
    import app.main  # noqa: F401
    import app.render  # noqa: F401
    import app.storage  # noqa: F401
    import app.venue_links  # noqa: F401

    import app.handlers as h

    assert h.router is not None


def test_handlers_namespaces_resolved():
    """Все имена, используемые в хендлерах, должны быть доступны в их пространстве."""
    import app.handlers as h

    for name in (
        "links_kb",
        "lang_kb",
        "main_menu",
        "screen_kb",
        "alert_kb",
        "alert_categories_kb",
        "alert_direction_kb",
        "alert_value_kb",
        "render",
        "METRICS",
    ):
        assert hasattr(h, name), f"handlers: имя {name!r} не определено (проверь импорты)"
