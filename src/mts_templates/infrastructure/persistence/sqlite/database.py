"""SQLite-хранилище приложения.

Соединение создаётся на поток: UI и фоновые задачи работают с одной базой,
WAL допускает параллельное чтение и запись.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _load_migrations() -> list[tuple[int, str]]:
    migrations: list[tuple[int, str]] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version_text, _, _ = path.stem.partition("_")
        try:
            version = int(version_text)
        except ValueError as exc:
            raise RuntimeError(f"Некорректное имя миграции: {path.name}") from exc
        migrations.append((version, path.read_text(encoding="utf-8")))
    if not migrations:
        raise RuntimeError(f"Не найдены миграции в {_MIGRATIONS_DIR}")
    return migrations


class Database:
    """Подключение к SQLite с миграциями, WAL и соединением на поток."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._local = threading.local()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is not None:
            return connection

        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        self._local.connection = connection
        return connection

    def migrate(self) -> None:
        connection = self.connect()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            int(row["version"])
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for version, script in _load_migrations():
            if version in applied:
                continue
            connection.executescript(script)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
            connection.commit()

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        return self.connect().execute(sql, parameters)

    def fetchall(self, sql: str, parameters: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        return list(self.connect().execute(sql, parameters).fetchall())

    def fetchone(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self.connect().execute(sql, parameters).fetchone()
        return row

    def close(self) -> None:
        """Закрыть соединение текущего потока.

        SQLite запрещает закрывать соединение из чужого потока, поэтому
        соединения фоновых потоков закрываются при завершении самих потоков.
        """
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            return
        connection.close()
        self._local = threading.local()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __iter__(self) -> Iterator[sqlite3.Row]:
        """Итератор по таблицам — удобно для диагностики."""
        return iter(self.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'"))
