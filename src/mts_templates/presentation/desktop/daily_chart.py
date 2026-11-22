"""Данные составной диаграммы сегментов по дням и операторам. Без Qt."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from mts_templates.application.dto import DailySegments
from mts_templates.presentation.desktop.formatting import format_int
from mts_templates.presentation.desktop.operator_colors import operator_color

DAY_LABEL_FORMAT = "%d.%m"
TICK_COUNT = 4
NICE_MULTIPLIERS = (1.0, 2.0, 2.5, 5.0, 10.0)


@dataclass(frozen=True, slots=True)
class StackedSegment:
    """Часть столбца: значение и цвет оператора."""

    label: str
    value: float
    color: str


@dataclass(frozen=True, slots=True)
class StackedBar:
    """Столбец дня: сегменты снизу вверх, первый — самый массовый."""

    label: str
    segments: tuple[StackedSegment, ...]

    @property
    def total(self) -> float:
        return sum(item.value for item in self.segments)


@dataclass(frozen=True, slots=True)
class DailyChartData:
    """Столбцы, легенда и подпись диаграммы по дням."""

    bars: tuple[StackedBar, ...] = ()
    legend: tuple[tuple[str, str], ...] = ()
    caption: str = ""


def build_daily_chart(daily: Sequence[DailySegments]) -> DailyChartData:
    """Собрать столбцы дней и легенду по суммарной массовости оператора.

    Порядок частей внутри дня сохраняется из DTO: SQL уже отсортировал
    операторов по убыванию сегментов за этот день.
    """
    totals: dict[str, int] = {}
    bars: list[StackedBar] = []
    overall = 0
    for item in daily:
        segments: list[StackedSegment] = []
        for part in item.operators:
            totals[part.operator] = totals.get(part.operator, 0) + part.segments
            overall += part.segments
            segments.append(
                StackedSegment(
                    label=part.operator,
                    value=float(part.segments),
                    color=operator_color(part.operator),
                )
            )
        bars.append(StackedBar(label=item.day.strftime(DAY_LABEL_FORMAT), segments=tuple(segments)))

    legend = tuple(
        (operator, operator_color(operator))
        for operator, _ in sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))
    )
    caption = f"всего {format_int(overall)} сегментов" if overall else ""
    return DailyChartData(bars=tuple(bars), legend=legend, caption=caption)


def nice_scale(max_value: int, ticks: int = TICK_COUNT) -> tuple[int, int]:
    """Шаг сетки и верхняя граница оси Y: ровные числа не меньше `max_value`."""
    if max_value <= 0:
        return 1, 0
    rough = max_value / ticks
    magnitude = 1
    while magnitude * 10 <= rough:
        magnitude *= 10
    step = 1
    for multiplier in NICE_MULTIPLIERS:
        candidate = magnitude * multiplier
        if candidate >= rough:
            step = max(1, math.ceil(candidate))
            break
    top = math.ceil(max_value / step) * step
    return step, top
