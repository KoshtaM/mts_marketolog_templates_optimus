"""Данные составной диаграммы сегментов по дням и операторам. Без Qt."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from mts_templates.application.dto import DailySegments
from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.presentation.desktop.formatting import format_int
from mts_templates.presentation.desktop.operator_colors import operator_color

DAY_LABEL_FORMAT = "%d.%m"
TICK_COUNT = 4
NICE_MULTIPLIERS = (1.0, 2.0, 2.5, 5.0, 10.0)
TEMPLATE_MATCHED_COLOR = "#ff8c00"
TEMPLATE_OTHER_COLOR = "#0d9488"
TEMPLATE_MATCHED_LABEL = "Соответствуют шаблону"
TEMPLATE_OTHER_LABEL = "Остальной трафик"
TEMPLATE_OTHER_TEMPLATED_LABEL = "Остальной шаблонированный трафик"


@dataclass(frozen=True, slots=True)
class StackedSegment:
    """Часть столбца: значение и цвет оператора."""

    label: str
    value: float
    color: str


@dataclass(frozen=True, slots=True)
class BarOverlay:
    """Часть, рисуемая поверх основного столбца.

    Вертикальное положение накладки задаёт диаграмма: все накладки начинаются
    на одной высоте, поэтому в данных хранятся только значение и цвет.
    """

    label: str
    value: float
    color: str


@dataclass(frozen=True, slots=True)
class StackedBar:
    """Столбец дня: сегменты снизу вверх, первый — самый массовый."""

    label: str
    segments: tuple[StackedSegment, ...]
    overlays: tuple[BarOverlay, ...] = ()

    @property
    def total(self) -> float:
        """Высота основного столбца; накладки внутрь не входят."""
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


def build_template_daily_chart(
    totals: Sequence[DaySegments],
    matched: Sequence[DaySegments],
    *,
    period_start: date,
    period_end: date,
    templated_only: bool = False,
) -> DailyChartData:
    """Столбцы дней выбранного шаблона: основной трафик и совпавшие сегменты.

    `totals` — базовый ряд: весь трафик дня или только шаблонированные SMS.
    Основной столбец (teal) показывает базовый объём целиком, совпавшие сегменты
    (dark orange) рисуются поверх него на общей высоте от основания. Дни без
    данных заполняются нулями, чтобы ось X покрывала период целиком.
    """
    total_by_day = {item.day: item.segments for item in totals}
    matched_by_day = {item.day: item.segments for item in matched}
    other_label = TEMPLATE_OTHER_TEMPLATED_LABEL if templated_only else TEMPLATE_OTHER_LABEL
    bars: list[StackedBar] = []
    matched_total = 0
    overall = 0
    for day in _period_days(total_by_day, matched_by_day, period_start, period_end):
        day_total = total_by_day.get(day, 0)
        day_matched = min(matched_by_day.get(day, 0), day_total)
        matched_total += day_matched
        overall += day_total
        parts: list[StackedSegment] = []
        if day_total:
            parts.append(StackedSegment(other_label, float(day_total), TEMPLATE_OTHER_COLOR))
        overlays: list[BarOverlay] = []
        if day_matched:
            overlays.append(
                BarOverlay(
                    TEMPLATE_MATCHED_LABEL,
                    float(day_matched),
                    TEMPLATE_MATCHED_COLOR,
                )
            )
        bars.append(
            StackedBar(
                label=day.strftime(DAY_LABEL_FORMAT),
                segments=tuple(parts),
                overlays=tuple(overlays),
            )
        )

    legend = (
        (TEMPLATE_MATCHED_LABEL, TEMPLATE_MATCHED_COLOR),
        (other_label, TEMPLATE_OTHER_COLOR),
    )
    if not overall:
        caption = ""
    elif templated_only:
        caption = (
            f"шаблон: {format_int(matched_total)} из {format_int(overall)} "
            "шаблонированных сегментов"
        )
    else:
        caption = f"шаблон: {format_int(matched_total)} из {format_int(overall)} сегментов"
    return DailyChartData(bars=tuple(bars), legend=legend, caption=caption)


def _period_days(
    total_by_day: dict[date, int],
    matched_by_day: dict[date, int],
    start: date,
    end: date,
) -> tuple[date, ...]:
    """Все дни периода; при некорректных границах — только дни с данными."""
    if end < start:
        return tuple(sorted(set(total_by_day) | set(matched_by_day)))
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


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
