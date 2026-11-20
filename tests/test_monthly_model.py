"""Тесты месячной модели кандидатов и производных статистик дашборда."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mts_templates.application.dto import BatchStatistics
from mts_templates.application.services.analysis_view import to_analysis_view
from mts_templates.domain.analytics.activity import TemplateMetrics
from mts_templates.domain.analytics.analysis import (
    DAYS_IN_MONTH,
    PARTIAL_PERIOD_DAYS,
    AnalysisRun,
    monthly_factor,
)
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money, Operator, Period

MSK = timezone(timedelta(hours=3))


def _period(days: int) -> Period:
    start = datetime(2026, 11, 1, 0, 0, tzinfo=MSK)
    return Period(start=start, end=start + timedelta(days=days - 1))


def test_full_period_is_not_scaled() -> None:
    assert monthly_factor(_period(30)) == Decimal(1)
    assert monthly_factor(_period(PARTIAL_PERIOD_DAYS)) == Decimal(1)


def test_partial_period_is_scaled_to_30_days() -> None:
    assert monthly_factor(_period(13)) == DAYS_IN_MONTH / Decimal(13)
    assert monthly_factor(_period(1)) == DAYS_IN_MONTH


def _run(period: Period) -> AnalysisRun:
    metrics = TemplateMetrics(
        template_id="t1",
        matched_messages=100,
        matched_segments=200,
        delivered_messages=90,
        unique_recipients=50,
        triggered_messages=80,
        off_operator_messages=10,
        actual_cost=Money.from_rub("400"),
        baseline_cost=Money.from_rub("1000"),
        template_fee=Money.from_rub("2000"),
        net_benefit=Money.from_rub("-1400"),
        trigger_rate=Decimal("0.8"),
        active=True,
    )
    return AnalysisRun(
        run_id="run-1",
        batch_id="batch-1",
        config_hash="hash",
        created_at=datetime(2026, 11, 1, 0, 0, tzinfo=MSK),
        period=period,
        message_count=100,
        matched_message_count=100,
        metrics=(metrics,),
        candidates=(),
    )


def _template() -> SmsTemplate:
    return SmsTemplate(
        template_id="t1",
        name="Шаблон",
        text="Текст %d",
        sender="TEST",
        operators=frozenset({Operator.T2, Operator.MTS}),
    )


def test_partial_period_scales_template_metrics_to_month() -> None:
    view = to_analysis_view(_run(_period(13)), (_template(),))

    metrics = view.metrics[0]
    assert view.is_partial_period is True
    assert metrics.monthly_messages == 231
    assert metrics.monthly_segments == 462
    assert metrics.monthly_actual_cost.rounded().amount == Decimal("923.08")
    assert metrics.monthly_baseline_cost.rounded().amount == Decimal("2307.69")
    assert metrics.monthly_net_benefit.rounded().amount == Decimal("-615.38")
    assert view.total_monthly_net_benefit.rounded().amount == Decimal("-615.38")
    assert metrics.matched_messages == 100
    assert metrics.net_benefit.rounded().amount == Decimal("-1400.00")


def test_full_period_metrics_are_not_scaled() -> None:
    view = to_analysis_view(_run(_period(30)), (_template(),))

    metrics = view.metrics[0]
    assert view.is_partial_period is False
    assert metrics.monthly_messages == 100
    assert metrics.monthly_segments == 200
    assert metrics.monthly_actual_cost.rounded().amount == Decimal("400.00")
    assert metrics.monthly_net_benefit.rounded().amount == Decimal("-1400.00")


def test_template_view_carries_registered_operators() -> None:
    view = to_analysis_view(_run(_period(30)), (_template(),))

    assert view.metrics[0].operators == ("MTS", "Tele2")


def _statistics() -> BatchStatistics:
    return BatchStatistics(
        message_count=100,
        segments=250,
        cost=Money.from_rub("1000"),
        delivered=90,
        ordinary_messages=40,
        ordinary_segments=120,
        ordinary_cost=Money.from_rub("400"),
        ordinary_rate=Money.from_rub("10"),
        templated_messages=60,
        templated_segments=130,
        templated_cost=Money.from_rub("600"),
        templated_rate=Money.from_rub("5"),
        senders=3,
    )


def test_statistics_averages_and_shares() -> None:
    statistics = _statistics()

    assert statistics.average_cost == Money.from_rub("10")
    assert statistics.ordinary_average_cost == Money.from_rub("10")
    assert statistics.templated_average_cost == Money.from_rub("10")
    assert statistics.average_segment_cost == Money.from_rub("4")
    assert statistics.ordinary_average_segment_cost == Money.from_rub("400") / 120
    assert statistics.templated_average_segment_cost == Money.from_rub("600") / 130
    assert statistics.delivered_share == 0.9
    assert statistics.ordinary_share == 0.4
    assert statistics.templated_share == 0.6
    assert statistics.ordinary_segment_share == 120 / 250
    assert statistics.templated_segment_share == 130 / 250
    assert statistics.average_segments == 2.5


def test_empty_statistics_has_no_averages() -> None:
    statistics = BatchStatistics(
        message_count=0,
        segments=0,
        cost=Money.zero(),
        delivered=0,
        ordinary_messages=0,
        ordinary_segments=0,
        ordinary_cost=Money.zero(),
        ordinary_rate=None,
        templated_messages=0,
        templated_segments=0,
        templated_cost=Money.zero(),
        templated_rate=None,
        senders=0,
    )

    assert statistics.average_cost is None
    assert statistics.ordinary_average_cost is None
    assert statistics.templated_average_cost is None
    assert statistics.average_segment_cost is None
    assert statistics.ordinary_average_segment_cost is None
    assert statistics.templated_average_segment_cost is None
    assert statistics.delivered_share == 0.0
    assert statistics.ordinary_share == 0.0
    assert statistics.templated_share == 0.0
    assert statistics.ordinary_segment_share == 0.0
    assert statistics.templated_segment_share == 0.0
    assert statistics.average_segments == 0.0
