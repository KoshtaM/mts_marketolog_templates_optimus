"""Информационный блок с крупной цветной суммой: подпись и значение."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

VALUE_FONT_SIZE = 20

PROFIT_COLOR = "#1b7f3a"
LOSS_TEXT_COLOR = "#b42318"
MODERATE_COLOR = "#4c9a58"
NEUTRAL_COLOR = "#1f2a37"


class BenefitTotal(QFrame):
    """Подпись и крупное число: суммарная выгода или убыток по группе строк."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caption = QLabel(caption, self)
        self._caption.setObjectName("benefitTotalCaption")
        self._caption.setWordWrap(True)
        self._value = QLabel("—", self)
        self._value.setObjectName("benefitTotalValue")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        layout.addStretch(1)

        self.set_value("—", NEUTRAL_COLOR)

    def set_value(self, text: str, color: str) -> None:
        """Показать значение; цвет — имя цвета из `benefit_totals`."""
        self._value.setText(text)
        self._value.setStyleSheet(
            f"color: {color}; font-size: {VALUE_FONT_SIZE}px; font-weight: 600;"
        )

    def reset(self) -> None:
        self.set_value("—", NEUTRAL_COLOR)

    def caption(self) -> str:
        return self._caption.text()
