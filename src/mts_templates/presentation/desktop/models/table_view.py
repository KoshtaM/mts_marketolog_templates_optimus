"""Прокси-модель и представление таблицы: сортировка и поиск по строкам."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from mts_templates.presentation.desktop.models.table_model import RowsTableModel

MIN_COLUMN_WIDTH = 48
MIN_STRETCH_WIDTH = 140


class RowsTableView(QTableView):
    """Таблица, которая растягивает одну колонку и подгоняет остальные.

    Ширины колонок берутся из содержимого. Свободное место забирает
    `stretch_column`; при нехватке места она сжимается до `MIN_STRETCH_WIDTH`,
    после чего появляется горизонтальная прокрутка.
    """

    def __init__(
        self,
        *,
        stretch_column: int | None = None,
        min_stretch_width: int = MIN_STRETCH_WIDTH,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stretch_column = stretch_column
        self._min_stretch_width = min_stretch_width
        self._content_widths: list[int] = []
        self._applying = False
        self.horizontalHeader().sectionResized.connect(self._remember_width)

    def fit_to_contents(self, *, max_widths: Mapping[int, int] | None = None) -> None:
        """Подогнать ширины под содержимое, не давая им разрастаться."""
        caps = max_widths or {}
        self._applying = True
        try:
            self.resizeColumnsToContents()
            widths: list[int] = []
            for index in range(self.model().columnCount()):
                width = max(self.columnWidth(index), MIN_COLUMN_WIDTH)
                cap = caps.get(index)
                if cap is not None:
                    width = min(width, cap)
                widths.append(width)
            self._content_widths = widths
            self._apply_widths()
        finally:
            self._applying = False

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_widths()

    def _remember_width(self, index: int, _old: int, new: int) -> None:
        if self._applying or index >= len(self._content_widths):
            return
        self._content_widths[index] = new
        self._apply_widths()

    def _apply_widths(self) -> None:
        if not self._content_widths:
            return

        widths = list(self._content_widths)
        if self._stretch_column is not None:
            index = self._stretch_column
            extra = self.viewport().width() - sum(widths)
            if extra >= 0:
                widths[index] += extra
            else:
                widths[index] = max(self._min_stretch_width, widths[index] + extra)

        self._applying = True
        try:
            for column, width in enumerate(widths):
                self.setColumnWidth(column, width)
        finally:
            self._applying = False


class SortedFilterProxy(QSortFilterProxyModel):
    """Сортирует по `UserRole` и фильтрует по всем колонкам."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def lessThan(
        self,
        left: QModelIndex | QPersistentModelIndex,
        right: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        left_value = left.data(Qt.ItemDataRole.UserRole)
        right_value = right.data(Qt.ItemDataRole.UserRole)
        if left_value is None:
            return True
        if right_value is None:
            return False
        try:
            return bool(left_value < right_value)
        except TypeError:
            return str(left_value) < str(right_value)


def build_table(
    model: RowsTableModel,
    parent: QWidget | None = None,
    *,
    stretch_column: int | None = -1,
    min_stretch_width: int = MIN_STRETCH_WIDTH,
) -> tuple[RowsTableView, SortedFilterProxy]:
    """Таблица с сортировкой по клику на заголовок и прокси-моделью для фильтра.

    `stretch_column` — колонка, забирающая свободное место: `-1` — последняя,
    `None` — свободное место остаётся справа от таблицы, число — указанная.
    `min_stretch_width` — ширина, до которой колонка сжимается при нехватке места.
    """
    proxy = SortedFilterProxy(parent)
    proxy.setSourceModel(model)

    view = RowsTableView(
        stretch_column=None if stretch_column is None else stretch_column,
        min_stretch_width=min_stretch_width,
    )
    view.setModel(proxy)
    view.setSortingEnabled(True)
    view.setAlternatingRowColors(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().setVisible(False)

    header = view.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)

    for index, column in enumerate(model.columns()):
        view.setColumnWidth(index, column.width)
    return view, proxy


def fit_columns(
    view: RowsTableView,
    *,
    max_widths: Mapping[int, int] | None = None,
) -> None:
    """Подогнать ширину колонок под содержимое, не давая им разрастаться."""
    view.fit_to_contents(max_widths=max_widths)
