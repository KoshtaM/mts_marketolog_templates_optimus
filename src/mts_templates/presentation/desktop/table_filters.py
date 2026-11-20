"""Отбор строк для связанных таблиц без участия Qt."""

from __future__ import annotations

from collections.abc import Sequence

from mts_templates.application.dto import OperatorTriggerView


def operator_rows_for_template(
    template_id: str | None,
    rows: Sequence[OperatorTriggerView],
) -> tuple[OperatorTriggerView, ...]:
    """Строки разбивки по операторам только для выбранного шаблона."""
    if template_id is None:
        return ()
    return tuple(row for row in rows if row.template_id == template_id)
