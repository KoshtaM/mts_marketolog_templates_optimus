"""Тесты пакетного тарифа."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from mts_templates.domain.tariffs.models import (
    PackagePlan,
    PricingMode,
    RateTier,
)
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from tests.helpers import make_message


def make_uniform_plan() -> PackagePlan:
    return PackagePlan(
        tariff_id="package-all-operators",
        name="Обычные SMS на всех операторов РФ",
        message_class=MessageClass.ORDINARY,
        package_size=1000,
        pricing_mode=PricingMode.UNIFORM,
        tiers=(
            RateTier(1, 150, Money.from_rub("7.00")),
            RateTier(151, 1000, Money.from_rub("9.90")),
            RateTier(1001, None, Money.from_rub("9.80")),
        ),
        effective_from=date(2026, 11, 1),
    )


def test_uniform_effective_rate_depends_on_package_size() -> None:
    plan = make_uniform_plan()
    assert plan.effective_rate().amount == Decimal("9.90")


def test_uniform_package_cost_is_rate_times_segments() -> None:
    plan = make_uniform_plan()
    messages = [
        make_message("1", segments=1),
        make_message("2", segments=2),
        make_message("3", segments=1),
    ]

    result = plan.calculate(messages)

    assert result.total.rounded().amount == Decimal("39.60")
    assert result.overage_segments == 0


def test_marginal_package_rate_and_cost() -> None:
    plan = PackagePlan(
        tariff_id="package-mts",
        name="Обычные SMS на МТС",
        message_class=MessageClass.ORDINARY,
        package_size=450_000,
        pricing_mode=PricingMode.MARGINAL,
        tiers=(
            RateTier(1, 400_000, Money.from_rub("7.54")),
            RateTier(400_001, 4_000_000, Money.from_rub("7.39")),
            RateTier(4_000_001, None, Money.from_rub("7.32")),
        ),
    )

    assert plan.effective_rate().rounded().amount == Decimal("7.52")

    result = plan.calculate([make_message("1", segments=2)])
    assert result.total.rounded().amount == Decimal("15.05")


def test_package_overage_uses_operator_rate() -> None:
    plan = PackagePlan(
        tariff_id="package-small",
        name="Маленький пакет",
        message_class=MessageClass.ORDINARY,
        package_size=10,
        pricing_mode=PricingMode.UNIFORM,
        tiers=(RateTier(1, 10, Money.from_rub("10.00")),),
        overage_rates={Operator.MTS: Money.from_rub("20.00")},
    )

    result = plan.calculate([make_message("1", segments=12)])

    assert result.total.rounded().amount == Decimal("140.00")
    assert result.overage_segments == 2


def test_package_size_must_fit_uniform_tier() -> None:
    with pytest.raises(ValueError):
        PackagePlan(
            tariff_id="bad",
            name="Плохой пакет",
            message_class=MessageClass.ORDINARY,
            package_size=500,
            pricing_mode=PricingMode.UNIFORM,
            tiers=(RateTier(1, 100, Money.from_rub("7.00")),),
        )


def test_package_tiers_must_not_have_gaps() -> None:
    with pytest.raises(ValueError):
        PackagePlan(
            tariff_id="bad",
            name="Плохие tier'ы",
            message_class=MessageClass.ORDINARY,
            package_size=100,
            pricing_mode=PricingMode.MARGINAL,
            tiers=(
                RateTier(1, 50, Money.from_rub("7.00")),
                RateTier(60, None, Money.from_rub("6.00")),
            ),
        )
