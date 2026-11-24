"""Круговая диаграмма долей на `QPainter`, без внешних зависимостей."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mts_templates.presentation.desktop.theme import active_palette

PIE_DIAMETER_RATIO = 1.5
"""Диаметр круговой диаграммы: задаётся как значение × `PIE_DIAMETER_RATIO` (в 1,5 раза меньше)."""


@dataclass(frozen=True, slots=True)
class PieSlice:
    """Сектор диаграммы: подпись, значение и цвет."""

    label: str
    value: float
    color: str


class PieChart(QWidget):
    """Показывает доли значений; нулевые и отрицательные сектора игнорируются."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._slices: tuple[PieSlice, ...] = ()
        self.setMinimumSize(150, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_slices(self, slices: Sequence[PieSlice]) -> None:
        self._slices = tuple(item for item in slices if item.value > 0)
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        area = self.rect().adjusted(8, 6, -8, -6)
        title_height = 24
        self._draw_title(painter, QRectF(area.x(), area.y(), area.width(), title_height))

        content = QRectF(
            area.x(),
            area.y() + title_height,
            area.width(),
            area.height() - title_height,
        )
        legend_rows = max(len(self._slices), 1)
        legend_height = legend_rows * 16 + 6
        pie_size = (
            max(40.0, min(content.width() - 6, content.height() - legend_height - 6))
            / PIE_DIAMETER_RATIO
        )
        pie_rect = QRectF(
            content.x() + (content.width() - pie_size) / 2,
            content.y() + 2,
            pie_size,
            pie_size,
        )
        self._draw_pie(painter, pie_rect)
        self._draw_legend(painter, content, pie_rect)

    def _draw_title(self, painter: QPainter, rect: QRectF) -> None:
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(active_palette().text))
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._title,
        )

    def _draw_pie(self, painter: QPainter, rect: QRectF) -> None:
        palette = active_palette()
        total = sum(item.value for item in self._slices)
        if total <= 0:
            painter.setPen(QPen(QColor(palette.border), 1))
            painter.setBrush(QColor(palette.surface_alt))
            painter.drawEllipse(rect)
            painter.setPen(QColor(palette.text_muted))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "Нет данных")
            return

        start_angle = 90 * 16
        painter.setPen(QPen(QColor(palette.surface), 1))
        for item in self._slices:
            span = round(-item.value / total * 360 * 16)
            painter.setBrush(QColor(item.color))
            painter.drawPie(rect, start_angle, span)
            start_angle += span

    def _draw_legend(self, painter: QPainter, content: QRectF, pie_rect: QRectF) -> None:
        if not self._slices:
            return

        font = painter.font()
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        total = sum(item.value for item in self._slices)
        top = pie_rect.bottom() + 6
        row_height = 16.0
        for index, item in enumerate(self._slices):
            y = top + index * row_height
            if y + row_height > content.bottom() + 2:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(item.color))
            painter.drawRect(QRectF(content.x(), y + 4, 9, 9))

            share = item.value / total if total else 0.0
            text = f"{item.label} — {share * 100:.1f}%"
            available = content.width() - 15
            painter.setPen(QColor(active_palette().text_muted))
            painter.drawText(
                QRectF(content.x() + 14, y, available, row_height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(available)),
            )
