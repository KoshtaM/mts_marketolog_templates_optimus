"""История шаблонов: тренд по загрузкам и сигнал деградации."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from mts_templates.domain.analytics.analysis import AnalysisRun, monthly_factor, monthly_net_benefit
from mts_templates.domain.value_objects import Money, Period


@dataclass(frozen=True, slots=True)
class TemplateTrendPoint:
    """Значение тренда шаблона в одном прогоне — одной загрузке."""

    template_id: str
    batch_id: str
    period: Period
    segments: int
    triggered_messages: int
    trigger_rate: Decimal
    net_benefit: Money

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("template_id обязателен")
        if self.segments < 0 or self.triggered_messages < 0:
            raise ValueError("Счётчики тренда не могут быть отрицательными")


@dataclass(frozen=True, slots=True)
class TemplateTrend:
    """Тренд шаблона по прогонам анализа, отсортированным по периоду."""

    template_id: str
    points: tuple[TemplateTrendPoint, ...]


@dataclass(frozen=True, slots=True)
class Deterioration:
    """Сигнал деградации: ранее шаблон срабатывал, в последнем прогоне — нет."""

    template_id: str
    previous_triggered_messages: int
    current_triggered_messages: int
    previous_trigger_rate: Decimal
    current_trigger_rate: Decimal


def build_template_trend(runs: Sequence[AnalysisRun], template_id: str) -> TemplateTrend:
    """Собрать тренд по прогонам анализа, отсортированным по периоду загрузки."""
    runs_for_template = sorted(
        (run for run in runs if any(metric.template_id == template_id for metric in run.metrics)),
        key=lambda run: run.period.start,
    )
    points = tuple(
        TemplateTrendPoint(
            template_id=template_id,
            batch_id=run.batch_id,
            period=run.period,
            segments=metric.matched_segments,
            triggered_messages=metric.triggered_messages,
            trigger_rate=metric.trigger_rate,
            net_benefit=monthly_net_benefit(metric, monthly_factor(run.period)),
        )
        for run in runs_for_template
        for metric in run.metrics
        if metric.template_id == template_id
    )
    return TemplateTrend(template_id=template_id, points=points)


def detect_deterioration(trend: TemplateTrend) -> Deterioration | None:
    """Деградация: ранее шаблон срабатывал, в последнем прогоне — нулевое срабатывание."""
    points = trend.points
    if len(points) < 2:
        return None
    previous, current = points[-2], points[-1]
    if current.triggered_messages > 0 or previous.triggered_messages == 0:
        return None
    return Deterioration(
        template_id=trend.template_id,
        previous_triggered_messages=previous.triggered_messages,
        current_triggered_messages=current.triggered_messages,
        previous_trigger_rate=previous.trigger_rate,
        current_trigger_rate=current.trigger_rate,
    )
