"""Загрузка фикстур — реальных ответов источников, снятых 21.09.2026 (Day-0 spike)."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text())
