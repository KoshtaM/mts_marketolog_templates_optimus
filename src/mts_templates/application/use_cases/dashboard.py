"""Use case: сводка для дашборда."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from mts_templates.application.dto import DailySegments, DashboardSummary, ImportBatch
from mts_templates.application.ports import (
    AnalysisRepository,
    ImportRepository,
    MessageQueryRepository,
    TemplateRepository,
)
from mts_templates.domain.analytics.analysis import monthly_factor, monthly_net_benefit
from mts_templates.domain.value_objects import Money


class ListBatches:
    """Лёгкий список загрузок для выпадающих списков."""

    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    def execute(self) -> tuple[ImportBatch, ...]:
        return self._imports.list_batches()


class GetDashboardSummary:
    """Собирает сводку по выбранной загрузке без загрузки всех сообщений."""

    def __init__(
        self,
        imports: ImportRepository,
        messages: MessageQueryRepository,
        templates: TemplateRepository,
        analysis: AnalysisRepository,
    ) -> None:
        self._imports = imports
        self._messages = messages
        self._templates = templates
        self._analysis = analysis

    def execute(self, batch_id: str | None = None) -> DashboardSummary:
        batches = self._imports.list_batches()
        batch = _select(batches, batch_id)
        template_count = self._templates.count()
        active_templates = self._templates.count_active()

        if batch is None:
            return DashboardSummary(
                batches=batches,
                batch=None,
                statistics=None,
                template_count=template_count,
                active_templates=active_templates,
                inactive_templates=template_count - active_templates,
                candidates=0,
                total_net_benefit=None,
                warnings=("Статистика ещё не импортирована.",),
            )

        statistics = self._messages.statistics(batch.id)
        operators = self._messages.operator_statistics(batch.id)
        segmentation = self._messages.segmentation_statistics(batch.id)
        daily_segments = fill_period_days(
            self._messages.daily_segments(batch.id),
            batch.period_from.date() if batch.period_from else None,
            batch.period_to.date() if batch.period_to else None,
        )
        latest = self._analysis.latest(batch.id)
        warnings = list(batch.warnings)
        if latest is not None:
            warnings.extend(latest.warnings)

        profitable = (
            positive_benefit(item.net_monthly for item in latest.candidates) if latest else None
        )
        profitable_candidates = (
            profitable_candidates_count(item.net_monthly for item in latest.candidates)
            if latest
            else 0
        )
        factor = monthly_factor(latest.period) if latest else None
        losses = (
            negative_benefit(monthly_net_benefit(item, factor) for item in latest.metrics)
            if latest and factor is not None
            else None
        )

        return DashboardSummary(
            batches=batches,
            batch=batch,
            statistics=statistics,
            template_count=template_count,
            active_templates=active_templates,
            inactive_templates=template_count - active_templates,
            candidates=len(latest.candidates) if latest else 0,
            total_net_benefit=latest.total_net_benefit if latest else None,
            profitable_candidates=profitable_candidates,
            profitable_candidates_benefit=profitable,
            loss_templates_benefit=losses,
            potential_benefit=(profitable - losses)
            if profitable is not None and losses is not None
            else None,
            warnings=tuple(dict.fromkeys(warnings)),
            operators=operators,
            segmentation=segmentation,
            daily_segments=daily_segments,
        )


def positive_benefit(values: Iterable[Money]) -> Money:
    """Сумма только положительных значений: потенциальная выгода внедрения."""
    total = Money.zero()
    for value in values:
        if value.amount > 0:
            total = total + value
    return total


def negative_benefit(values: Iterable[Money]) -> Money:
    """Сумма только отрицательных значений: убыток убыточных шаблонов."""
    total = Money.zero()
    for value in values:
        if value.amount < 0:
            total = total + value
    return total


def profitable_candidates_count(values: Iterable[Money]) -> int:
    """Сколько кандидатов выгодно: количество положительных значений."""
    return sum(1 for value in values if value.amount > 0)


def fill_period_days(
    daily: Sequence[DailySegments],
    start: date | None,
    end: date | None,
) -> tuple[DailySegments, ...]:
    """Дополнить дни без отправок, чтобы ось X покрывала весь период.

    Без границ периода возвращаются только дни с данными.
    """
    if start is None or end is None or end < start:
        return tuple(daily)
    by_day = {item.day: item for item in daily}
    days = (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    return tuple(by_day.get(day, DailySegments(day=day)) for day in days)


def _select(batches: Sequence[ImportBatch], batch_id: str | None) -> ImportBatch | None:
    if not batches:
        return None
    if batch_id is None:
        return batches[0]
    return next((batch for batch in batches if batch.id == batch_id), batches[0])
