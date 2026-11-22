"""Индикатор операции: минимальное время показа и его границы."""

from __future__ import annotations

from mts_templates.presentation.desktop.widgets.busy_overlay import (
    MIN_VISIBLE_MS,
    remaining_visible_ms,
)


def test_instant_operation_keeps_indicator_for_full_minimum() -> None:
    assert remaining_visible_ms(0) == MIN_VISIBLE_MS


def test_short_operation_keeps_only_the_rest() -> None:
    assert remaining_visible_ms(100) == MIN_VISIBLE_MS - 100


def test_operation_at_the_threshold_hides_immediately() -> None:
    assert remaining_visible_ms(MIN_VISIBLE_MS) == 0


def test_long_operation_hides_immediately() -> None:
    assert remaining_visible_ms(MIN_VISIBLE_MS * 4) == 0


def test_negative_elapsed_is_treated_as_instant() -> None:
    assert remaining_visible_ms(-50) == MIN_VISIBLE_MS


def test_custom_minimum_is_respected() -> None:
    assert remaining_visible_ms(80, minimum_ms=200) == 120
