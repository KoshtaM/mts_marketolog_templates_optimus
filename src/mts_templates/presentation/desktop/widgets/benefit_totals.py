"""Информационный блок с крупной цветной суммой: подпись и значение."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mts_templates.presentation.desktop.contrast import readable_text_color
from mts_templates.presentation.desktop.theme import active_palette

VALUE_FONT_SIZE = 20
INLINE_VALUE_FONT_SIZE = 22
INLINE_CAPTION_FONT_SIZE = 13

PROFIT_COLOR = "#1b7f3a"
LOSS_TEXT_COLOR = "#b42318"
MODERATE_COLOR = "#4c9a58"
NEUTRAL_COLOR = "#667085"


def neutral_color() -> str:
    """Цвет прочерка, читаемый на фоне активной темы."""
    return readable_text_color(active_palette().window)


class BenefitTotal(QFrame):
    """Подпись и крупное число: суммарная выгода или убыток по группе строк.

    В обычном режиме подпись стоит над значением; `inline=True` кладёт значение
    и подпись в одну строку, чтобы несколько итогов занимали по одной строке.
    """

    def __init__(
        self,
        caption: str,
        parent: QWidget | None = None,
        *,
        inline: bool = False,
    ) -> None:
        super().__init__(parent)
        self._value_font_size = INLINE_VALUE_FONT_SIZE if inline else VALUE_FONT_SIZE
        self._caption = QLabel(caption, self)
        self._caption.setObjectName("benefitTotalCaption")
        self._value = QLabel("—", self)
        self._value.setObjectName("benefitTotalValue")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout: QBoxLayout
        if inline:
            self._caption.setWordWrap(False)
            self._caption.setToolTip(caption)
            self._caption.setStyleSheet(f"font-size: {INLINE_CAPTION_FONT_SIZE}px;")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(10, 5, 10, 5)
            layout.setSpacing(10)
            layout.addWidget(self._value, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(self._caption, 1, Qt.AlignmentFlag.AlignVCenter)
        else:
            self._caption.setWordWrap(True)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(2)
            layout.addWidget(self._caption)
            layout.addWidget(self._value)
            layout.addStretch(1)

        self.reset()

    def set_value(self, text: str, color: str) -> None:
        """Показать значение; цвет — имя цвета из `benefit_totals`."""
        self._value.setText(text)
        self._value.setStyleSheet(
            f"color: {color}; font-size: {self._value_font_size}px; font-weight: 600;"
        )

    def reset(self) -> None:
        self.set_value("—", neutral_color())

    def caption(self) -> str:
        return str(self._caption.text())
