"""Фиксированные цвета операторов в круговых диаграммах."""

from __future__ import annotations

from mts_templates.domain.value_objects import Operator
from mts_templates.presentation.desktop.operator_colors import (
    OPERATOR_COLORS,
    OTHER_COLOR,
    operator_color,
)

MTS_RED = "#e30611"
TELE2_BLACK = "#1d1d1f"
MEGAFON_GREEN = "#00b956"
BEELINE_YELLOW = "#ffcc00"


def test_requested_operator_colors() -> None:
    assert operator_color(Operator.MTS.value) == MTS_RED
    assert operator_color(Operator.T2.value) == TELE2_BLACK
    assert operator_color(Operator.MEGAFON.value) == MEGAFON_GREEN
    assert operator_color(Operator.BEELINE.value) == BEELINE_YELLOW


def test_every_operator_has_its_own_color() -> None:
    colors = [operator_color(operator.value) for operator in Operator]

    assert len(set(colors)) == len(Operator)
    assert OTHER_COLOR not in colors


def test_color_does_not_depend_on_position() -> None:
    assert set(OPERATOR_COLORS) == {operator.value for operator in Operator}


def test_unknown_name_falls_back_to_other_color() -> None:
    assert operator_color("Неизвестный оператор") == OTHER_COLOR
