"""Компоновка дашборда: доли, топ операторов и вывод по концентрации."""

from __future__ import annotations

from mts_templates.application.dto import OperatorStatistics
from mts_templates.domain.value_objects import Money, Operator
from mts_templates.presentation.desktop.widgets.dashboard_page import (
    _operator_concentration,
    _structure_pies_fit,
    _top_operators,
)
from mts_templates.presentation.desktop.widgets.share_bar import part_widths


def _operator(name: str, messages: int, segments: int, cost: str) -> OperatorStatistics:
    return OperatorStatistics(
        operator=name,
        messages=messages,
        segments=segments,
        cost=Money.from_rub(cost),
    )


def test_part_widths_are_proportional() -> None:
    assert part_widths((1.0, 3.0), 100.0) == (25.0, 75.0)


def test_part_widths_ignore_negative_and_zero_total() -> None:
    assert part_widths((-5.0, 5.0), 100.0) == (0.0, 100.0)
    assert part_widths((0.0, 0.0), 100.0) == (0.0, 0.0)
    assert part_widths((1.0,), 0.0) == (0.0,)


def test_structure_pies_fit_needs_room_for_structure_and_operators() -> None:
    assert _structure_pies_fit(582, 320, 250, 12)
    assert not _structure_pies_fit(581, 320, 250, 12)


def test_top_operators_merges_the_rest() -> None:
    operators = tuple(
        _operator(f"OP{index}", index * 10, index * 20, f"{index}.00") for index in range(1, 9)
    )

    rows = _top_operators(operators)

    assert len(rows) == 7
    assert rows[:6] == operators[:6]
    other = rows[-1]
    assert other.operator == "Другие"
    assert other.messages == operators[6].messages + operators[7].messages
    assert other.segments == operators[6].segments + operators[7].segments
    assert other.cost.amount == operators[6].cost.amount + operators[7].cost.amount


def test_top_operators_keeps_short_list() -> None:
    operators = (_operator(Operator.MTS.value, 10, 20, "5.00"),)

    assert _top_operators(operators) == operators


def test_operator_concentration_names_the_leader_and_top_three() -> None:
    operators = (
        _operator(Operator.MTS.value, 600, 1200, "100.00"),
        _operator(Operator.T2.value, 300, 600, "50.00"),
        _operator(Operator.MEGAFON.value, 50, 100, "10.00"),
        _operator(Operator.BEELINE.value, 50, 100, "10.00"),
    )

    assert _operator_concentration(operators) == (
        "Крупнейший — МТС: 60.0% сообщений · топ-3 — 95.0%"
    )
    assert _operator_concentration(()) == ""
