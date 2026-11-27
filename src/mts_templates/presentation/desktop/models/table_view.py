"""Прокси-модель и представление таблицы: сортировка и поиск по строкам."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
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
    """Таблица с подгонкой ширин под содержимое и ширину окна.

    Ширины колонок берутся из содержимого. Свободное место забирает
    `stretch_column`; при нехватке места она сжимается до `MIN_STRETCH_WIDTH`.
    В режиме `fit_to_viewport` все колонки пропорционально сжимаются до
    ширины видимой области — горизонтальной прокрутки нет, а длинный текст
    доступен в подсказке ячейки.
    """

    def __init__(
        self,
        *,
        stretch_column: int | None = None,
        min_stretch_width: int = MIN_STRETCH_WIDTH,
        fit_to_viewport: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stretch_column = None if fit_to_viewport else stretch_column
        self._min_stretch_width = min_stretch_width
        self._fit_to_viewport = fit_to_viewport
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

    def _shrink_to_viewport(self, widths: list[int], available: int) -> list[int]:
        """Пропорционально ужать колонки, сохраняя минимальную ширину."""
        if available <= 0 or sum(widths) <= available:
            return widths

        excess = sum(widths) - available
        reducible = sum(width - MIN_COLUMN_WIDTH for width in widths if width > MIN_COLUMN_WIDTH)
        if reducible > 0:
            take = min(excess, reducible)
            widths = [
                width - round((width - MIN_COLUMN_WIDTH) * take / reducible) for width in widths
            ]

        # Если даже минимальных ширин не хватает, делим место поровну.
        total = sum(widths)
        if total > available:
            ratio = available / total
            widths = [max(24, int(width * ratio)) for width in widths]
        while sum(widths) > available and max(widths) > 24:
            largest = max(range(len(widths)), key=widths.__getitem__)
            widths[largest] -= 1
        return widths

    def _apply_widths(self) -> None:
        if not self._content_widths:
            return

        widths = list(self._content_widths)
        available = self.viewport().width()
        if self._fit_to_viewport:
            widths = self._shrink_to_viewport(widths, available)
        elif self._stretch_column is not None:
            index = self._stretch_column
            extra = available - sum(widths)
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


def column_index(model: QAbstractItemModel, title: str) -> int:
    """Номер колонки по заголовку."""
    for index in range(model.columnCount()):
        if model.headerData(index, Qt.Orientation.Horizontal) == title:
            return index
    raise ValueError(f"Колонка {title!r} не найдена")


def _compare(left: Any, right: Any) -> int:
    """Сравнение значений сортировки: -1, 0 или 1."""
    if left is None:
        return 0 if right is None else -1
    if right is None:
        return 1
    try:
        if left < right:
            return -1
        if right < left:
            return 1
    except TypeError:
        left_text, right_text = str(left), str(right)
        if left_text < right_text:
            return -1
        if right_text < left_text:
            return 1
    return 0


class SortedFilterProxy(QSortFilterProxyModel):
    """Сортирует по `UserRole` и фильтрует по всем колонкам.

    `secondary_sort` — колонка и направление, которые разводят строки с
    одинаковым значением основной колонки.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        secondary_sort: tuple[int, Qt.SortOrder] | None = None,
    ) -> None:
        super().__init__(parent)
        self._secondary_sort = secondary_sort
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def lessThan(
        self,
        left: QModelIndex | QPersistentModelIndex,
        right: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        primary = _compare(
            left.data(Qt.ItemDataRole.UserRole),
            right.data(Qt.ItemDataRole.UserRole),
        )
        if primary != 0:
            return primary < 0
        if self._secondary_sort is None:
            return False
        column, order = self._secondary_sort
        model = self.sourceModel()
        if model is None:
            return False
        secondary = _compare(
            model.index(left.row(), column).data(Qt.ItemDataRole.UserRole),
            model.index(right.row(), column).data(Qt.ItemDataRole.UserRole),
        )
        if secondary == 0:
            return False
        result = secondary < 0 if order == Qt.SortOrder.AscendingOrder else secondary > 0
        # Прокси инвертирует результат lessThan при нисходящей основной сортировке.
        return not result if self.sortOrder() == Qt.SortOrder.DescendingOrder else result


def build_table(
    model: RowsTableModel,
    parent: QWidget | None = None,
    *,
    stretch_column: int | None = -1,
    min_stretch_width: int = MIN_STRETCH_WIDTH,
    fit_to_viewport: bool = False,
    secondary_sort: tuple[str, Qt.SortOrder] | None = None,
) -> tuple[RowsTableView, SortedFilterProxy]:
    """Таблица с сортировкой по клику на заголовок и прокси-моделью для фильтра.

    `stretch_column` — колонка, забирающая свободное место: `-1` — последняя,
    `None` — свободное место остаётся справа от таблицы, число — указанная.
    `min_stretch_width` — ширина, до которой колонка сжимается при нехватке места.
    `fit_to_viewport` — подогнать все колонки под видимую ширину без прокрутки.
    `secondary_sort` — заголовок и направление дополнительной сортировки при
    совпадении значения основной колонки.
    """
    fallback = (
        None
        if secondary_sort is None
        else (column_index(model, secondary_sort[0]), secondary_sort[1])
    )
    proxy = SortedFilterProxy(parent, secondary_sort=fallback)
    proxy.setSourceModel(model)

    view = RowsTableView(
        stretch_column=None if stretch_column is None else stretch_column,
        min_stretch_width=min_stretch_width,
        fit_to_viewport=fit_to_viewport,
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


def sort_by_title(view: RowsTableView, title: str, order: Qt.SortOrder) -> None:
    """Задать сортировку по заголовку колонки и показать индикатор в шапке."""
    model = view.model()
    if model is None:
        raise ValueError("У таблицы нет модели")
    view.horizontalHeader().setSortIndicator(column_index(model, title), order)
