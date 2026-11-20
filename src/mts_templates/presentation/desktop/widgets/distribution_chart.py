"""Горизонтальная гистограмма распределения на `QPainter`, без внешних зависимостей."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from mts_templates.presentation.desktop.distribution import DistributionBar
from mts_templates.presentation.desktop.formatting import format_int, format_percent
from mts_templates.presentation.desktop.theme import active_palette

EXACT_GRADIENT = ("#1f6feb", "#6aa9ff")
GROUPED_GRADIENT = ("#98a2b3", "#c9d0db")
DARK_MUSTARD_GRADIENT = ("#8a6a15", "#bfa03c")

TITLE_HEIGHT = 24.0
CAPTION_HEIGHT = 16.0
ROW_HEIGHT = 24.0
BAR_HEIGHT = 12.0
LABEL_GAP = 10.0
VALUE_GAP = 10.0
BAR_RADIUS = 4.0


class DistributionChart(QWidget):
    """Столбцы «значение — количество — доля» с подписью итога под заголовком."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        exact_gradient: tuple[str, str] = EXACT_GRADIENT,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._caption = ""
        self._bars: tuple[DistributionBar, ...] = ()
        self._exact_gradient = exact_gradient
        self.setMinimumSize(260, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_bars(self, bars: Sequence[DistributionBar], *, caption: str = "") -> None:
        self._bars = tuple(bars)
        self._caption = caption
        self.setMinimumHeight(self._required_height())
        self.update()

    def _required_height(self) -> int:
        rows = max(len(self._bars), 1)
        return int(TITLE_HEIGHT + CAPTION_HEIGHT + rows * ROW_HEIGHT + 16)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        area = self.rect().adjusted(8, 6, -8, -6)
        self._draw_title(painter, QRectF(area.x(), area.y(), area.width(), TITLE_HEIGHT))
        self._draw_caption(
            painter,
            QRectF(area.x(), area.y() + TITLE_HEIGHT, area.width(), CAPTION_HEIGHT),
        )

        rows_top = area.y() + TITLE_HEIGHT + CAPTION_HEIGHT + 6
        rows = QRectF(area.x(), rows_top, area.width(), area.bottom() - rows_top)
        if not self._bars:
            self._draw_empty(painter, rows)
            return
        self._draw_rows(painter, rows)

    def _draw_title(self, painter: QPainter, rect: QRectF) -> None:
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(active_palette().text))
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._title
        )

    def _draw_caption(self, painter: QPainter, rect: QRectF) -> None:
        if not self._caption:
            return
        font = painter.font()
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(active_palette().text_muted))
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self._caption
        )

    def _draw_empty(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QColor(active_palette().text_muted))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "Нет данных")

    def _draw_rows(self, painter: QPainter, rect: QRectF) -> None:
        font = painter.font()
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        values = [_value_text(bar) for bar in self._bars]
        label_width = max(metrics.horizontalAdvance(bar.label) for bar in self._bars) + LABEL_GAP
        value_width = max(metrics.horizontalAdvance(text) for text in values) + VALUE_GAP
        track_left = rect.x() + label_width
        track_width = max(rect.width() - label_width - value_width, 20.0)
        peak = max((bar.count for bar in self._bars), default=0)

        for index, (bar, value) in enumerate(zip(self._bars, values, strict=True)):
            top = rect.y() + index * ROW_HEIGHT
            if top + ROW_HEIGHT > rect.bottom() + 1:
                break
            row = QRectF(rect.x(), top, rect.width(), ROW_HEIGHT)
            self._draw_row(
                painter, row, bar, value, track_left, track_width, peak, metrics.height()
            )

    def _draw_row(
        self,
        painter: QPainter,
        row: QRectF,
        bar: DistributionBar,
        value: str,
        track_left: float,
        track_width: float,
        peak: int,
        text_height: int,
    ) -> None:
        center_y = row.center().y()
        painter.setPen(QColor(active_palette().text))
        painter.drawText(
            QRectF(row.x(), row.y(), track_left - row.x() - LABEL_GAP, row.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            bar.label,
        )

        track = QRectF(track_left, center_y - BAR_HEIGHT / 2, track_width, BAR_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(active_palette().surface_alt))
        painter.drawRoundedRect(track, BAR_RADIUS, BAR_RADIUS)

        if peak > 0 and bar.count > 0:
            fill_width = max(track_width * bar.count / peak, BAR_HEIGHT)
            fill = QRectF(track.x(), track.y(), fill_width, track.height())
            painter.setBrush(
                QBrush(
                    _gradient(
                        fill,
                        GROUPED_GRADIENT if bar.grouped else self._exact_gradient,
                    )
                )
            )
            painter.drawRoundedRect(fill, BAR_RADIUS, BAR_RADIUS)

        painter.setPen(QColor(active_palette().text_muted))
        painter.drawText(
            QRectF(
                track.right() + VALUE_GAP,
                row.y(),
                row.right() - track.right() - VALUE_GAP,
                row.height(),
            ),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            value,
        )


def _value_text(bar: DistributionBar) -> str:
    return f"{format_int(bar.count)} · {format_percent(bar.share)}"


def _gradient(rect: QRectF, colors: tuple[str, str]) -> QLinearGradient:
    gradient = QLinearGradient(QPointF(rect.left(), 0), QPointF(rect.right(), 0))
    gradient.setColorAt(0.0, QColor(colors[0]))
    gradient.setColorAt(1.0, QColor(colors[1]))
    return gradient
