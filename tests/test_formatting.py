"""Тесты форматирования булевых значений для таблиц."""

from __future__ import annotations

from mts_templates.domain.value_objects import Operator
from mts_templates.presentation.desktop.formatting import format_bool_icon, format_operators


def test_true_is_green_check() -> None:
    assert format_bool_icon(True) == "✔"


def test_false_is_cross() -> None:
    assert format_bool_icon(False) == "✘"


def test_icons_differ() -> None:
    assert format_bool_icon(True) != format_bool_icon(False)


def test_operators_use_short_names_in_stable_order() -> None:
    operators = [
        Operator.T2.value,
        Operator.BEELINE.value,
        Operator.MTS.value,
        Operator.MEGAFON.value,
    ]

    assert format_operators(operators) == "МТС, МегаФон, Билайн, Tele2"


def test_empty_operator_list_means_all_operators() -> None:
    assert format_operators(()) == "все"


def test_unknown_operator_name_is_kept() -> None:
    assert format_operators(["Новый оператор"]) == "Новый оператор"
