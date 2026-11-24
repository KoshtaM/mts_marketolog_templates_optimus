"""Окно со списком реальных сообщений, подпавших под шаблон или кандидата."""

from __future__ import annotations

from collections.abc import Sequence

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

from mts_templates.application.dto import MatchedMessageView
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import build_table, fit_columns

MESSAGE_TEXT_LIMIT = 140
COPY_CONFIRMATION = "Скопировано в буфер обмена"
TEMPLATE_TEXT_HEIGHT = 90


def _short_text(text: str) -> str:
    if len(text) <= MESSAGE_TEXT_LIMIT:
        return text
    return text[:MESSAGE_TEXT_LIMIT] + "…"


COLUMNS = (
    Column(
        "Сообщение",
        lambda item: item.text,
        formatter=_short_text,
        width=380,
        tooltip=lambda item: item.text,
    ),
    Column("Длина", lambda item: item.segments, width=150),
    Column("Номер", lambda item: item.masked_recipient, width=140),
    Column("Дата/Время отправки", lambda item: item.sent_at, width=165),
    Column("Оператор", lambda item: item.operator, width=115),
    Column("Статус доставки", lambda item: item.delivery_status, width=180),
)


class MatchedMessagesDialog(QDialog):
    """Таблица подпавших сообщений: строки приходят из выгрузки, без пересчёта."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сообщения шаблона")
        self.resize(1150, 620)

        self._count = QLabel("Найдено сообщений: 0", self)
        self._hint = QLabel(
            "Номера получателей замаскированы; полный текст — в подсказке ячейки.", self
        )
        self._template_label = QLabel("Полный текст шаблона:", self)
        self._template_text = QPlainTextEdit(self)
        self._template_text.setReadOnly(True)
        self._template_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._template_text.setMaximumHeight(TEMPLATE_TEXT_HEIGHT)
        self._template_text.setObjectName("templateTextView")
        self._copy_button = QPushButton("Копировать", self)
        self._copy_status = QLabel("", self)
        self._model = RowsTableModel(COLUMNS, self)
        self._table, _proxy = build_table(self._model, self, stretch_column=0)
        self._close = QPushButton("Закрыть", self)
        self._close.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._template_label)
        text_row = QHBoxLayout()
        text_row.addWidget(self._template_text, stretch=1)
        copy_column = QVBoxLayout()
        copy_column.addWidget(self._copy_button)
        copy_column.addWidget(self._copy_status)
        copy_column.addStretch(1)
        text_row.addLayout(copy_column)
        layout.addLayout(text_row)
        layout.addWidget(self._count)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._hint)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._close)
        layout.addLayout(buttons)

        self._copy_button.clicked.connect(self._copy_template_text)

    def set_rows(
        self,
        rows: Sequence[MatchedMessageView],
        *,
        title: str,
        template_text: str,
        template_label: str = "Полный текст шаблона:",
    ) -> None:
        """Показать сообщения, заголовок окна и текст шаблона целиком."""
        self.setWindowTitle(title)
        self._template_label.setText(template_label)
        self._template_text.setPlainText(template_text)
        self._copy_status.clear()
        self._model.set_rows(rows)
        fit_columns(self._table, max_widths={0: 600})
        self._count.setText(f"Найдено сообщений: {len(rows)}")

    def _copy_template_text(self) -> None:
        QGuiApplication.clipboard().setText(self._template_text.toPlainText())
        self._copy_status.setText(COPY_CONFIRMATION)
