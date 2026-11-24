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


@dataclass(frozen=True)
class OperatorRow:
    operator: str
    listed: bool
    share: float


OPERATOR_COLUMNS = (
    Column("Оператор", lambda item: item.operator),
    Column("В списке", lambda item: item.listed),
    Column("Доля (%)", lambda item: item.share),
)


def test_secondary_sort_breaks_ties_by_share_descending() -> None:
    model = RowsTableModel(OPERATOR_COLUMNS)
    model.set_rows(
        [
            OperatorRow("Tele2", False, 0.9),
            OperatorRow("MTS", True, 0.5),
            OperatorRow("Megafon", False, 0.1),
            OperatorRow("Beeline", True, 0.8),
        ]
    )
    table, proxy = build_table(
        model,
        secondary_sort=("Доля (%)", Qt.SortOrder.DescendingOrder),
    )

    sort_by_title(table, "В списке", Qt.SortOrder.DescendingOrder)

    assert [proxy.index(row, 0).data() for row in range(proxy.rowCount())] == [
        "Beeline",
        "MTS",
        "Tele2",
        "Megafon",
    ]


def test_secondary_sort_stays_descending_with_ascending_primary() -> None:
    model = RowsTableModel(OPERATOR_COLUMNS)
    model.set_rows(
        [
            OperatorRow("Tele2", False, 0.9),
            OperatorRow("MTS", True, 0.5),
            OperatorRow("Megafon", False, 0.1),
            OperatorRow("Beeline", True, 0.8),
        ]
    )
    table, proxy = build_table(
        model,
        secondary_sort=("Доля (%)", Qt.SortOrder.DescendingOrder),
    )

    sort_by_title(table, "В списке", Qt.SortOrder.AscendingOrder)

    assert [proxy.index(row, 0).data() for row in range(proxy.rowCount())] == [
        "Tele2",
        "Megafon",
        "Beeline",
        "MTS",
    ]
