"""Индикатор длительной операции: вращающийся кружок и бесконечный прогресс-бар."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

SPINNER_DIAMETER = 18
SPINNER_INTERVAL_MS = 60
SPINNER_STEP_DEGREES = 30
SPINNER_ARC_DEGREES = 100
SPINNER_PEN_WIDTH = 2.4
SPINNER_COLOR = "#2f6fba"
PROGRESS_HEIGHT = 10


class BusySpinner(QWidget):
    """Кружок с вращающейся дугой; анимацию гоняет QTimer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SPINNER_DIAMETER, SPINNER_DIAMETER)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(SPINNER_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._angle = (self._angle + SPINNER_STEP_DEGREES) % 360
        self.update()

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(SPINNER_COLOR), SPINNER_PEN_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        margin = pen.widthF() / 2 + 0.5
        side = SPINNER_DIAMETER - margin * 2
        rect = QRectF(margin, margin, side, side)
        painter.drawArc(rect, self._angle * 16, SPINNER_ARC_DEGREES * 16)


class BusyBar(QWidget):
    """Строка «кружок + подпись + бесконечный прогресс-бар».

    Показывается на время фоновой операции: `start(text)` запускает
    анимацию, `stop()` прячет строку и останавливает таймер.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spinner = BusySpinner(self)
        self._text = QLabel(self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)
        self._bar.setFixedHeight(PROGRESS_HEIGHT)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._spinner)
        row.addWidget(self._text)
        row.addWidget(self._bar, stretch=1)
        self.setVisible(False)

    def start(self, text: str) -> None:
        self._text.setText(text)
        self.setVisible(True)
        self._spinner.start()

    def stop(self) -> None:
        self.setVisible(False)
        self._spinner.stop()
