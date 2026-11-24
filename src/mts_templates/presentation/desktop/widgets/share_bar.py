"""Компактные доли целого: горизонтальные полосы и мини-индикатор доли.

Модуль рисует доли без Qt Charts: полоса из цветных частей с процентами внутри
и маленький индикатор для таблиц. Данные приходят из presentation-слоя, цвета —
из палитры темы или фиксированной палитры операторов.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from mts_templates.presentation.desktop.contrast import readable_text_color
from mts_templates.presentation.desktop.formatting import format_percent
from mts_templates.presentation.desktop.theme import active_palette

ROW_HEIGHT = 30.0
BAR_HEIGHT = 20.0
BAR_RADIUS = 4.0
LABEL_GAP = 10.0
VALUE_GAP = 10.0
LEGEND_HEIGHT = 18.0
LEGEND_SWATCH = 8.0
LEGEND_TEXT_GAP = 5.0
LEGEND_ITEM_GAP = 14.0
MIN_PART_LABEL_WIDTH = 38.0
EMPTY_TEXT = "Нет данных"
METER_WIDTH = 96
METER_HEIGHT = 16
METER_TRACK_WIDTH = 52
METER_TRACK_HEIGHT = 6


@dataclass(frozen=True, slots=True)
class SharePart:
    """Часть целого: подпись, значение и цвет."""

    label: str
    value: float
    color: str


@dataclass(frozen=True, slots=True)
class ShareRow:
    """Строка долей: подпись, итог справа и части целого."""

    label: str
    total_text: str
    parts: tuple[SharePart, ...]


def part_widths(values: Sequence[float], width: float) -> tuple[float, ...]:
    """Ширины частей пропорционально значениям; нули получают ноль."""
    total = sum(max(value, 0.0) for value in values)
    if total <= 0 or width <= 0:
        return tuple(0.0 for _ in values)
    return tuple(max(value, 0.0) / total * width for value in values)


class ShareBarChart(QWidget):
    """Несколько строк стопроцентных полос с общей легендой."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: tuple[ShareRow, ...] = ()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_rows(self, rows: Sequence[ShareRow]) -> None:
        self._rows = tuple(row for row in rows if any(part.value > 0 for part in row.parts))
        self.setMinimumHeight(self._required_height())
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(320, self._required_height())

    def _required_height(self) -> int:
        rows = max(len(self._rows), 1)
        has_legend = bool(self._legend_entries())
        return int(rows * ROW_HEIGHT + (LEGEND_HEIGHT if has_legend else 0) + 4)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        area = QRectF(self.rect().adjusted(0, 4, 0, -4))
        if not self._rows:
            painter.setPen(QColor(active_palette().text_muted))
            painter.drawText(area, int(Qt.AlignmentFlag.AlignCenter), EMPTY_TEXT)
            return

        label_width = self._text_width(painter, [row.label for row in self._rows]) + LABEL_GAP
        value_width = self._text_width(painter, [row.total_text for row in self._rows]) + VALUE_GAP
        track_left = area.left() + label_width
        track_width = max(area.width() - label_width - value_width, 20.0)

        for index, row in enumerate(self._rows):
            self._draw_row(painter, row, area, index, track_left, track_width)

        legend_top = area.y() + len(self._rows) * ROW_HEIGHT
        self._draw_legend(painter, QRectF(area.x(), legend_top, area.width(), LEGEND_HEIGHT))

    def _draw_row(
        self,
        painter: QPainter,
        row: ShareRow,
        area: QRectF,
        index: int,
        track_left: float,
        track_width: float,
    ) -> None:
        palette = active_palette()
        top = area.y() + index * ROW_HEIGHT
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(palette.text_muted))
        painter.drawText(
            QRectF(area.x(), top, track_left - area.x() - LABEL_GAP, ROW_HEIGHT),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            row.label,
        )

        track = QRectF(track_left, top + (ROW_HEIGHT - BAR_HEIGHT) / 2, track_width, BAR_HEIGHT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.surface_alt))
        painter.drawRoundedRect(track, BAR_RADIUS, BAR_RADIUS)

        values = [part.value for part in row.parts]
        total = sum(values)
        widths = part_widths(values, track_width)
        x = track.x()
        for part, width in zip(row.parts, widths, strict=True):
            if width <= 0:
                continue
            rect = QRectF(x, track.y(), width, track.height())
            painter.save()
            painter.setClipRect(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(part.color))
            painter.drawRect(rect)
            painter.restore()

            share = part.value / total if total else 0.0
            if width >= MIN_PART_LABEL_WIDTH:
                label_font = QFont(painter.font())
                label_font.setPointSize(8)
                label_font.setBold(True)
                painter.setFont(label_font)
                painter.setPen(QColor(readable_text_color(part.color)))
                painter.drawText(
                    rect,
                    int(Qt.AlignmentFlag.AlignCenter),
                    format_percent(share),
                )
                painter.setFont(font)
            x += width

        painter.setPen(QColor(palette.border))
        x = track.x()
        for width in widths[:-1]:
            x += width
            painter.drawLine(QPointF(x, track.top()), QPointF(x, track.bottom()))

        painter.setPen(QColor(palette.text))
        painter.drawText(
            QRectF(
                track.right() + VALUE_GAP,
                top,
                area.right() - track.right() - VALUE_GAP,
                ROW_HEIGHT,
            ),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            row.total_text,
        )

    def _draw_legend(self, painter: QPainter, rect: QRectF) -> None:
        entries = self._legend_entries()
        if not entries:
            return
        font = QFont(painter.font())
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        palette = active_palette()
        x = rect.x()
        for label, color in entries:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRect(QRectF(x, rect.y() + 5, LEGEND_SWATCH, LEGEND_SWATCH))
            x += LEGEND_SWATCH + LEGEND_TEXT_GAP
            painter.setPen(QColor(palette.text_muted))
            painter.drawText(
                QRectF(x, rect.y(), metrics.horizontalAdvance(label) + 2, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
            x += metrics.horizontalAdvance(label) + LEGEND_ITEM_GAP

    def _legend_entries(self) -> tuple[tuple[str, str], ...]:
        seen: dict[str, str] = {}
        for row in self._rows:
            for part in row.parts:
                if part.value > 0:
                    seen.setdefault(part.label, part.color)
        return tuple(seen.items())

    def _text_width(self, painter: QPainter, texts: Sequence[str]) -> float:
        font = QFont(painter.font())
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        return float(max((metrics.horizontalAdvance(text) for text in texts), default=0))


class ShareMeter(QWidget):
    """Мини-индикатор доли для таблицы: полоска и процент."""

    def __init__(
        self,
        share: float = 0.0,
        color: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._share = share
        self._color = color
        self.setFixedSize(METER_WIDTH, METER_HEIGHT)

    def set_share(self, share: float, color: str | None = None) -> None:
        self._share = max(0.0, min(share, 1.0))
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        palette = active_palette()

        track = QRectF(
            0, (METER_HEIGHT - METER_TRACK_HEIGHT) / 2, METER_TRACK_WIDTH, METER_TRACK_HEIGHT
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.surface_alt))
        painter.drawRoundedRect(track, 3, 3)
        if self._share > 0 and self._color:
            fill = QRectF(track.x(), track.y(), track.width() * self._share, track.height())
            painter.setBrush(QColor(self._color))
            painter.drawRoundedRect(fill, 3, 3)

        font = QFont(painter.font())
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(active_palette().text_muted))
        painter.drawText(
            QRectF(METER_TRACK_WIDTH + 6, 0, METER_WIDTH - METER_TRACK_WIDTH - 6, METER_HEIGHT),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            format_percent(self._share),
        )
