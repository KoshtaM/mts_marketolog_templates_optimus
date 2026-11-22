"""Сегменты по дням и операторам: SQL-агрегат, пропущенные дни и шкала оси Y."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from mts_templates.application.dto import DailyOperatorSegments, DailySegments
from mts_templates.application.use_cases.dashboard import fill_period_days
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.query_repository import (
    SqliteMessageQueryRepository,
)
from mts_templates.presentation.desktop.daily_chart import build_daily_chart, nice_scale
from mts_templates.presentation.desktop.operator_colors import OTHER_COLOR, operator_color

BATCH_ID = "batch-1"

# (день отправки, оператор получателя, сегменты)
Entry = tuple[str, str, int]

ENTRIES: tuple[Entry, ...] = (
    ("2026-11-02", "MTS", 3),
    ("2026-11-02", "MTS", 4),
    ("2026-11-02", "Beeline", 2),
    ("2026-11-01", "Tele2", 5),
    ("2026-11-01", "MTS", 1),
    ("2026-11-03", "Beeline", 0),
)


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
    for index, (day, operator, segments) in enumerate(entries, start=1):
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
                f"{day}T10:00:00+03:00",
                "79000000001",
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


def daily(db: Database) -> tuple[DailySegments, ...]:
    return SqliteMessageQueryRepository(db).daily_segments(BATCH_ID)


def test_daily_segments_group_by_day_and_operator(database: Database) -> None:
    fill(database, ENTRIES)

    result = daily(database)

    assert [
        (item.day, [(part.operator, part.segments) for part in item.operators]) for item in result
    ] == [
        (date(2026, 11, 1), [("Tele2", 5), ("MTS", 1)]),
        (date(2026, 11, 2), [("MTS", 7), ("Beeline", 2)]),
    ]


def test_daily_segments_skip_days_without_sent_segments(database: Database) -> None:
    fill(database, ENTRIES)

    days = [item.day for item in daily(database)]

    assert date(2026, 11, 3) not in days


def test_daily_segments_total_is_the_sum_of_operators(database: Database) -> None:
    fill(database, ENTRIES)

    assert [item.segments for item in daily(database)] == [6, 9]


def test_daily_segments_of_empty_batch_are_empty(database: Database) -> None:
    assert daily(database) == ()


def test_fill_period_days_adds_missing_days_in_order() -> None:
    existing = (DailySegments(day=date(2026, 11, 1)), DailySegments(day=date(2026, 11, 3)))

    filled = fill_period_days(existing, date(2026, 11, 1), date(2026, 11, 4))

    assert [item.day for item in filled] == [
        date(2026, 11, 1),
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
    ]
    assert [item.segments for item in filled] == [0, 0, 0, 0]


def test_fill_period_days_keeps_days_outside_the_period() -> None:
    existing = (DailySegments(day=date(2026, 10, 31)),)

    filled = fill_period_days(existing, date(2026, 11, 1), date(2026, 11, 2))

    assert [item.day for item in filled] == [date(2026, 11, 1), date(2026, 11, 2)]


@pytest.mark.parametrize(("start", "end"), [(None, date(2026, 11, 1)), (date(2026, 11, 1), None)])
def test_fill_period_days_without_bounds_returns_source(start, end) -> None:
    existing = (DailySegments(day=date(2026, 11, 3)),)

    assert fill_period_days(existing, start, end) == existing


def test_fill_period_days_with_reversed_bounds_returns_source() -> None:
    existing = (DailySegments(day=date(2026, 11, 3)),)

    assert fill_period_days(existing, date(2026, 11, 4), date(2026, 11, 1)) == existing


def test_build_daily_chart_keeps_operator_order_inside_each_day() -> None:
    daily_items = (
        DailySegments(
            day=date(2026, 11, 1),
            operators=(
                DailyOperatorSegments("Beeline", 7),
                DailyOperatorSegments("MTS", 2),
            ),
        ),
    )

    chart = build_daily_chart(daily_items)

    assert [(segment.label, segment.value) for segment in chart.bars[0].segments] == [
        ("Beeline", 7.0),
        ("MTS", 2.0),
    ]
    assert chart.bars[0].label == "01.11"
    assert chart.bars[0].total == 9.0


def test_build_daily_chart_colors_match_operator_colors() -> None:
    daily_items = (
        DailySegments(
            day=date(2026, 11, 1),
            operators=(DailyOperatorSegments("MTS", 3), DailyOperatorSegments("Unknown op", 1)),
        ),
    )

    chart = build_daily_chart(daily_items)

    colors = [segment.color for segment in chart.bars[0].segments]
    assert colors == [operator_color("MTS"), OTHER_COLOR]


def test_build_daily_chart_legend_orders_operators_by_period_total() -> None:
    daily_items = (
        DailySegments(
            day=date(2026, 11, 1),
            operators=(DailyOperatorSegments("MTS", 5), DailyOperatorSegments("Beeline", 1)),
        ),
        DailySegments(
            day=date(2026, 11, 2),
            operators=(DailyOperatorSegments("Beeline", 9), DailyOperatorSegments("Tele2", 1)),
        ),
    )

    chart = build_daily_chart(daily_items)

    assert [name for name, _ in chart.legend] == ["Beeline", "MTS", "Tele2"]
    assert chart.caption == "всего 16 сегментов"


def test_build_daily_chart_keeps_empty_days_as_bars_without_segments() -> None:
    chart = build_daily_chart((DailySegments(day=date(2026, 11, 1)),))

    assert len(chart.bars) == 1
    assert chart.bars[0].segments == ()
    assert chart.caption == ""


def test_build_daily_chart_of_no_days_is_empty() -> None:
    assert build_daily_chart(()).bars == ()


@pytest.mark.parametrize(("max_value", "expected"), [(0, (1, 0)), (1, (1, 1)), (100, (25, 100))])
def test_nice_scale_returns_round_ticks(max_value: int, expected: tuple[int, int]) -> None:
    assert nice_scale(max_value) == expected


@pytest.mark.parametrize("max_value", [7, 55, 137, 640, 12_345, 1_000_000])
def test_nice_scale_covers_the_peak_with_a_round_step(max_value: int) -> None:
    step, top = nice_scale(max_value)

    assert top >= max_value
    assert top % step == 0
    assert step <= top
