"""Тесты наблюдаемых ставок и разбивки по операторам."""

from __future__ import annotations

from datetime import datetime

from mts_templates.application.services.analysis_view import to_analysis_view
from mts_templates.domain.analytics.activity import OperatorTrigger
from mts_templates.domain.analytics.analysis import AnalysisRun
from mts_templates.domain.analytics.baseline import build_observed_rates
from mts_templates.domain.value_objects import MessageClass, Money, Operator, Period
from tests.helpers import MSK, make_message


def test_class_average_counts_zero_cost_and_undelivered_segments() -> None:
    messages = [
        make_message(
            "t1",
            message_class=MessageClass.TEMPLATED,
            cost=Money.from_rub("10"),
        ),
        make_message(
            "t2",
            message_class=MessageClass.TEMPLATED,
            cost=Money.zero(),
            segments=1,
        ),
        make_message("o1", cost=Money.from_rub("9.60")),
        make_message("o2", cost=Money.zero(), delivered=False),
    ]

    rates = build_observed_rates(messages)

    templated = rates.average_for(MessageClass.TEMPLATED)
    ordinary = rates.average_for(MessageClass.ORDINARY)
    assert templated is not None and templated.rounded().amount == Money.from_rub("5").amount
    assert ordinary is not None and ordinary.rounded().amount == Money.from_rub("4.80").amount


def test_operator_rate_uses_only_delivered_paid_messages() -> None:
    messages = [
        make_message("o1", cost=Money.from_rub("10")),
        make_message("o2", cost=Money.zero()),
    ]

    rates = build_observed_rates(messages)

    operator_rate = rates.rate_for(Operator.MTS, 1)
    assert operator_rate is not None
    assert operator_rate.rounded().amount == Money.from_rub("10").amount


def test_operator_share_is_by_matched_segments() -> None:
    period = Period(
        start=datetime(2026, 11, 1, tzinfo=MSK),
        end=datetime(2026, 11, 30, tzinfo=MSK),
    )
    run = AnalysisRun(
        run_id="run",
        batch_id="batch",
        config_hash="hash",
        created_at=datetime(2026, 11, 30, tzinfo=MSK),
        period=period,
        message_count=4,
        matched_message_count=4,
        metrics=(),
        candidates=(),
        operator_triggers=(
            OperatorTrigger(
                template_id="t1",
                operator=Operator.MTS,
                listed=True,
                matched_messages=2,
                triggered_messages=2,
                matched_segments=8,
            ),
            OperatorTrigger(
                template_id="t1",
                operator=Operator.BEELINE,
                listed=False,
                matched_messages=2,
                triggered_messages=0,
                matched_segments=2,
            ),
        ),
    )

    view = to_analysis_view(run, ())

    shares = {row.operator: row.share for row in view.operator_triggers}
    assert shares[Operator.MTS.value] == 0.8
    assert shares[Operator.BEELINE.value] == 0.2
