"""Тесты геометрии столбцов диаграммы «Динамика по дням»."""

from __future__ import annotations

import pytest

from mts_templates.presentation.desktop.daily_chart import BarOverlay, StackedBar, StackedSegment
from mts_templates.presentation.desktop.widgets.stacked_bar_chart import (
    BAR_GAP,
    BAR_GAP_RATIO,
    MIN_BAR_WIDTH,
    MIN_OVERLAY_HEIGHT,
    bar_width_for_slot,
    overlay_geometry,
)


def test_gap_between_bars_is_relative_to_slot() -> None:
    for slot in (20.0, 33.0, 44.0, 58.0, 100.0):
        width = bar_width_for_slot(slot)
        assert slot - width > 0
        assert slot - width == pytest.approx(slot * BAR_GAP_RATIO)


def test_narrow_slot_keeps_minimal_gap() -> None:
    slot = 8.0
    width = bar_width_for_slot(slot)
    assert slot - width == BAR_GAP


def test_wide_slot_keeps_bar_from_touching_neighbour() -> None:
    slot = 120.0
    width = bar_width_for_slot(slot)
    assert width < slot
    assert slot - width > BAR_GAP
    assert slot - width == pytest.approx(slot * BAR_GAP_RATIO)


def test_narrow_slot_does_not_overlap() -> None:
    width = bar_width_for_slot(2.0)
    assert width <= 2.0
    assert width <= MIN_BAR_WIDTH


def test_overlay_starts_inside_the_bar() -> None:
    offset, height = overlay_geometry(100.0, 10.0, 0.1)

    assert offset == pytest.approx(10.0)
    assert height == pytest.approx(10.0)


def test_small_overlay_keeps_minimal_visible_height() -> None:
    _offset, height = overlay_geometry(100.0, 0.5, 0.1)

    assert height == pytest.approx(MIN_OVERLAY_HEIGHT)


def test_overlay_does_not_rise_above_the_bar() -> None:
    offset, height = overlay_geometry(100.0, 100.0, 0.1)

    assert offset == pytest.approx(10.0)
    assert height == pytest.approx(90.0)
    assert offset + height <= 100.0


def test_overlay_of_tiny_bar_stays_within_it() -> None:
    offset, height = overlay_geometry(1.0, 1.0, 0.1)

    assert offset + height <= 1.0


def test_zero_values_have_no_overlay() -> None:
    assert overlay_geometry(0.0, 10.0, 0.1) is None
    assert overlay_geometry(100.0, 0.0, 0.1) is None


def test_bar_total_counts_only_the_base_column() -> None:
    bar = StackedBar(
        label="01.11",
        segments=(StackedSegment("Остальной трафик", 9.0, "#0d9488"),),
        overlays=(BarOverlay("Соответствуют шаблону", 5.0, "#ff8c00", 0.1),),
    )

    assert bar.total == 9.0
