"""Небольшая кнопка в ячейке таблицы: открывает связанный список сообщений."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QWidget,
)

BUTTON_WIDTH = 34
BUTTON_HEIGHT = 24


class CellButtonDelegate(QStyledItemDelegate):
    """Кнопка, которая рисуется в ячейке и сообщает о щелчке по ней."""

    clicked = Signal(QModelIndex)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        button = QStyleOptionButton()
        button.rect = self._button_rect(option.rect)
        button.text = self._text
        button.state = option.state
        QApplication.style().drawControl(QStyle.ControlElement.CE_PushButton, button, painter)

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(BUTTON_WIDTH, BUTTON_HEIGHT)

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() is not QEvent.Type.MouseButtonRelease:
            return False
        if not isinstance(event, QMouseEvent) or event.button() is not Qt.MouseButton.LeftButton:
            return False
        if not self._button_rect(option.rect).contains(event.position().toPoint()):
            return False
        if isinstance(index, QModelIndex):
            source = index
        else:
            model = index.model()
            if model is None:
                return False
            source = model.index(index.row(), index.column())
        self.clicked.emit(source)
        return True

    @staticmethod
    def _button_rect(rect: QRect) -> QRect:
        width = min(BUTTON_WIDTH, rect.width())
        return QRect(
            rect.x(), rect.y() + (rect.height() - BUTTON_HEIGHT) // 2, width, BUTTON_HEIGHT
        )
