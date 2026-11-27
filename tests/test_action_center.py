"""Тесты центра действий: приоритеты, действия, суммы и переходы к сообщениям."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from mts_templates.domain.analytics.actions import (
    Action,
    ActionItem,
    ActionKind,
    DrillDown,
    build_action_center,
)
from mts_templates.domain.analytics.activity import DaySegments, OperatorTrigger, TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun, CandidateGroup
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


def _unworking_metrics() -> TemplateMetrics:
    return TemplateMetrics(
        template_id="t1",
        matched_messages=0,
        matched_segments=0,
        delivered_messages=0,
        unique_recipients=0,
        actual_cost=Money.zero(),
        baseline_cost=Money.zero(),
        template_fee=Money.from_rub("2000"),
        net_benefit=Money.from_rub("-2000"),
        triggered_messages=0,
        off_operator_messages=0,
        trigger_rate=Decimal("0"),
        active=False,
    )


def _run(
    *,
    days: int = 30,
    metrics: tuple[TemplateMetrics, ...] = (),
    candidates: tuple[CandidateGroup, ...] = (),
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
        candidates=candidates,
        operator_triggers=triggers,
        observed_templated_rate=templated_rate,
        unmatched_templated_messages=unmatched_messages,
        unmatched_templated_segments=unmatched_segments,
        unmatched_templated_cost=unmatched_cost or Money.zero(),
    )


def _candidate(net_monthly: str) -> CandidateGroup:
    """Кандидат с платой за шаблон 2 000 ₽ и заданной месячной выгодой."""
    net = Money.from_rub(net_monthly)
    fee = Money.from_rub("2000")
    return CandidateGroup(
        candidate_id="c1",
        template_text="Заказ %d готов",
        messages=50,
        segments=80,
        actual_cost=Money.from_rub("800"),
        templated_cost=Money.from_rub("400"),
        monthly_saving=net + fee,
        template_fee=fee,
        net_monthly=net,
        payback_months=None,
        confidence=Decimal("0.9"),
        coverage=Decimal("0.8"),
        senders=("SHOP",),
        operators=(Operator.MTS,),
        period=_period(),
        is_partial_period=False,
        daily_segments=(DaySegments(day=date(2026, 11, 1), segments=80),),
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
    assert item.monthly_benefit == Money.zero()
    # Убыток 1400 ₽ меньше 75 % платы (1500 ₽): шаблон наблюдаем, но не удаляем.
    assert item.action is Action.WATCH
    assert "Наблюдать" in item.recommendation
    assert center.total_monthly_loss.rounded().amount == Decimal("1400.00")
    assert center.total_monthly_benefit == Money.zero()


def test_partial_period_scales_monthly_loss() -> None:
    center = build_action_center(_run(days=15, metrics=(_loss_metrics(),)), (_template(),))

    item = center.items[0]
    assert center.monthly_factor == Decimal(2)
    assert item.monthly_loss.rounded().amount == Decimal("800.00")
    assert center.total_monthly_loss.rounded().amount == Decimal("800.00")


def test_unworking_template_is_marked_as_unworking() -> None:
    center = build_action_center(_run(metrics=(_unworking_metrics(),)), (_template(),))

    assert center.loss_templates == 1
    item = center.items[0]
    assert item.kind is ActionKind.UNWORKING_TEMPLATE
    assert item.title == "Неработающий"
    assert item.monthly_loss.rounded().amount == Decimal("2000.00")
    assert item.messages == 0
    assert item.severity == 1
    assert item.template_id == "t1"
    assert item.drill_down is DrillDown.TEMPLATE
    assert center.total_monthly_loss.rounded().amount == Decimal("2000.00")


def test_unworking_template_with_matched_messages_is_marked_as_unworking() -> None:
    metrics = replace(
        _unworking_metrics(),
        matched_messages=100,
        matched_segments=200,
        off_operator_messages=100,
        active=True,
    )

    center = build_action_center(_run(metrics=(metrics,)), (_template(),))

    item = center.items[0]
    assert item.kind is ActionKind.UNWORKING_TEMPLATE
    assert item.title == "Неработающий"
    assert item.messages == 100
    assert item.segments == 200
    assert item.monthly_loss.rounded().amount == Decimal("2000.00")


def test_loss_at_quarter_of_fee_is_skipped() -> None:
    metrics = replace(
        _loss_metrics(),
        baseline_cost=Money.from_rub("1900"),
        net_benefit=Money.from_rub("-500"),
    )

    center = build_action_center(_run(metrics=(metrics,)), (_template(),))

    assert center.items == ()
    assert center.loss_templates == 0
    assert center.total_monthly_loss == Money.zero()


def test_loss_above_quarter_of_fee_is_included() -> None:
    metrics = replace(
        _loss_metrics(),
        baseline_cost=Money.from_rub("1800"),
        net_benefit=Money.from_rub("-600"),
    )

    center = build_action_center(_run(metrics=(metrics,)), (_template(),))

    assert [item.kind for item in center.items] == [ActionKind.LOSS_TEMPLATE]
    assert center.items[0].monthly_loss.rounded().amount == Decimal("600.00")
    assert center.items[0].action is Action.WATCH
    assert center.loss_templates == 1


def test_off_operator_is_not_included_in_action_center() -> None:
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
            days=15,
            triggers=(trigger,),
            templated_rate=Money.from_rub("5"),
        ),
        (_template(),),
    )

    assert center.items == ()
    assert center.total_monthly_loss == Money.zero()


def test_trigger_below_full_is_not_shown_in_action_center() -> None:
    """Срабатывание ниже 100 % остаётся в разбивке по операторам, не в таблице."""
    center = build_action_center(_run(metrics=(_loss_metrics(),)), (_template(),))

    assert [item.kind for item in center.items] == [ActionKind.LOSS_TEMPLATE]
    assert all(item.title != "Срабатывание ниже 100 %" for item in center.items)


def test_unmatched_templated_stays_outside_table() -> None:
    center = build_action_center(
        _run(
            unmatched_messages=5,
            unmatched_segments=7,
            unmatched_cost=Money.from_rub("35"),
        ),
        (_template(),),
    )

    assert center.items == ()
    assert center.unmatched_templated_messages == 5
    assert center.unmatched_templated_segments == 7
    assert center.unmatched_templated_cost.rounded().amount == Decimal("35.00")
    assert center.total_monthly_loss == Money.zero()
    assert center.total_monthly_benefit == Money.zero()


def test_items_are_sorted_by_monthly_impact() -> None:
    center = build_action_center(
        _run(metrics=(_loss_metrics(),), candidates=(_candidate("3000"),)),
        (_template(),),
    )

    assert [item.kind for item in center.items] == [
        ActionKind.PROFITABLE_CANDIDATE,
        ActionKind.LOSS_TEMPLATE,
    ]
    assert center.total_monthly_loss.rounded().amount == Decimal("1400.00")
    assert center.total_monthly_benefit.rounded().amount == Decimal("3000.00")


def test_unworking_template_offers_delete() -> None:
    center = build_action_center(_run(metrics=(_unworking_metrics(),)), (_template(),))

    item = center.items[0]
    assert item.action is Action.DELETE
    assert item.monthly_benefit == Money.zero()
    assert item.monthly_loss.rounded().amount == Decimal("2000.00")
    assert center.total_monthly_benefit == Money.zero()


def test_loss_template_action_requires_three_quarters_of_fee() -> None:
    below = replace(
        _loss_metrics(),
        baseline_cost=Money.from_rub("900"),
        net_benefit=Money.from_rub("-1500"),
    )
    above = replace(
        _loss_metrics(),
        baseline_cost=Money.from_rub("800"),
        net_benefit=Money.from_rub("-1600"),
    )

    below_center = build_action_center(_run(metrics=(below,)), (_template(),))
    above_center = build_action_center(_run(metrics=(above,)), (_template(),))

    assert below_center.items[0].action is Action.WATCH
    assert "Наблюдать" in below_center.items[0].recommendation
    assert below_center.items[0].monthly_benefit == Money.zero()
    assert above_center.items[0].action is Action.DELETE
    assert above_center.items[0].monthly_benefit == Money.zero()
    assert above_center.items[0].monthly_loss.rounded().amount == Decimal("1600.00")


def test_profitable_candidate_offers_add() -> None:
    center = build_action_center(_run(candidates=(_candidate("1600"),)), ())

    item = center.items[0]
    assert item.kind is ActionKind.PROFITABLE_CANDIDATE
    assert item.title == "Выгодный кандидат"
    assert item.subject == "Заказ %d готов"
    assert item.action is Action.ADD
    assert item.drill_down is None
    assert item.messages == 50
    assert item.segments == 80
    assert item.monthly_loss == Money.zero()
    assert item.monthly_benefit.rounded().amount == Decimal("1600.00")
    assert center.profitable_candidates == 1
    assert center.total_monthly_benefit.rounded().amount == Decimal("1600.00")
    assert center.total_monthly_loss == Money.zero()


def test_candidate_at_three_quarters_of_fee_is_skipped() -> None:
    center = build_action_center(_run(candidates=(_candidate("1500"),)), ())

    assert center.items == ()
    assert center.profitable_candidates == 0
    assert center.total_monthly_benefit == Money.zero()


def test_action_item_rejects_loss_and_benefit_together() -> None:
    with pytest.raises(ValueError, match="не может быть одновременно"):
        ActionItem(
            key="invalid",
            kind=ActionKind.LOSS_TEMPLATE,
            severity=1,
            title="Убыточный шаблон",
            subject="Ваш код %d",
            detail="",
            recommendation="",
            monthly_loss=Money.from_rub("100"),
            messages=1,
            segments=1,
            monthly_benefit=Money.from_rub("100"),
        )


def test_loss_and_benefit_are_mutually_exclusive() -> None:
    center = build_action_center(
        _run(metrics=(_loss_metrics(),), candidates=(_candidate("1600"),)),
        (_template(),),
    )

    assert len(center.items) == 2
    for item in center.items:
        assert item.monthly_loss == Money.zero() or item.monthly_benefit == Money.zero()
        assert not (item.monthly_loss.amount > 0 and item.monthly_benefit.amount > 0)
    assert {item.kind for item in center.items} == {
        ActionKind.LOSS_TEMPLATE,
        ActionKind.PROFITABLE_CANDIDATE,
    }
