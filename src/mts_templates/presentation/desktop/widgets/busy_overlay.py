"""Индикатор длительной операции: вращающийся кружок в центре таблицы.

Быстрые операции (результат из кэша анализа) завершаются раньше первого
кадра, поэтому индикатор держится на экране минимум `MIN_VISIBLE_MS`:
иначе пользователь не видит, что действие вообще выполнялось.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QLabel, QVBoxLayout, QWidget
from shiboken6 import isValid

from mts_templates.presentation.desktop.contrast import readable_text_color
from mts_templates.presentation.desktop.theme import active_palette

SPINNER_DIAMETER = 18
OVERLAY_SPINNER_DIAMETER = 40
SPINNER_INTERVAL_MS = 60
SPINNER_STEP_DEGREES = 30
SPINNER_ARC_DEGREES = 100
SPINNER_MIN_PEN_WIDTH = 2.0
SPINNER_PEN_RATIO = 0.12
MIN_VISIBLE_MS = 450
OVERLAY_ALPHA = 225
OVERLAY_LABEL_FONT_SIZE = 13


def remaining_visible_ms(elapsed_ms: int, minimum_ms: int = MIN_VISIBLE_MS) -> int:
    """Сколько ещё держать индикатор, чтобы он не мигнул на быстрой операции."""
    return max(0, minimum_ms - max(elapsed_ms, 0))


class BusySpinner(QWidget):
    """Кружок с вращающейся дугой; анимацию гоняет QTimer."""

    def __init__(self, parent: QWidget | None = None, *, diameter: int = SPINNER_DIAMETER) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._pen_width = max(SPINNER_MIN_PEN_WIDTH, diameter * SPINNER_PEN_RATIO)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(SPINNER_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(diameter, diameter)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + SPINNER_STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(active_palette().accent), self._pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = pen.widthF() / 2 + 0.5
        side = self._diameter - margin * 2
        painter.drawArc(
            QRectF(margin, margin, side, side),
            self._angle * 16,
            SPINNER_ARC_DEGREES * 16,
        )


class BusyOverlay(QWidget):
    """Полупрозрачный слой с кружком и подписью поверх таблицы.

    `start(text)` показывает слой и запускает анимацию, `stop()` прячет его,
    но не раньше `MIN_VISIBLE_MS`. Слой не перехватывает мышь: кнопки на время
    операции блокирует сама страница.
    """

    def __init__(self, table: QAbstractScrollArea) -> None:
        viewport = table.viewport()
        super().__init__(viewport)
        self._viewport = viewport
        self._spinner = BusySpinner(self, diameter=OVERLAY_SPINNER_DIAMETER)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label)
        layout.addStretch(1)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide)
        self._started_at = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        viewport.installEventFilter(self)
        self.refresh_theme()
        self.setVisible(False)

    def start(self, text: str) -> None:
        self._hide_timer.stop()
        self._started_at = time.monotonic()
        self._label.setText(text)
        self._sync_geometry()
        self.setVisible(True)
        self.raise_()
        self._spinner.start()

    def stop(self) -> None:
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        delay_ms = remaining_visible_ms(elapsed_ms)
        if delay_ms:
            self._hide_timer.start(delay_ms)
            return
        self._hide()

    def refresh_theme(self) -> None:
        """Перекрасить подпись под активную тему."""
        text_color = readable_text_color(active_palette().surface)
        self._label.setStyleSheet(
            f"color: {text_color}; font-size: {OVERLAY_LABEL_FONT_SIZE}px; background: transparent;"
        )
        self.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize and isValid(self):
            self._sync_geometry()
        return False

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        background = QColor(active_palette().surface)
        background.setAlpha(OVERLAY_ALPHA)
        painter.fillRect(self.rect(), background)

    def _sync_geometry(self) -> None:
        if isValid(self._viewport):
            self.setGeometry(self._viewport.rect())

    def _hide(self) -> None:
        self._spinner.stop()
        self.setVisible(False)
