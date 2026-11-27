"""Мини-дашборд выбранного шаблона или кандидата: дневной график и показатели."""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.presentation.desktop.benefit_style import semantic_text
from mts_templates.presentation.desktop.contrast import readable_text_color
from mts_templates.presentation.desktop.daily_chart import (
    TEMPLATE_MATCHED_LABEL,
    build_segment_daily_chart,
    merge_day_segments,
)
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.theme_catalog import ThemePalette
from mts_templates.presentation.desktop.widgets.stacked_bar_chart import StackedBarChart

CHART_TITLE = "Сегменты по дням"
TITLE_FONT_SIZE = 12
TILE_CAPTION_FONT_SIZE = 11
TILE_VALUE_FONT_SIZE = 17


@dataclass(frozen=True, slots=True)
class DashboardTile:
    """Значение плитки и его семантический тон."""

    value: str
    tone: str = "neutral"


@dataclass(frozen=True, slots=True)
class DashboardDriftFragment:
    """Фрагмент сравнения текста шаблона и кандидата."""

    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class DashboardDrift:
    """Дрейф текста шаблона: что было и что стало в сообщениях."""

    similarity: float
    candidate_text: str
    before: tuple[DashboardDriftFragment, ...]
    after: tuple[DashboardDriftFragment, ...]


@dataclass(frozen=True, slots=True)
class DashboardSeries:
    """Ряд выбранного шаблона или кандидата для мини-дашборда.

    `matched` — сегменты сообщений выбранного объекта по дням.
    `templated_extra` — сегменты, которые нужно добавить к шаблонированному
    трафику при включённом чекбоксе: так моделируется 100 % срабатывание
    кандидата после его регистрации.
    `drift` — пометка о том, что текст сообщений шаблона изменился.
    """

    title: str
    tooltip: str
    matched: tuple[DaySegments, ...]
    tiles: tuple[DashboardTile, ...]
    templated_extra: tuple[DaySegments, ...] = ()
    series_label: str = "шаблон"
    matched_label: str = TEMPLATE_MATCHED_LABEL
    drift: DashboardDrift | None = None


class DriftNotice(QFrame):
    """Пометка о дрейфе текста шаблона с наглядным местом изменения."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardDriftNotice")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drift: DashboardDrift | None = None

        self._title = QLabel(self)
        self._title.setWordWrap(True)
        self._before = QLabel(self)
        self._before.setWordWrap(True)
        self._before.setTextFormat(Qt.TextFormat.RichText)
        self._after = QLabel(self)
        self._after.setWordWrap(True)
        self._after.setTextFormat(Qt.TextFormat.RichText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        layout.addWidget(self._title)
        layout.addWidget(self._before)
        layout.addWidget(self._after)

        self.setVisible(False)
        self.refresh_theme()

    def set_drift(self, drift: DashboardDrift | None) -> None:
        """Показать дрейф или скрыть пометку, если изменений нет."""
        self._drift = drift
        self.setVisible(drift is not None)
        self._render()

    def refresh_theme(self) -> None:
        """Пересобрать цвета пометки под активную тему."""
        palette = active_palette()
        self.setStyleSheet(
            f"QFrame#dashboardDriftNotice {{ background: {palette.surface_alt}; "
            f"border: 1px solid {palette.warning}; border-radius: 8px; }}"
        )
        self._title.setStyleSheet(
            f"color: {semantic_text(palette.warning, palette.surface_alt)}; "
            "font-size: 12px; font-weight: 600;"
        )
        text_color = readable_text_color(palette.surface_alt)
        for label in (self._before, self._after):
            label.setStyleSheet(f"color: {text_color}; font-size: 12px;")
        self._render()

    def _render(self) -> None:
        drift = self._drift
        if drift is None:
            self._title.setText("")
            self._before.setText("")
            self._after.setText("")
            return
        palette = active_palette()
        self._title.setText(f"Текст сообщений изменился · похожесть {drift.similarity * 100:.0f} %")
        self._title.setToolTip(drift.candidate_text)
        self._before.setText("Было: " + _fragments_html(drift.before, palette))
        self._after.setText("Стало: " + _fragments_html(drift.after, palette))


def _fragments_html(fragments: Sequence[DashboardDriftFragment], palette: ThemePalette) -> str:
    """Фрагменты сравнения с подсветкой удалённого и добавленного текста."""
    negative = semantic_text(palette.negative, palette.surface_alt)
    positive = semantic_text(palette.positive, palette.surface_alt)
    parts: list[str] = []
    for fragment in fragments:
        text = html.escape(fragment.text)
        if fragment.kind == "removed":
            parts.append(
                f'<span style="color: {negative}; text-decoration: line-through;">{text}</span>'
            )
        elif fragment.kind == "added":
            parts.append(f'<span style="color: {positive}; font-weight: 600;">{text}</span>')
        else:
            parts.append(text)
    return " ".join(parts)


class MetricTile(QFrame):
    """Плитка показателя: подпись и крупное значение с семантическим цветом."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardMetricTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tone = "neutral"

        self._caption = QLabel(caption, self)
        self._caption.setWordWrap(True)
        self._value = QLabel("—", self)
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)
        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        layout.addStretch(1)

        self.refresh_theme()

    def set_value(self, text: str, *, tone: str = "neutral") -> None:
        """Показать значение; `tone` — `neutral`, `positive` или `negative`."""
        self._tone = tone
        self._value.setText(text)
        self._apply_value_color()

    def reset(self) -> None:
        self.set_value("—")

    def refresh_theme(self) -> None:
        """Пересобрать локальные цвета под активную тему."""
        palette = active_palette()
        self.setStyleSheet(
            f"QFrame#dashboardMetricTile {{ background: {palette.surface_alt}; "
            f"border: 1px solid {palette.border}; border-radius: 8px; }}"
        )
        self._caption.setStyleSheet(
            f"color: {palette.text_muted}; font-size: {TILE_CAPTION_FONT_SIZE}px;"
        )
        self._apply_value_color()

    def _apply_value_color(self) -> None:
        palette = active_palette()
        if self._tone == "positive":
            color = semantic_text(palette.positive, palette.surface_alt)
        elif self._tone == "negative":
            color = semantic_text(palette.negative, palette.surface_alt)
        else:
            color = readable_text_color(palette.surface_alt)
        self._value.setStyleSheet(
            f"color: {color}; font-size: {TILE_VALUE_FONT_SIZE}px; font-weight: 600;"
        )


class SegmentDashboard(QWidget):
    """Статистика выбранного шаблона или кандидата: дневной график и плитки.

    Компонент не знает о таблице и анализе: получает готовые DTO-ряды, подписи
    плиток и их значения. Поэтому он общий для вкладок «Шаблоны» и «Кандидаты».
    """

    def __init__(
        self,
        tile_captions: Sequence[str],
        *,
        empty_title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._series: DashboardSeries | None = None
        self._daily_total: tuple[DaySegments, ...] = ()
        self._daily_templated: tuple[DaySegments, ...] = ()
        self._period_days: tuple[date, date] | None = None

        self._title = QLabel(empty_title, self)
        self._title.setWordWrap(True)
        self._title.setMinimumWidth(0)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self._templated_only = QCheckBox("Только шаблонированные", self)
        self._templated_only.setToolTip(
            "Сопоставлять сегменты с шаблонированным трафиком дня, а не со всем трафиком"
        )
        self._templated_only.toggled.connect(self._refresh_chart)

        self._chart = StackedBarChart(CHART_TITLE, self, compact=True)
        self._chart.setMaximumHeight(210)
        self._drift = DriftNotice(self)

        self._tiles = tuple(MetricTile(caption, self) for caption in tile_captions)
        self._empty_title = empty_title
        self._build()
        self.refresh_theme()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addWidget(self._title, stretch=1)
        header.addWidget(self._templated_only)
        layout.addLayout(header)

        layout.addWidget(self._drift)

        layout.addWidget(self._chart, stretch=1)

        tiles = QGridLayout()
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setHorizontalSpacing(8)
        tiles.setVerticalSpacing(8)
        for index, tile in enumerate(self._tiles):
            tiles.addWidget(tile, index // 2, index % 2)
        for column in range(2):
            tiles.setColumnStretch(column, 1)
        layout.addLayout(tiles)

    def set_context(
        self,
        daily_total: Sequence[DaySegments],
        daily_templated: Sequence[DaySegments],
        period_days: tuple[date, date] | None,
    ) -> None:
        """Задать дневные ряды и границы периода для всех объектов загрузки."""
        self._daily_total = tuple(daily_total)
        self._daily_templated = tuple(daily_templated)
        self._period_days = period_days
        self._refresh_chart()

    def show_series(self, series: DashboardSeries | None) -> None:
        """Показать статистику выбранного объекта; `None` — очистить дашборд."""
        if series is not None and len(series.tiles) != len(self._tiles):
            raise ValueError("Число значений плиток не совпадает с их подписями")
        self._series = series
        self._refresh()

    def clear(self) -> None:
        """Очистить контекст и показатели, например при смене загрузки."""
        self._daily_total = ()
        self._daily_templated = ()
        self._period_days = None
        self._series = None
        self._templated_only.blockSignals(True)
        self._templated_only.setChecked(False)
        self._templated_only.blockSignals(False)
        self._refresh()

    def refresh_theme(self) -> None:
        """Пересчитать цвета заголовка, плиток и графика под активную тему."""
        palette = active_palette()
        self._title.setStyleSheet(
            f"color: {palette.text}; font-size: {TITLE_FONT_SIZE}px; font-weight: 600;"
        )
        for tile in self._tiles:
            tile.refresh_theme()
        self._drift.refresh_theme()
        self._chart.update()

    def _refresh(self) -> None:
        series = self._series
        self._templated_only.setEnabled(series is not None)
        if series is None:
            self._title.setText(self._empty_title)
            self._title.setToolTip("")
            self._drift.set_drift(None)
            for tile in self._tiles:
                tile.reset()
            self._chart.set_data(())
            return

        self._title.setText(series.title)
        self._title.setToolTip(series.tooltip)
        self._drift.set_drift(series.drift)
        for tile, value in zip(self._tiles, series.tiles, strict=True):
            tile.set_value(value.value, tone=value.tone)
        self._refresh_chart()

    def _refresh_chart(self) -> None:
        series = self._series
        if series is None or self._period_days is None:
            self._chart.set_data(())
            return
        templated_only = self._templated_only.isChecked()
        totals = (
            merge_day_segments(self._daily_templated, series.templated_extra)
            if templated_only
            else self._daily_total
        )
        start, end = self._period_days
        data = build_segment_daily_chart(
            totals,
            series.matched,
            period_start=start,
            period_end=end,
            templated_only=templated_only,
            series_label=series.series_label,
            matched_label=series.matched_label,
        )
        self._chart.set_data(data.bars, legend=data.legend, caption=data.caption)
