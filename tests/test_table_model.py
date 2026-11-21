"""Тесты модели таблицы: форматирование, подсказки и цвет строки."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.contrast import (
    MIN_CONTRAST,
    contrast_ratio,
    readable_text_color,
)
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel


@dataclass(frozen=True)
class Row:
    title: str
    amount: Money
    active: bool


ROW = Row("Длинный шаблон с переменной %d", Money.from_rub("12.50"), True)
COLUMNS = (
    Column("Шаблон", lambda item: item.title),
    Column("Сумма", lambda item: item.amount),
    Column("Активен", lambda item: item.active),
)


def make_model() -> RowsTableModel:
    model = RowsTableModel(COLUMNS)
    model.set_rows([ROW])
    return model


def test_display_role_formats_values() -> None:
    model = make_model()

    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == ROW.title
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "12.50 ₽"
    assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == "✔"


def test_tooltip_shows_full_text() -> None:
    model = make_model()

    assert model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole) == ROW.title


def test_column_tooltip_overrides_display_text() -> None:
    model = RowsTableModel(
        (Column("Шаблон", lambda item: item.title, tooltip=lambda item: f"full: {item.title}"),)
    )
    model.set_rows([ROW])

    assert model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole) == f"full: {ROW.title}"


def test_bool_has_no_tooltip() -> None:
    model = make_model()

    assert model.data(model.index(0, 2), Qt.ItemDataRole.ToolTipRole) is None


def test_row_color_applies_to_background() -> None:
    model = RowsTableModel(COLUMNS, row_color=lambda item: QColor("#c8e6c9"))
    model.set_rows([ROW])

    assert model.data(model.index(0, 0), Qt.ItemDataRole.BackgroundRole) == QColor("#c8e6c9")


def test_row_text_contrasts_with_row_background() -> None:
    fill = "#121916"
    model = RowsTableModel(COLUMNS, row_color=lambda item: QColor(fill))
    model.set_rows([ROW])

    foreground = model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole)

    assert foreground == QColor(readable_text_color(fill))
    assert contrast_ratio(foreground.name(), fill) >= MIN_CONTRAST


def test_bool_colors_stay_readable_on_row_background() -> None:
    fill = "#e6c8c8"
    model = RowsTableModel(COLUMNS, row_color=lambda item: QColor(fill))
    model.set_rows([ROW, Row("Убыток", Money.from_rub("-1"), False)])

    for row in (0, 1):
        foreground = model.data(model.index(row, 2), Qt.ItemDataRole.ForegroundRole)
        assert isinstance(foreground, QColor)
        assert contrast_ratio(foreground.name(), fill) >= MIN_CONTRAST
