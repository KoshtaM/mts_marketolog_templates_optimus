"""Тесты экономической выгоды."""

from __future__ import annotations

from decimal import Decimal

from mts_templates.domain.analytics.benefit import (
    calculate_candidate_benefit,
    calculate_template_benefit,
)
from mts_templates.domain.value_objects import Money


def test_active_template_benefit() -> None:
    result = calculate_template_benefit(
        actual_message_cost=Money.from_rub("100.00"),
        baseline_cost=Money.from_rub("5000.00"),
        template_fee=Money.from_rub("2000.00"),
    )

    assert result.active is True
    assert result.actual_message_cost == Money.from_rub("100.00")
    assert result.template_fee == Money.from_rub("2000.00")
    assert result.net_benefit == Money.from_rub("2900.00")


def test_inactive_template_benefit_is_loss() -> None:
    result = calculate_template_benefit(
        actual_message_cost=Money.from_rub("0.00"),
        baseline_cost=Money.from_rub("5000.00"),
        template_fee=Money.from_rub("2000.00"),
        active=False,
    )

    assert result.active is False
    assert result.actual_message_cost == Money.zero()
    assert result.baseline_cost == Money.zero()
    assert result.net_benefit == Money.from_rub("-2000.00")


def test_template_fee_multiplies_by_months() -> None:
    result = calculate_template_benefit(
        actual_message_cost=Money.from_rub("100.00"),
        baseline_cost=Money.from_rub("5000.00"),
        template_fee=Money.from_rub("2000.00"),
        months=3,
    )

    assert result.template_fee == Money.from_rub("6000.00")
    assert result.net_benefit == Money.from_rub("-1100.00")


def test_candidate_benefit_and_payback() -> None:
    result = calculate_candidate_benefit(
        ordinary_cost_per_message=Money.from_rub("10.00"),
        templated_cost_per_message=Money.from_rub("4.00"),
        monthly_messages=1000,
        template_fee=Money.from_rub("2000.00"),
    )

    assert result.monthly_saving == Money.from_rub("6000.00")
    assert result.net_monthly == Money.from_rub("4000.00")
    assert result.payback_months == Decimal("333.3333333333333333333333333")
    assert result.break_even_messages == 334


def test_candidate_benefit_negative_saving() -> None:
    result = calculate_candidate_benefit(
        ordinary_cost_per_message=Money.from_rub("4.00"),
        templated_cost_per_message=Money.from_rub("6.00"),
        monthly_messages=1000,
        template_fee=Money.from_rub("2000.00"),
    )

    assert result.monthly_saving == Money.from_rub("-2000.00")
    assert result.net_monthly == Money.from_rub("-4000.00")
    assert result.payback_months is None
    assert result.break_even_messages is None
