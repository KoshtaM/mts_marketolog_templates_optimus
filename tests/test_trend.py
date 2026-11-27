"""Тесты истории шаблонов: тренд по загрузкам и сигнал деградации."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mts_templates.domain.analytics.activity import TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun
from mts_templates.domain.analytics.trend import (
    TemplateTrend,
    TemplateTrendPoint,
    build_template_trend,
    detect_deterioration,
)
from mts_templates.domain.value_objects import Money, Period

MSK = timezone(timedelta(hours=3))


def _period(offset_days: int) -> Period:
    start = datetime(2026, 11, 1, tzinfo=MSK) + timedelta(days=offset_days)
    return Period(start=start, end=start + timedelta(days=13))


def _metrics(template_id: str, *, triggered: int, segments: int) -> TemplateMetrics:
    return TemplateMetrics(
        template_id=template_id,
        matched_messages=max(triggered, 1),
        matched_segments=segments,
        delivered_messages=segments,
        unique_recipients=1,
        triggered_messages=triggered,
        off_operator_messages=0,
        actual_cost=Money.from_rub("100"),
        baseline_cost=Money.from_rub("100"),
        template_fee=Money.from_rub("2000"),
        net_benefit=Money.from_rub("-100"),
        trigger_rate=Decimal(triggered) / Decimal(max(segments, 1)),
        active=True,
    )


def _run(
    batch_id: str,
    period: Period,
    template_id: str,
    *,
    triggered: int,
    segments: int,
) -> AnalysisRun:
    return AnalysisRun(
        run_id=f"run-{batch_id}",
        batch_id=batch_id,
        config_hash="hash",
        created_at=datetime(2026, 11, 20, tzinfo=MSK),
        period=period,
        message_count=segments,
        matched_message_count=max(triggered, 1),
        metrics=(_metrics(template_id, triggered=triggered, segments=segments),),
        candidates=(),
    )


def _point(batch_id: str, period: Period, triggered: int, segments: int) -> TemplateTrendPoint:
    return TemplateTrendPoint(
        template_id="t1",
        batch_id=batch_id,
        period=period,
        segments=segments,
        triggered_messages=triggered,
        trigger_rate=Decimal(triggered) / Decimal(max(segments, 1)),
        net_benefit=Money.from_rub("-100"),
    )


def test_trend_builds_points_in_period_order() -> None:
    trend = build_template_trend(
        (
            _run("batch-2", _period(13), "t1", triggered=3, segments=6),
            _run("batch-1", _period(0), "t1", triggered=5, segments=9),
        ),
        "t1",
    )

    assert isinstance(trend, TemplateTrend)
    assert trend.template_id == "t1"
    assert [point.batch_id for point in trend.points] == ["batch-1", "batch-2"]


def test_trend_without_metrics_has_no_points() -> None:
    runs = (_run("batch-1", _period(0), "t1", triggered=1, segments=1),)
    assert build_template_trend(runs, "other").points == ()


def test_deterioration_detects_stopped_triggering() -> None:
    trend = TemplateTrend(
        template_id="t1",
        points=(
            _point("batch-1", _period(0), triggered=5, segments=9),
            _point("batch-2", _period(13), triggered=0, segments=0),
        ),
    )

    deterioration = detect_deterioration(trend)

    assert deterioration is not None
    assert deterioration.template_id == "t1"
    assert deterioration.previous_triggered_messages == 5
    assert deterioration.current_triggered_messages == 0
    assert deterioration.previous_trigger_rate == Decimal(5) / Decimal(9)
    assert deterioration.current_trigger_rate == Decimal(0)


def test_no_deterioration_when_triggering_continued() -> None:
    trend = TemplateTrend(
        template_id="t1",
        points=(
            _point("batch-1", _period(0), triggered=5, segments=9),
            _point("batch-2", _period(13), triggered=2, segments=4),
        ),
    )

    assert detect_deterioration(trend) is None


def test_no_deterioration_with_single_point() -> None:
    trend = TemplateTrend(
        template_id="t1", points=(_point("batch-1", _period(0), triggered=1, segments=2),)
    )

    assert detect_deterioration(trend) is None
