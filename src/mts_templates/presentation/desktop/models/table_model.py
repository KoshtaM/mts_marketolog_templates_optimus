"""Модель таблицы поверх списка DTO."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.contrast import (
    MIN_CONTRAST,
    contrast_ratio,
    readable_text_color,
)
from mts_templates.presentation.desktop.formatting import format_bool_icon, format_money
from mts_templates.presentation.desktop.theme import active_palette


def default_format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Money):
        return format_money(value)
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, bool):
        return format_bool_icon(value)
    return str(value)


def sort_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Money):
        return float(value.amount)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value.casefold()
    return value


def _bool_color(value: bool, background: str) -> str:
    """Цвет галочки/крестика из темы, при слабом контрасте — читаемый текст."""
    palette = active_palette()
    candidate = palette.positive if value else palette.negative
    if contrast_ratio(candidate, background) >= MIN_CONTRAST:
        return candidate
    return readable_text_color(background)


@dataclass(frozen=True)
class Column:
    """Описание колонки: заголовок, значение и формат отображения."""

    title: str
    getter: Callable[[Any], Any]
    formatter: Callable[[Any], str] = field(default=default_format)
    width: int = 120
    tooltip: Callable[[Any], str] | None = None


class RowsTableModel(QAbstractTableModel):
    """Показывает строки DTO; сортировка и фильтрация — в прокси-модели.

    `row_color` задаёт цвет фона всей строки: возвращает `QColor` или None.
    Текст поверх заливки выбирается по контрасту, поэтому подсветка выгоды
    читается и в светлых, и в тёмных темах.
    """

    def __init__(
        self,
        columns: Sequence[Column],
        parent: Any = None,
        *,
        row_color: Callable[[Any], QColor | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = tuple(columns)
        self._rows: list[Any] = []
        self._row_color = row_color

    def set_rows(self, rows: Sequence[Any]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def refresh(self) -> None:
        """Перерисовать строки: изменились настройки цвета или оформления."""
        if not self._rows or not self._columns:
            return
        top = self.index(0, 0)
        bottom = self.index(len(self._rows) - 1, len(self._columns) - 1)
        self.dataChanged.emit(
            top,
            bottom,
            [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
        )

    def _background(self, row: int) -> QColor | None:
        if self._row_color is None:
            return None
        return self._row_color(self._rows[row])

    def _foreground(self, row: int, value: Any, background: QColor | None) -> QColor | None:
        """Читаемый цвет текста: поверх заливки строки и для булевых значений."""
        if background is not None:
            fill = background.name()
            if isinstance(value, bool):
                return QColor(_bool_color(value, fill))
            return QColor(readable_text_color(fill))
        if isinstance(value, bool):
            return QColor(_bool_color(value, active_palette().surface))
        return None

    def rows(self) -> tuple[Any, ...]:
        return tuple(self._rows)

    def row_at(self, row: int) -> Any:
        return self._rows[row]

    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008
    ) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        column = self._columns[index.column()]
        value = column.getter(self._rows[index.row()])
        if role == Qt.ItemDataRole.DisplayRole:
            return column.formatter(value)
        if role == Qt.ItemDataRole.ToolTipRole:
            if isinstance(value, bool):
                return None
            if column.tooltip is not None:
                return column.tooltip(self._rows[index.row()])
            return column.formatter(value)
        if role == Qt.ItemDataRole.UserRole:
            return sort_value(value)
        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(index.row(), value, self._background(index.row()))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(value, bool):
                return int(Qt.AlignmentFlag.AlignCenter)
            if isinstance(value, (int, float, Money)):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._background(index.row())
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].title
        return section + 1

    def columns(self) -> tuple[Column, ...]:
        return self._columns
