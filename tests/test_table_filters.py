"""Тесты отбора строк разбивки по операторам для выделенного шаблона."""

from __future__ import annotations

from mts_templates.application.dto import OperatorTriggerView
from mts_templates.presentation.desktop.table_filters import operator_rows_for_template


def _row(template_id: str, operator: str) -> OperatorTriggerView:
    return OperatorTriggerView(
        template_id=template_id,
        template_name=f"Шаблон {template_id}",
        sender="SENDER",
        operator=operator,
        listed=True,
        matched_messages=10,
        triggered_messages=8,
    )


ROWS = (_row("1", "MTS"), _row("1", "Beeline"), _row("2", "MTS"))


def test_only_selected_template_rows() -> None:
    rows = operator_rows_for_template("1", ROWS)

    assert {row.operator for row in rows} == {"MTS", "Beeline"}
    assert all(row.template_id == "1" for row in rows)


def test_unknown_template_has_no_rows() -> None:
    assert operator_rows_for_template("404", ROWS) == ()


def test_no_selection_has_no_rows() -> None:
    assert operator_rows_for_template(None, ROWS) == ()


def test_trigger_rate_of_row() -> None:
    assert _row("1", "MTS").trigger_rate == 0.8
