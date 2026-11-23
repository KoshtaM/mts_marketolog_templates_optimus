"""Составная столбчатая диаграмма по дням на `QPainter`, без внешних зависимостей."""

from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mts_templates.presentation.desktop.daily_chart import StackedBar, nice_scale
from mts_templates.presentation.desktop.formatting import format_int
from mts_templates.presentation.desktop.theme import active_palette

TITLE_HEIGHT = 24.0
TITLE_FONT_SIZE = 10
AUX_FONT_SIZE = 8
LEGEND_ROW_HEIGHT = 18.0
LEGEND_SWATCH = 9.0
LEGEND_ITEM_GAP = 14.0
LEGEND_TEXT_GAP = 5.0
X_LABEL_HEIGHT = 18.0
X_LABEL_GAP = 8.0
Y_LABEL_GAP = 8.0
Y_LABEL_HEIGHT = 16.0
PLOT_TOP_GAP = 8.0
BAR_GAP = 2.0
BAR_GAP_RATIO = 0.2
MIN_BAR_WIDTH = 3.0
MIN_OVERLAY_HEIGHT = 2.0
MIN_PLOT_HEIGHT = 60.0
MIN_WIDTH = 320
COMPACT_MIN_WIDTH = 240
# Накладки всех столбцов начинаются на 20 % высоты самого маленького ненулевого
# столбца: так оранжевые части дневного графика стоят на одной высоте.
OVERLAY_BASE_RATIO = 0.2
EMPTY_TEXT = "Нет данных"


def bar_width_for_slot(slot: float) -> float:
    """Ширина столбца: зазор 20 % слота, но не меньше 2 px."""
    gap = max(slot * BAR_GAP_RATIO, BAR_GAP)
    return min(max(slot - gap, MIN_BAR_WIDTH), slot)


def overlay_base_offset(
    bar_heights: Sequence[float],
    ratio: float = OVERLAY_BASE_RATIO,
) -> float:
    """Общее начало накладок: доля высоты самого маленького ненулевого столбца."""
    nonzero = [height for height in bar_heights if height > 0]
    if not nonzero or ratio <= 0:
        return 0.0
    return min(nonzero) * ratio


def overlay_geometry(
    bar_height: float,
    value_height: float,
    base_offset: float,
) -> tuple[float, float] | None:
    """Смещение от основания и высота накладки внутри столбца.

    `base_offset` — общая для всех столбцов высота начала накладки в пикселях.
    Накладка не выходит за верх столбца и остаётся видимой даже при малом
    значении. `None` — рисовать нечего.
    """
    if bar_height <= 0 or value_height <= 0:
        return None
    offset = min(max(base_offset, 0.0), max(bar_height - MIN_OVERLAY_HEIGHT, 0.0))
    available = bar_height - offset
    if available <= 0:
        return None
    height = min(max(value_height, MIN_OVERLAY_HEIGHT), available)
    return offset, height


class StackedBarChart(QWidget):
    """Столбцы по дням, составленные из сегментов операторов.

    `set_data` принимает столбцы и легенду `(оператор, цвет)`. Цвета частей
    задаются вызывающим кодом, чтобы совпадать с круговыми диаграммами.
    """

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._caption = ""
        self._bars: tuple[StackedBar, ...] = ()
        self._legend: tuple[tuple[str, str], ...] = ()
        self.setMinimumSize(COMPACT_MIN_WIDTH if compact else MIN_WIDTH, 150 if compact else 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(
        self,
        bars: Sequence[StackedBar],
        *,
        legend: Sequence[tuple[str, str]] = (),
        caption: str = "",
    ) -> None:
        self._bars = tuple(bars)
        self._legend = tuple(legend)
        self._caption = caption
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        area = QRectF(self.rect().adjusted(8, 6, -8, -6))
        self._draw_title(painter, QRectF(area.x(), area.y(), area.width(), TITLE_HEIGHT))

        plot_top = area.y() + TITLE_HEIGHT
        plot_top += self._draw_legend(painter, area, plot_top) + PLOT_TOP_GAP
        plot_bottom = area.bottom() - X_LABEL_HEIGHT
        plot = QRectF(area.x(), plot_top, area.width(), plot_bottom - plot_top)
        if not self._bars or plot.height() < MIN_PLOT_HEIGHT:
            self._draw_empty(painter, plot)
            return
        self._draw_plot(painter, plot)

    def _draw_title(self, painter: QPainter, rect: QRectF) -> None:
        palette = active_palette()
        title_font = QFont(painter.font())
        title_font.setPointSize(TITLE_FONT_SIZE)
        title_font.setBold(True)
        title_metrics = QFontMetrics(title_font)

        caption_font = QFont(title_font)
        caption_font.setPointSize(AUX_FONT_SIZE)
        caption_font.setBold(False)
        caption_metrics = QFontMetrics(caption_font)

        caption_width = 0.0
        if self._caption:
            caption_width = caption_metrics.horizontalAdvance(self._caption) + 12.0

        title_width = max(0.0, rect.width() - caption_width)
        title = title_metrics.elidedText(self._title, Qt.TextElideMode.ElideRight, int(title_width))
        painter.setFont(title_font)
        painter.setPen(QColor(palette.text))
        painter.drawText(
            QRectF(rect.x(), rect.y(), title_width, rect.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            title,
        )
        if not self._caption:
            return

        painter.setFont(caption_font)
        painter.setPen(QColor(palette.text_muted))
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            self._caption,
        )

    def _draw_legend(self, painter: QPainter, area: QRectF, top: float) -> float:
        """Легенда операторов в одну или несколько строк; вернуть её высоту."""
        if not self._legend:
            return 0.0

        font = QFont(painter.font())
        font.setPointSize(AUX_FONT_SIZE)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        palette = active_palette()

        rows = _pack_legend(self._legend, metrics, area.width())
        for row_index, row in enumerate(rows):
            y = top + row_index * LEGEND_ROW_HEIGHT
            x = area.x()
            for label, color in row:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(color))
                painter.drawRect(QRectF(x, y + 4, LEGEND_SWATCH, LEGEND_SWATCH))
                x += LEGEND_SWATCH + LEGEND_TEXT_GAP
                painter.setPen(QColor(palette.text_muted))
                painter.drawText(
                    QRectF(x, y, metrics.horizontalAdvance(label), LEGEND_ROW_HEIGHT),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    label,
                )
                x += metrics.horizontalAdvance(label) + LEGEND_ITEM_GAP
        return len(rows) * LEGEND_ROW_HEIGHT

    def _draw_plot(self, painter: QPainter, plot: QRectF) -> None:
        peak = max(round(bar.total) for bar in self._bars)
        if peak <= 0:
            self._draw_empty(painter, plot)
            return

        font = QFont(painter.font())
        font.setPointSize(AUX_FONT_SIZE)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        step, top = nice_scale(peak)
        labels = tuple(format_int(value) for value in range(0, top + 1, step))
        label_width = float(max((metrics.horizontalAdvance(text) for text in labels), default=0))
        label_width += Y_LABEL_GAP
        chart = QRectF(plot.x() + label_width, plot.y(), plot.width() - label_width, plot.height())
        if chart.width() <= 0:
            self._draw_empty(painter, plot)
            return

        self._draw_grid(painter, chart, labels, step, top, label_width)
        self._draw_bars(painter, chart, top)
        self._draw_day_labels(painter, chart, metrics)

    def _draw_grid(
        self,
        painter: QPainter,
        chart: QRectF,
        labels: Sequence[str],
        step: int,
        top: int,
        label_width: float,
    ) -> None:
        """Горизонтальная сетка и подписи оси Y слева от графика."""
        palette = active_palette()
        line_pen = QPen(QColor(palette.border), 1)
        text_color = QColor(palette.text_muted)
        label_rect = QRectF(
            chart.left() - label_width,
            0.0,
            label_width - Y_LABEL_GAP,
            Y_LABEL_HEIGHT,
        )
        for index, text in enumerate(labels):
            value = index * step
            y = chart.bottom() - (value / top) * chart.height() if top else chart.bottom()
            painter.setPen(line_pen)
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
            painter.setPen(text_color)
            painter.drawText(
                QRectF(label_rect.x(), y - Y_LABEL_HEIGHT / 2, label_rect.width(), Y_LABEL_HEIGHT),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                text,
            )

    def _draw_bars(self, painter: QPainter, chart: QRectF, top: int) -> None:
        palette = active_palette()
        slot = chart.width() / len(self._bars)
        bar_width = bar_width_for_slot(slot)
        separator = QPen(QColor(palette.surface), 0.8)
        heights = [(bar.total / top) * chart.height() if top else 0.0 for bar in self._bars]
        base_offset = overlay_base_offset(heights)
        for index, bar in enumerate(self._bars):
            x = chart.left() + index * slot + (slot - bar_width) / 2
            cumulative = 0.0
            for segment in bar.segments:
                height = (segment.value / top) * chart.height() if top else 0.0
                if height <= 0:
                    continue
                rect = QRectF(x, chart.bottom() - cumulative - height, bar_width, height)
                painter.setPen(separator)
                painter.setBrush(QColor(segment.color))
                painter.drawRect(rect)
                cumulative += height
            self._draw_overlays(
                painter,
                chart,
                bar,
                x,
                bar_width,
                heights[index],
                base_offset,
                top,
                separator,
            )

    def _draw_overlays(
        self,
        painter: QPainter,
        chart: QRectF,
        bar: StackedBar,
        x: float,
        bar_width: float,
        bar_height: float,
        base_offset: float,
        top: int,
        separator: QPen,
    ) -> None:
        """Накладки внутри основного столбца: общее начало и высота по значению."""
        if not bar.overlays or top <= 0:
            return
        for overlay in bar.overlays:
            value_height = (overlay.value / top) * chart.height()
            geometry = overlay_geometry(bar_height, value_height, base_offset)
            if geometry is None:
                continue
            offset, height = geometry
            rect = QRectF(x, chart.bottom() - offset - height, bar_width, height)
            painter.setPen(separator)
            painter.setBrush(QColor(overlay.color))
            painter.drawRect(rect)

    def _draw_day_labels(self, painter: QPainter, chart: QRectF, metrics: QFontMetrics) -> None:
        """Подписи дней под осью X; при тесноте — через несколько дней."""
        slot = chart.width() / len(self._bars)
        required = metrics.horizontalAdvance("00.00") + X_LABEL_GAP
        step = max(1, math.ceil(required / slot))
        painter.setPen(QColor(active_palette().text_muted))
        for index in range(0, len(self._bars), step):
            x = chart.left() + index * slot
            painter.drawText(
                QRectF(x, chart.bottom() + 2, slot, X_LABEL_HEIGHT - 2),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                self._bars[index].label,
            )

    def _draw_empty(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QColor(active_palette().text_muted))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), EMPTY_TEXT)


def _pack_legend(
    legend: Sequence[tuple[str, str]],
    metrics: QFontMetrics,
    width: float,
) -> list[list[tuple[str, str]]]:
    """Разложить элементы легенды по строкам в пределах ширины."""
    rows: list[list[tuple[str, str]]] = [[]]
    used = 0.0
    for entry in legend:
        text_width = metrics.horizontalAdvance(entry[0])
        entry_width = LEGEND_SWATCH + LEGEND_TEXT_GAP + text_width + LEGEND_ITEM_GAP
        if rows[-1] and used + entry_width > width:
            rows.append([])
            used = 0.0
        rows[-1].append(entry)
        used += entry_width
    return rows
