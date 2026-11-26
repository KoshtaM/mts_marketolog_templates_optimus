"""Тесты центра действий: приоритеты, суммы потерь и переходы к сообщениям."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mts_templates.domain.analytics.actions import (
    ActionKind,
    DrillDown,
    build_action_center,
)
from mts_templates.domain.analytics.activity import OperatorTrigger, TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money, Operator, Period

MSK = timezone(timedelta(hours=3))


def _period(days: int = 30) -> Period:
    start = datetime(2026, 11, 1, tzinfo=MSK)
    return Period(start=start, end=start + timedelta(days=days - 1))


def _template() -> SmsTemplate:
    return SmsTemplate(
        template_id="t1",
        name="Код подтверждения",
        text="Ваш код %d",
        sender="TEST",
        operators=frozenset({Operator.MTS}),
    )


def _loss_metrics() -> TemplateMetrics:
    return TemplateMetrics(
        template_id="t1",
        matched_messages=100,
        matched_segments=200,
        delivered_messages=100,
        unique_recipients=100,
        actual_cost=Money.from_rub("400"),
        baseline_cost=Money.from_rub("1000"),
        template_fee=Money.from_rub("2000"),
        net_benefit=Money.from_rub("-1400"),
        triggered_messages=100,
        off_operator_messages=0,
        trigger_rate=Decimal("1"),
        active=True,
    )


def _run(
    *,
    days: int = 30,
    metrics: tuple[TemplateMetrics, ...] = (),
    triggers: tuple[OperatorTrigger, ...] = (),
    templated_rate: Money | None = None,
    unmatched_messages: int = 0,
    unmatched_segments: int = 0,
    unmatched_cost: Money | None = None,
) -> AnalysisRun:
    return AnalysisRun(
        run_id="run",
        batch_id="batch",
        config_hash="hash",
        created_at=datetime(2026, 11, 30, tzinfo=MSK),
        period=_period(days),
        message_count=100,
        matched_message_count=100,
        metrics=metrics,
        candidates=(),
        operator_triggers=triggers,
        observed_templated_rate=templated_rate,
        unmatched_templated_messages=unmatched_messages,
        unmatched_templated_segments=unmatched_segments,
        unmatched_templated_cost=unmatched_cost or Money.zero(),
    )


def test_loss_template_is_paid_back_by_disabling() -> None:
    center = build_action_center(_run(metrics=(_loss_metrics(),)), (_template(),))

    assert center.loss_templates == 1
    item = center.items[0]
    assert item.kind is ActionKind.LOSS_TEMPLATE
    assert item.severity == 1
    assert item.monthly_loss.rounded().amount == Decimal("1400.00")
    assert item.subject == "Ваш код %d"
    assert item.template_id == "t1"
    assert item.drill_down is DrillDown.TEMPLATE
    assert center.total_monthly_loss.rounded().amount == Decimal("1400.00")


def test_partial_period_scales_monthly_loss() -> None:
    center = build_action_center(_run(days=15, metrics=(_loss_metrics(),)), (_template(),))

    item = center.items[0]
    assert center.monthly_factor == Decimal(2)
    assert item.monthly_loss.rounded().amount == Decimal("800.00")
    assert center.total_monthly_loss.rounded().amount == Decimal("800.00")


def test_off_operator_loss_uses_observed_templated_rate() -> None:
    trigger = OperatorTrigger(
        template_id="t1",
        operator=Operator.BEELINE,
        listed=False,
        matched_messages=10,
        triggered_messages=0,
        matched_segments=20,
        untriggered_messages=10,
        untriggered_segments=20,
        untriggered_cost=Money.from_rub("200"),
    )

    center = build_action_center(
        _run(triggers=(trigger,), templated_rate=Money.from_rub("5")),
        (_template(),),
    )

    item = center.items[0]
    assert item.kind is ActionKind.OFF_OPERATOR
    assert item.operator == Operator.BEELINE.value
    assert item.messages == 10
    assert item.segments == 20
    assert item.monthly_loss.rounded().amount == Decimal("100.00")
    assert item.drill_down is DrillDown.TEMPLATE
    assert center.off_operator_loss.rounded().amount == Decimal("100.00")
    assert center.off_operator_messages == 10


def test_off_operator_loss_is_scaled_for_partial_period() -> None:
    trigger = OperatorTrigger(
        template_id="t1",
        operator=Operator.BEELINE,
        listed=False,
        matched_messages=10,
        triggered_messages=0,
        matched_segments=20,
        untriggered_messages=10,
        untriggered_segments=20,
        untriggered_cost=Money.from_rub("200"),
    )

    center = build_action_center(
        _run(days=15, triggers=(trigger,), templated_rate=Money.from_rub("5")),
        (_template(),),
    )

    assert center.items[0].monthly_loss.rounded().amount == Decimal("200.00")


def test_trigger_below_full_marks_listed_operator() -> None:
    trigger = OperatorTrigger(
        template_id="t1",
        operator=Operator.MTS,
        listed=True,
        matched_messages=10,
        triggered_messages=8,
        matched_segments=10,
        untriggered_messages=2,
        untriggered_segments=2,
        untriggered_cost=Money.from_rub("19.20"),
    )

    center = build_action_center(
        _run(triggers=(trigger,), templated_rate=Money.from_rub("4")),
        (_template(),),
    )

    item = center.items[0]
    assert item.kind is ActionKind.UNTRIGGERED
    assert item.monthly_loss.rounded().amount == Decimal("11.20")
    assert center.untriggered_loss.rounded().amount == Decimal("11.20")
    assert center.untriggered_messages == 2


def test_unmatched_templated_is_informational_only() -> None:
    center = build_action_center(
        _run(
            unmatched_messages=5,
            unmatched_segments=7,
            unmatched_cost=Money.from_rub("35"),
        ),
        (_template(),),
    )

    item = center.items[0]
    assert item.kind is ActionKind.UNMATCHED_TEMPLATED
    assert item.severity == 0
    assert item.monthly_loss == Money.zero()
    assert item.messages == 5
    assert item.segments == 7
    assert item.drill_down is DrillDown.UNMATCHED_TEMPLATED
    assert center.unmatched_templated_messages == 5
    assert center.unmatched_templated_segments == 7
    assert center.unmatched_templated_cost.rounded().amount == Decimal("35.00")
    assert center.total_monthly_loss == Money.zero()


def test_missing_templated_rate_keeps_volumes_without_money() -> None:
    trigger = OperatorTrigger(
        template_id="t1",
        operator=Operator.MTS,
        listed=True,
        matched_messages=10,
        triggered_messages=0,
        matched_segments=10,
        untriggered_messages=10,
        untriggered_segments=10,
        untriggered_cost=Money.from_rub("100"),
    )

    center = build_action_center(_run(triggers=(trigger,)), (_template(),))

    item = center.items[0]
    assert item.monthly_loss == Money.zero()
    assert item.segments == 10
    assert center.total_monthly_loss == Money.zero()
    assert any("Нет наблюдаемой ставки" in warning for warning in center.warnings)


def test_items_are_sorted_by_monthly_loss() -> None:
    trigger = OperatorTrigger(
        template_id="t1",
        operator=Operator.BEELINE,
        listed=False,
        matched_messages=10,
        triggered_messages=0,
        matched_segments=20,
        untriggered_messages=10,
        untriggered_segments=20,
        untriggered_cost=Money.from_rub("200"),
    )

    center = build_action_center(
        _run(
            metrics=(_loss_metrics(),),
            triggers=(trigger,),
            templated_rate=Money.from_rub("5"),
        ),
        (_template(),),
    )

    assert [item.kind for item in center.items] == [
        ActionKind.LOSS_TEMPLATE,
        ActionKind.OFF_OPERATOR,
    ]
    assert center.total_monthly_loss.rounded().amount == Decimal("1500.00")
