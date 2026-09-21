"""Хранилище настроек чатов, алертов и дайджеста (SQLite).

chat_settings: язык, направление пары (direct/inverse), объём расчёта USDT.
alerts: подписки — спред USDT vs Blue и абсолютные курсы (blue, медианы USDT).
digest_subs: подписки на дайджест дня (час отправки, AR-время).
digest_history: ежедневные снимки ключевых значений (для дельт в дайджесте).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id    INTEGER PRIMARY KEY,
    lang       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

ALERTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    metric        TEXT NOT NULL,             -- spread_sell | spread_buy | blue_buyusd | blue_sellusd | usdt_buy | usdt_sell
    kind          TEXT NOT NULL,             -- spread | abs
    threshold     REAL NOT NULL,             -- % для spread; ARS для abs
    direction     TEXT NOT NULL DEFAULT 'above',  -- above | below (для abs)
    enabled       INTEGER NOT NULL DEFAULT 1,
    state         INTEGER NOT NULL DEFAULT 0,     -- 1 = условие активно, уведомление уже отправлено
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_fired_at TEXT,
    UNIQUE (chat_id, metric, direction, threshold)
)
"""

DIGEST_SUBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_subs (
    chat_id        INTEGER PRIMARY KEY,
    hour           INTEGER NOT NULL,          -- час отправки (AR-время)
    last_sent_date TEXT                       -- YYYY-MM-DD последней отправки
)
"""

DIGEST_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_history (
    date TEXT PRIMARY KEY,                    -- YYYY-MM-DD (AR)
    data TEXT NOT NULL                        -- JSON с ключевыми значениями
)
"""

# миграции chat_settings (v1.1: direction, v1.3: usdt_volume)
MIGRATIONS = (
    "ALTER TABLE chat_settings ADD COLUMN direction TEXT NOT NULL DEFAULT 'direct'",
    "ALTER TABLE chat_settings ADD COLUMN usdt_volume INTEGER NOT NULL DEFAULT 100",
)


@dataclass(frozen=True)
class Alert:
    id: int
    chat_id: int
    metric: str
    kind: str
    threshold: float
    direction: str
    enabled: bool
    active: bool              # условие выполнено, уведомление уже отправлено
    last_fired_at: datetime | None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _row_to_alert(row) -> Alert:
    return Alert(
        id=row[0],
        chat_id=row[1],
        metric=row[2],
        kind=row[3],
        threshold=row[4],
        direction=row[5],
        enabled=bool(row[6]),
        active=bool(row[7]),
        last_fired_at=_parse_dt(row[8]),
    )


_ALERT_COLUMNS = (
    "id, chat_id, metric, kind, threshold, direction, enabled, state, last_fired_at"
)


def _migrate_alerts_v12_to_v13(conn: sqlite3.Connection) -> None:
    """v1.2 (metric sell/buy + threshold_pct + was_above) -> v1.3 (метрики, threshold, direction, state)."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(alerts)")]
    if not cols or "threshold_pct" not in cols:
        return  # свежая БД или уже мигрирована
    conn.execute("ALTER TABLE alerts RENAME TO alerts_old")
    conn.execute(ALERTS_SCHEMA)
    conn.execute(
        """
        INSERT INTO alerts (chat_id, metric, kind, threshold, direction, enabled, state, created_at, last_fired_at)
        SELECT chat_id,
               CASE metric WHEN 'sell' THEN 'spread_sell' WHEN 'buy' THEN 'spread_buy' ELSE metric END,
               'spread', threshold_pct, 'above', enabled, was_above, created_at, last_fired_at
        FROM alerts_old
        """
    )
    conn.execute("DROP TABLE alerts_old")


class BotStorage:
    def __init__(self, path: str = "bot.db") -> None:
        self._path = path
        with closing(self._connect()) as conn, conn:
            conn.execute(SCHEMA)
            conn.execute(ALERTS_SCHEMA)
            conn.execute(DIGEST_SUBS_SCHEMA)
            conn.execute(DIGEST_HISTORY_SCHEMA)
            for sql in MIGRATIONS:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # колонка уже есть
            _migrate_alerts_v12_to_v13(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ---------- язык ----------

    def get_lang(self, chat_id: int, default: str = "es") -> str:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT lang FROM chat_settings WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row[0] if row else default

    def set_lang(self, chat_id: int, lang: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO chat_settings (chat_id, lang) VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE
                SET lang = excluded.lang, updated_at = datetime('now')
                """,
                (chat_id, lang),
            )

    # ---------- направление пары ----------

    def get_direction(self, chat_id: int) -> str:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT direction FROM chat_settings WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row[0] if row else "direct"

    def set_direction(self, chat_id: int, direction: str, lang: str = "es") -> None:
        if direction not in ("direct", "inverse"):
            raise ValueError(f"unknown direction: {direction}")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO chat_settings (chat_id, lang, direction) VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE
                SET direction = excluded.direction, updated_at = datetime('now')
                """,
                (chat_id, lang, direction),
            )

    # ---------- объём расчёта USDT ----------

    def get_volume(self, chat_id: int, default: int = 100) -> int:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT usdt_volume FROM chat_settings WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row[0] if row else default

    def set_volume(self, chat_id: int, volume: int, lang: str = "es") -> None:
        if not (1 <= volume <= 1_000_000):
            raise ValueError(f"volume out of range: {volume}")
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO chat_settings (chat_id, lang, usdt_volume) VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE
                SET usdt_volume = excluded.usdt_volume, updated_at = datetime('now')
                """,
                (chat_id, lang, volume),
            )

    # ---------- алерты ----------

    def list_alerts(self, chat_id: int | None = None) -> list[Alert]:
        query = f"SELECT {_ALERT_COLUMNS} FROM alerts WHERE enabled = 1"
        params: tuple = ()
        if chat_id is not None:
            query += " AND chat_id = ?"
            params = (chat_id,)
        query += " ORDER BY id"
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_alert(r) for r in rows]

    def add_alert(
        self,
        chat_id: int,
        metric: str,
        kind: str,
        threshold: float,
        direction: str = "above",
    ) -> bool:
        """True — создан, False — такой уже есть (дедупликация)."""
        if direction not in ("above", "below"):
            raise ValueError(f"unknown direction: {direction}")
        if kind not in ("spread", "abs"):
            raise ValueError(f"unknown kind: {kind}")
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO alerts (chat_id, metric, kind, threshold, direction)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, metric, kind, threshold, direction),
            )
            return cur.rowcount > 0

    def remove_alert(self, alert_id: int, chat_id: int) -> bool:
        """Удаление только своего алерта (chat_id — защита от чужих callback)."""
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE alerts SET enabled = 0 WHERE id = ? AND chat_id = ?",
                (alert_id, chat_id),
            )
            return cur.rowcount > 0

    def mark_fired(self, alert_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE alerts SET state = 1, last_fired_at = ? WHERE id = ?",
                (now, alert_id),
            )

    def set_active(self, alert_id: int, value: bool) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE alerts SET state = ? WHERE id = ?",
                (int(value), alert_id),
            )

    # ---------- дайджест ----------

    def digest_subscribe(self, chat_id: int, hour: int) -> None:
        """Подписка/смена часа; last_sent_date сохраняется (без дубля в день смены)."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO digest_subs (chat_id, hour) VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE
                SET hour = excluded.hour
                """,
                (chat_id, hour),
            )

    def digest_unsubscribe(self, chat_id: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM digest_subs WHERE chat_id = ?", (chat_id,))

    def digest_sub(self, chat_id: int) -> int | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT hour FROM digest_subs WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return row[0] if row else None

    def digest_due(self, hour: int, today: str) -> list[int]:
        """Чаты, чей час настал и которым сегодня ещё не отправляли."""
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT chat_id FROM digest_subs
                WHERE hour = ? AND (last_sent_date IS NULL OR last_sent_date != ?)
                """,
                (hour, today),
            ).fetchall()
        return [r[0] for r in rows]

    def digest_mark_sent(self, chat_id: int, today: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE digest_subs SET last_sent_date = ? WHERE chat_id = ?",
                (today, chat_id),
            )

    def save_digest_snapshot(self, date: str, data: dict) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO digest_history (date, data) VALUES (?, ?)",
                (date, json.dumps(data)),
            )

    def get_digest_snapshot(self, date: str) -> dict | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT data FROM digest_history WHERE date = ?", (date,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def last_digest_snapshot_before(self, date: str) -> dict | None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT data FROM digest_history WHERE date < ? ORDER BY date DESC LIMIT 1",
                (date,),
            ).fetchone()
        return json.loads(row[0]) if row else None
