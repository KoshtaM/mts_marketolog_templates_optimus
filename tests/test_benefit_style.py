"""Тесты цветов уровней выгоды шаблона и читаемости подсветки строк."""

from __future__ import annotations

import pytest

from mts_templates.application.settings import BenefitThresholds
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.benefit_style import (
    RowPalette,
    benefit_color,
    benefit_level,
    row_palette,
    semantic_text,
)
from mts_templates.presentation.desktop.contrast import (
    MIN_CONTRAST,
    contrast_ratio,
    readable_text_color,
)

THRESHOLDS = BenefitThresholds()
LIGHT = row_palette("#ffffff", "#1b7f3a", "#b42318")
DARK = row_palette("#121916", "#4fbf87", "#d9534f")


def test_thresholds_must_strictly_ascend() -> None:
    with pytest.raises(ValueError):
        BenefitThresholds(
            level_1=Money.from_rub("10"),
            level_2=Money.from_rub("5"),
            level_3=Money.from_rub("100"),
            level_4=Money.from_rub("1000"),
            level_5=Money.from_rub("10000"),
        )


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_loss_uses_palette_loss_color(palette: RowPalette) -> None:
    assert benefit_level(Money.from_rub("-1"), THRESHOLDS) == -1
    assert benefit_color(Money.from_rub("-2000"), THRESHOLDS, palette) == palette.loss_color


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_zero_benefit_has_no_color(palette: RowPalette) -> None:
    assert benefit_level(Money.zero(), THRESHOLDS) == 0
    assert benefit_color(Money.zero(), THRESHOLDS, palette) is None


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


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_each_level_has_its_own_color(palette: RowPalette) -> None:
    assert len(set(palette.level_colors)) == 5
    assert benefit_color(Money.from_rub("100000"), THRESHOLDS, palette) == palette.level_colors[-1]


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_row_highlights_keep_text_readable(palette: RowPalette) -> None:
    for color in palette.all_colors:
        text = readable_text_color(color)
        assert contrast_ratio(text, color) >= MIN_CONTRAST


def test_light_and_dark_palettes_differ() -> None:
    assert LIGHT.level_colors != DARK.level_colors
    assert LIGHT.loss_color != DARK.loss_color


def test_semantic_text_keeps_readable_accent() -> None:
    assert semantic_text("#1b7f3a", "#ffffff") == "#1b7f3a"


def test_semantic_text_falls_back_when_contrast_is_low() -> None:
    assert semantic_text("#1b7f3a", "#121916") == readable_text_color("#121916")
