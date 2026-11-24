"""Тесты сортировки таблиц по заголовку колонки."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import build_table, sort_by_title

_APP = QApplication.instance() or QApplication([])


@dataclass(frozen=True)
class Row:
    title: str
    benefit: Money


COLUMNS = (
    Column("Шаблон", lambda item: item.title),
    Column("Выгода/мес", lambda item: item.benefit),
)


def test_sort_by_title_sets_descending_indicator_and_order() -> None:
    model = RowsTableModel(COLUMNS)
    model.set_rows(
        [
            Row("Первый", Money.from_rub("10")),
            Row("Второй", Money.from_rub("50")),
        ]
    )
    table, proxy = build_table(model)

    sort_by_title(table, "Выгода/мес", Qt.SortOrder.DescendingOrder)

    assert table.horizontalHeader().sortIndicatorSection() == 1
    assert table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert [proxy.index(row, 0).data() for row in range(proxy.rowCount())] == [
        "Второй",
        "Первый",
    ]


def test_sort_by_title_rejects_unknown_column() -> None:
    table, _proxy = build_table(RowsTableModel(COLUMNS))

    try:
        sort_by_title(table, "Нет колонки", Qt.SortOrder.DescendingOrder)
    except ValueError:
        return
    raise AssertionError("Ожидалось исключение ValueError")
