"""Тесты SQLite-схемы."""

from __future__ import annotations

import threading
from pathlib import Path

from mts_templates.infrastructure.persistence.sqlite.database import Database

EXPECTED_TABLES = {
    "schema_migrations",
    "import_batches",
    "messages",
    "billing_rows",
    "templates",
    "analysis_runs",
    "template_metrics",
    "candidate_groups",
}


def test_migrate_creates_schema(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()

    tables = {
        row["name"] for row in db.fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert tables >= EXPECTED_TABLES

    versions = [row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")]
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8]

    db.close()


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()
    db.migrate()

    versions = [row["version"] for row in db.fetchall("SELECT version FROM schema_migrations")]
    assert versions == [1, 2, 3, 4, 5, 6, 7, 8]

    db.close()


def test_close_after_worker_thread_does_not_fail(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()

    worker = threading.Thread(target=db.fetchall, args=("SELECT name FROM sqlite_master",))
    worker.start()
    worker.join()

    db.close()


def test_segment_sum_migration_recalculates_segments(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()
    db.execute(
        """
        INSERT INTO import_batches
            (id, source_path, source_sha256, kind, imported_at, status, segment_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("batch-1", "test.xlsx", "hash", "statistics", "2026-11-13T00:00:00+03:00", "ok", 3),
    )
    db.execute(
        """
        INSERT INTO messages
            (id, batch_id, sent_at, recipient, operator, sender, text,
             segments, message_class, cost_kopecks, delivered)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "message-1",
            "batch-1",
            "2026-11-13T00:00:00+03:00",
            "79000000000",
            "MTS",
            "TEST",
            "text",
            3,
            "ordinary",
            3500,
            1,
        ),
    )
    for segments in (2, 3):
        db.execute(
            """
            INSERT INTO billing_rows
                (message_id, package_type, price_per_segment_kopecks, cost_kopecks, segments)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("message-1", "Подписка", 1000, 1750, segments),
        )
    db.execute(
        """
        INSERT INTO analysis_runs (id, batch_id, config_hash, created_at, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("run-1", "batch-1", "hash", "2026-11-13T00:00:00+03:00", "{}"),
    )
    db.execute("DELETE FROM schema_migrations WHERE version = 6")
    db.connection.commit()

    db.migrate()

    assert (
        db.fetchone("SELECT segments FROM messages WHERE id = ?", ("message-1",))["segments"] == 5
    )
    assert db.fetchone("SELECT segment_count FROM import_batches")["segment_count"] == 5
    assert db.fetchone("SELECT COUNT(*) AS count FROM analysis_runs")["count"] == 0
    db.close()


def test_foreign_keys_cascade(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.migrate()

    db.execute(
        """
        INSERT INTO import_batches
            (id, source_path, source_sha256, kind, imported_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("batch-1", "test.xlsx", "hash", "statistics", "2026-11-13T00:00:00+03:00", "ok"),
    )
    db.execute(
        """
        INSERT INTO messages
            (id, batch_id, sent_at, recipient, operator, sender, text,
             segments, message_class, cost_kopecks, delivered)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "message-1",
            "batch-1",
            "2026-11-13T00:00:00+03:00",
            "79000000000",
            "MTS",
            "TEST",
            "text",
            1,
            "ordinary",
            754,
            1,
        ),
    )
    db.connection.commit()

    assert db.fetchone("SELECT COUNT(*) AS count FROM messages")["count"] == 1

    db.execute("DELETE FROM import_batches WHERE id = ?", ("batch-1",))
    db.connection.commit()

    assert db.fetchone("SELECT COUNT(*) AS count FROM messages")["count"] == 0

    db.close()
