"""Мини-дашборд выбранного шаблона: дневной график и ключевые показатели."""

from __future__ import annotations

from collections.abc import Sequence
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

from mts_templates.application.dto import TemplateMetricsView
from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.presentation.desktop.benefit_style import semantic_text
from mts_templates.presentation.desktop.contrast import readable_text_color
from mts_templates.presentation.desktop.daily_chart import build_template_daily_chart
from mts_templates.presentation.desktop.formatting import format_money, format_percent
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.stacked_bar_chart import StackedBarChart

CHART_TITLE = "Сегменты по дням"
EMPTY_TITLE = "Шаблон не выбран"
TITLE_FONT_SIZE = 12
TILE_CAPTION_FONT_SIZE = 11
TILE_VALUE_FONT_SIZE = 17


class MetricTile(QFrame):
    """Плитка показателя: подпись и крупное значение с семантическим цветом."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("templateMetricTile")
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
            f"QFrame#templateMetricTile {{ background: {palette.surface_alt}; "
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


class TemplateDashboard(QWidget):
    """Статистика выбранного шаблона: дневной график и ключевые показатели.

    Компонент не знает о таблице и анализе: получает DTO метрики, дневные ряды и
    границы периода через `set_context`/`show_template`, поэтому его можно
    использовать на любом экране.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metric: TemplateMetricsView | None = None
        self._daily_total: tuple[DaySegments, ...] = ()
        self._daily_templated: tuple[DaySegments, ...] = ()
        self._period_days: tuple[date, date] | None = None

        self._title = QLabel(EMPTY_TITLE, self)
        self._title.setWordWrap(True)
        self._title.setMinimumWidth(0)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self._templated_only = QCheckBox("Только шаблонированные", self)
        self._templated_only.setToolTip(
            "Сопоставлять сегменты шаблона с шаблонированным трафиком дня, а не со всем трафиком"
        )
        self._templated_only.toggled.connect(self._refresh_chart)

        self._chart = StackedBarChart(CHART_TITLE, self, compact=True)
        self._chart.setMaximumHeight(210)

        self._all_share = MetricTile("% от всех сегментов", self)
        self._templated_share = MetricTile("% от шаблонированных", self)
        self._benefit = MetricTile("Выгода/мес", self)
        self._trigger = MetricTile("Срабатывание", self)
        self._tiles = (self._all_share, self._templated_share, self._benefit, self._trigger)

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

        layout.addWidget(self._chart, stretch=1)

        tiles = QGridLayout()
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setHorizontalSpacing(8)
        tiles.setVerticalSpacing(8)
        tiles.addWidget(self._all_share, 0, 0)
        tiles.addWidget(self._templated_share, 0, 1)
        tiles.addWidget(self._benefit, 1, 0)
        tiles.addWidget(self._trigger, 1, 1)
        tiles.setColumnStretch(0, 1)
        tiles.setColumnStretch(1, 1)
        layout.addLayout(tiles)

    def set_context(
        self,
        daily_total: Sequence[DaySegments],
        daily_templated: Sequence[DaySegments],
        period_days: tuple[date, date] | None,
    ) -> None:
        """Задать дневные ряды и границы периода для всех шаблонов загрузки."""
        self._daily_total = tuple(daily_total)
        self._daily_templated = tuple(daily_templated)
        self._period_days = period_days
        self._refresh_chart()

    def show_template(self, metric: TemplateMetricsView | None) -> None:
        """Показать статистику шаблона; `None` — очистить мини-дашборд."""
        self._metric = metric
        self._refresh()

    def clear(self) -> None:
        """Очистить контекст и показатели, например при смене загрузки."""
        self._daily_total = ()
        self._daily_templated = ()
        self._period_days = None
        self._metric = None
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
        self._chart.update()

    def _refresh(self) -> None:
        metric = self._metric
        self._templated_only.setEnabled(metric is not None)
        if metric is None:
            self._title.setText(EMPTY_TITLE)
            self._title.setToolTip("")
            for tile in self._tiles:
                tile.reset()
            self._chart.set_data(())
            return

        self._title.setText(f"{metric.name} · ID {metric.template_id}")
        self._title.setToolTip(metric.text)
        self._all_share.set_value(format_percent(metric.share_of_all_segments))
        self._templated_share.set_value(format_percent(metric.share_of_templated_segments))
        benefit = metric.monthly_net_benefit
        tone = "positive" if benefit.amount > 0 else "negative" if benefit.amount < 0 else "neutral"
        self._benefit.set_value(format_money(benefit), tone=tone)
        self._trigger.set_value(format_percent(metric.trigger_rate))
        self._refresh_chart()

    def _refresh_chart(self) -> None:
        metric = self._metric
        if metric is None or self._period_days is None:
            self._chart.set_data(())
            return
        templated_only = self._templated_only.isChecked()
        totals = self._daily_templated if templated_only else self._daily_total
        start, end = self._period_days
        data = build_template_daily_chart(
            totals,
            metric.daily_segments,
            period_start=start,
            period_end=end,
            templated_only=templated_only,
        )
        self._chart.set_data(data.bars, legend=data.legend, caption=data.caption)
