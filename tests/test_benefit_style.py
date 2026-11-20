"""Тесты цветов уровней выгоды шаблона."""

from __future__ import annotations

import pytest

from mts_templates.application.settings import BenefitThresholds
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.benefit_style import (
    LEVEL_COLORS,
    LOSS_COLOR,
    benefit_color,
    benefit_level,
)

THRESHOLDS = BenefitThresholds()


def test_thresholds_must_strictly_ascend() -> None:
    with pytest.raises(ValueError):
        BenefitThresholds(
            level_1=Money.from_rub("10"),
            level_2=Money.from_rub("5"),
            level_3=Money.from_rub("100"),
            level_4=Money.from_rub("1000"),
            level_5=Money.from_rub("10000"),
        )


def test_loss_is_weak_red() -> None:
    assert benefit_level(Money.from_rub("-1"), THRESHOLDS) == -1
    assert benefit_color(Money.from_rub("-2000"), THRESHOLDS) == LOSS_COLOR


def test_zero_benefit_has_no_color() -> None:
    assert benefit_level(Money.zero(), THRESHOLDS) == 0
    assert benefit_color(Money.zero(), THRESHOLDS) is None


def test_levels_follow_thresholds() -> None:
    cases = (
        ("1", 1),
        ("2999", 1),
        ("3000", 2),
        ("9999", 2),
        ("10000", 3),
        ("30000", 4),
        ("99999", 4),
        ("100000", 5),
        ("1000000", 5),
    )

    for amount, expected in cases:
        assert benefit_level(Money.from_rub(amount), THRESHOLDS) == expected


def test_each_level_has_its_own_green() -> None:
    assert len(set(LEVEL_COLORS)) == 5
    assert benefit_color(Money.from_rub("100000"), THRESHOLDS) == LEVEL_COLORS[-1]
