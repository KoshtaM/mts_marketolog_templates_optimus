"""Агрегаты по абонентам и распределениям SMS-сегментов на синтетической БД."""

from __future__ import annotations

from pathlib import Path

import pytest

from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.query_repository import (
    SqliteMessageQueryRepository,
)

BATCH_ID = "batch-1"

# (номер получателя, оператор, сегменты каждого сообщения)
Entry = tuple[str, str, tuple[int, ...]]

BASE_ENTRIES: tuple[Entry, ...] = (
    ("79000000001", "MTS", (1, 2)),
    ("79000000002", "MTS", (2,)),
    ("79000000003", "Beeline", (1,)),
    ("79000000005", "MTS", (1, 1, 1)),
    # Два сообщения у MTS и одно у Beeline: оператор абонента — MTS.
    ("79000000006", "MTS", (1, 1)),
    ("79000000006", "Beeline", (2,)),
    ("79000000007", "MTS", (1,)),
)
ERROR_ONLY_ENTRY: Entry = ("79000000004", "Beeline", (0,))


@pytest.fixture
def database(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.migrate()
    db.execute(
        """
        INSERT INTO import_batches
            (id, source_path, source_sha256, kind, imported_at, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (BATCH_ID, "test.xlsx", "hash", "statistics", "2026-11-13T00:00:00+03:00", "ok"),
    )
    yield db
    db.close()


def fill(db: Database, entries: tuple[Entry, ...]) -> None:
    index = 0
    for recipient, operator, segments_list in entries:
        for segments in segments_list:
            index += 1
            db.execute(
                """
                INSERT INTO messages
                    (id, batch_id, sent_at, recipient, operator, sender, text,
                     segments, message_class, cost_kopecks, delivered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"message-{index}",
                    BATCH_ID,
                    "2026-11-13T10:00:00+03:00",
                    recipient,
                    operator,
                    "TEST",
                    "text",
                    segments,
                    "ordinary",
                    0,
                    1,
                ),
            )
    db.connection.commit()


def statistics(db: Database):
    return SqliteMessageQueryRepository(db).segmentation_statistics(BATCH_ID)


def test_subscriber_totals_exclude_error_only_recipients(database: Database) -> None:
    fill(database, (*BASE_ENTRIES, ERROR_ONLY_ENTRY))

    stats = statistics(database)

    assert stats.subscribers == 6
    assert stats.subscriber_segments == 14
    assert stats.subscriber_messages == 11
    assert stats.zero_segment_messages == 1
    assert stats.average_subscriber_segments == pytest.approx(14 / 6)
    assert stats.average_subscriber_messages == pytest.approx(11 / 6)


def test_subscribers_by_segments_sum_message_segments_per_recipient(database: Database) -> None:
    fill(database, (*BASE_ENTRIES, ERROR_ONLY_ENTRY))

    stats = statistics(database)

    by_segments = {bucket.segments: bucket for bucket in stats.subscribers_by_segments}
    assert sorted(by_segments) == [1, 2, 3, 4]
    assert by_segments[1].count == 2
    assert by_segments[2].count == 1
    assert by_segments[3].count == 2
    assert by_segments[4].count == 1
    assert sum(bucket.count for bucket in stats.subscribers_by_segments) == stats.subscribers
    assert by_segments[2].share == pytest.approx(1 / 6)


def test_subscriber_operator_is_the_one_with_most_messages(database: Database) -> None:
    fill(database, (*BASE_ENTRIES, ERROR_ONLY_ENTRY))

    stats = statistics(database)

    by_operator = {item.operator: item for item in stats.subscribers_by_operator}
    assert by_operator["MTS"].subscribers == 5
    assert by_operator["Beeline"].subscribers == 1
    assert by_operator["MTS"].share == pytest.approx(5 / 6)
    assert sum(item.subscribers for item in stats.subscribers_by_operator) == stats.subscribers


def test_tie_between_operators_goes_to_alphabetically_first(database: Database) -> None:
    fill(
        database,
        (
            ("79000000010", "MTS", (1,)),
            ("79000000010", "Beeline", (1,)),
        ),
    )

    stats = statistics(database)

    assert [(item.operator, item.subscribers) for item in stats.subscribers_by_operator] == [
        ("Beeline", 1)
    ]


def test_messages_by_segments_exclude_zero_segment_messages(database: Database) -> None:
    fill(database, (*BASE_ENTRIES, ERROR_ONLY_ENTRY))

    stats = statistics(database)

    by_segments = {bucket.segments: bucket for bucket in stats.messages_by_segments}
    assert by_segments[1].count == 8
    assert by_segments[2].count == 3
    assert 0 not in by_segments
    assert by_segments[1].share == pytest.approx(8 / 11)
    assert sum(bucket.count for bucket in stats.messages_by_segments) == stats.subscriber_messages


def test_batch_without_sent_messages_has_zero_averages(database: Database) -> None:
    fill(database, (ERROR_ONLY_ENTRY,))

    stats = statistics(database)

    assert stats.subscribers == 0
    assert stats.subscribers_by_segments == ()
    assert stats.subscribers_by_operator == ()
    assert stats.messages_by_segments == ()
    assert stats.zero_segment_messages == 1
    assert stats.average_subscriber_segments == 0.0
    assert stats.average_subscriber_messages == 0.0
