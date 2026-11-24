"""Дневные серии сегментов: накопитель шаблона и инварианты прогона."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from mts_templates.domain.analytics.activity import DaySegments, TemplateActivity, TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun, CandidateGroup
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator, Period

MSK = timezone(timedelta(hours=3))


def _message(day: int, segments: int = 1) -> SmsMessage:
    return SmsMessage(
        message_id=f"m-{day}-{segments}",
        sent_at=datetime(2026, 11, day, 10, 0, tzinfo=MSK),
        recipient="79000000000",
        operator=Operator.MTS,
        sender="TEST",
        text="Текст",
        segments=segments,
        message_class=MessageClass.ORDINARY,
        cost=Money.zero(),
        delivered=True,
    )


def _metrics(
    *,
    daily_segments: tuple[DaySegments, ...] = (),
) -> TemplateMetrics:
    return TemplateMetrics(
        template_id="t1",
        matched_messages=1,
        matched_segments=1,
        delivered_messages=1,
        unique_recipients=1,
        triggered_messages=1,
        off_operator_messages=0,
        actual_cost=Money.zero(),
        baseline_cost=Money.zero(),
        template_fee=Money.zero(),
        net_benefit=Money.zero(),
        trigger_rate=Decimal("1"),
        active=True,
        daily_segments=daily_segments,
    )


def _candidate(
    *,
    segments: int = 1,
    daily_segments: tuple[DaySegments, ...] = (),
) -> CandidateGroup:
    return CandidateGroup(
        candidate_id="c1",
        template_text="Заказ %d готов",
        messages=1,
        segments=segments,
        actual_cost=Money.zero(),
        templated_cost=Money.zero(),
        monthly_saving=Money.zero(),
        template_fee=Money.zero(),
        net_monthly=Money.zero(),
        payback_months=None,
        confidence=Decimal("1"),
        coverage=Decimal("1"),
        senders=("TEST",),
        operators=(Operator.MTS,),
        period=Period(
            start=datetime(2026, 11, 1, 0, 0, tzinfo=MSK),
            end=datetime(2026, 11, 4, 23, 59, tzinfo=MSK),
        ),
        is_partial_period=False,
        daily_segments=daily_segments,
    )


def _run(
    metrics: tuple[TemplateMetrics, ...] = (),
    daily_segments: tuple[DaySegments, ...] = (),
    daily_templated_segments: tuple[DaySegments, ...] = (),
) -> AnalysisRun:
    return AnalysisRun(
        run_id="run-1",
        batch_id="batch-1",
        config_hash="hash",
        created_at=datetime(2026, 11, 1, 0, 0, tzinfo=MSK),
        period=Period(
            start=datetime(2026, 11, 1, 0, 0, tzinfo=MSK),
            end=datetime(2026, 11, 4, 23, 59, tzinfo=MSK),
        ),
        message_count=1,
        matched_message_count=1,
        metrics=metrics,
        candidates=(),
        daily_segments=daily_segments,
        daily_templated_segments=daily_templated_segments,
    )


def test_day_segments_reject_negative_value() -> None:
    with pytest.raises(ValueError):
        DaySegments(day=date(2026, 11, 1), segments=-1)


def test_template_activity_accumulates_matched_segments_by_day() -> None:
    activity = TemplateActivity("t1")
    activity.add(_message(1, 2), Money.zero(), operator_listed=True)
    activity.add(_message(1, 3), Money.zero(), operator_listed=True)
    activity.add(_message(2, 1), Money.zero(), operator_listed=True)

    metrics = activity.to_metrics(monthly_fee=Money.zero())

    assert [(item.day, item.segments) for item in metrics.daily_segments] == [
        (date(2026, 11, 1), 5),
        (date(2026, 11, 2), 1),
    ]


def test_template_metrics_reject_duplicate_days() -> None:
    day = DaySegments(day=date(2026, 11, 1), segments=1)

    with pytest.raises(ValueError):
        _metrics(daily_segments=(day, day))


def test_run_rejects_duplicate_days() -> None:
    day = DaySegments(day=date(2026, 11, 1), segments=1)

    with pytest.raises(ValueError):
        _run(daily_segments=(day, day))


def test_run_rejects_template_segments_above_daily_traffic() -> None:
    day = date(2026, 11, 1)
    metrics = _metrics(daily_segments=(DaySegments(day=day, segments=5),))

    with pytest.raises(ValueError):
        _run(metrics=(metrics,), daily_segments=(DaySegments(day=day, segments=4),))


def test_run_rejects_templated_segments_above_daily_traffic() -> None:
    day = date(2026, 11, 1)

    with pytest.raises(ValueError):
        _run(
            daily_segments=(DaySegments(day=day, segments=4),),
            daily_templated_segments=(DaySegments(day=day, segments=5),),
        )


def test_run_rejects_duplicate_templated_days() -> None:
    day = DaySegments(day=date(2026, 11, 1), segments=1)

    with pytest.raises(ValueError):
        _run(daily_templated_segments=(day, day))


def test_run_accepts_templated_segments_within_daily_traffic() -> None:
    day = date(2026, 11, 1)

    run = _run(
        daily_segments=(DaySegments(day=day, segments=10),),
        daily_templated_segments=(DaySegments(day=day, segments=6),),
    )

    assert run.daily_templated_segments == (DaySegments(day=day, segments=6),)


def test_run_accepts_template_segments_within_daily_traffic() -> None:
    day = date(2026, 11, 1)
    metrics = _metrics(daily_segments=(DaySegments(day=day, segments=4),))

    run = _run(metrics=(metrics,), daily_segments=(DaySegments(day=day, segments=10),))

    assert run.daily_segments == (DaySegments(day=day, segments=10),)


def test_candidate_rejects_duplicate_days() -> None:
    day = DaySegments(day=date(2026, 11, 1), segments=1)

    with pytest.raises(ValueError):
        _candidate(segments=2, daily_segments=(day, day))


def test_candidate_rejects_daily_total_mismatch() -> None:
    with pytest.raises(ValueError):
        _candidate(
            segments=5,
            daily_segments=(DaySegments(day=date(2026, 11, 1), segments=4),),
        )


def test_candidate_accepts_matching_daily_series() -> None:
    candidate = _candidate(
        segments=3,
        daily_segments=(
            DaySegments(day=date(2026, 11, 1), segments=1),
            DaySegments(day=date(2026, 11, 2), segments=2),
        ),
    )

    assert sum(item.segments for item in candidate.daily_segments) == candidate.segments
