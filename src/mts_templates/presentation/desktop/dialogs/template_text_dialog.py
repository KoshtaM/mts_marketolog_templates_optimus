"""Окно полного текста шаблона с копированием в буфер обмена."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

COPY_CONFIRMATION = "Скопировано в буфер обмена"


class TemplateTextDialog(QDialog):
    """Показывает текст шаблона целиком и копирует его по кнопке."""

    def __init__(
        self,
        text: str,
        *,
        title: str = "Текст шаблона",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self.setWindowTitle(title)
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        caption = QLabel("Полный текст шаблона:", self)
        layout.addWidget(caption)

        editor = QPlainTextEdit(text, self)
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setObjectName("templateTextView")
        layout.addWidget(editor, stretch=1)

        buttons = QHBoxLayout()
        self._status = QLabel("", self)
        self._status.setObjectName("templateTextStatus")
        self._copy_button = QPushButton("Копировать", self)
        self._copy_button.setDefault(True)
        close_button = QPushButton("Закрыть", self)
        buttons.addWidget(self._status, stretch=1)
        buttons.addWidget(self._copy_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._copy_button.clicked.connect(self._copy)
        close_button.clicked.connect(self.accept)
        editor.setFocus()
        editor.selectAll()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text)
        self._status.setText(COPY_CONFIRMATION)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
