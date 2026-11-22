"""Тесты геометрии столбцов диаграммы «Динамика по дням»."""

from __future__ import annotations

from mts_templates.presentation.desktop.widgets.stacked_bar_chart import (
    BAR_GAP,
    MIN_BAR_WIDTH,
    bar_width_for_slot,
)


def test_gap_between_bars_is_minimal_but_visible() -> None:
    for slot in (8.0, 20.0, 33.0, 44.0):
        width = bar_width_for_slot(slot)
        assert 0 < slot - width <= BAR_GAP
        assert slot - width == BAR_GAP


def test_wide_slot_keeps_bar_from_touching_neighbour() -> None:
    slot = 120.0
    width = bar_width_for_slot(slot)
    assert width < slot
    assert slot - width > BAR_GAP


def test_narrow_slot_does_not_overlap() -> None:
    width = bar_width_for_slot(2.0)
    assert width <= 2.0
    assert width <= MIN_BAR_WIDTH
