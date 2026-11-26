"""Агрегат прогона анализа: метрики шаблонов и кандидаты."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from mts_templates.domain.analytics.activity import (
    DaySegments,
    OperatorTrigger,
    TemplateMetrics,
    ensure_unique_days,
)
from mts_templates.domain.value_objects import Money, Operator, Period

DAYS_IN_MONTH = Decimal("30")
PARTIAL_PERIOD_DAYS = 28


def monthly_factor(period: Period) -> Decimal:
    """Коэффициент моделирования месячной выгоды.

    Полный период (не меньше 28 дней) не масштабируется: выгода за месяц равна
    фактической. Неполный период растягивается до 30 дней, чтобы прогноз
    кандидата был сопоставим с ежемесячной стоимостью шаблона.
    """
    if period.days >= PARTIAL_PERIOD_DAYS:
        return Decimal(1)
    return DAYS_IN_MONTH / Decimal(period.days)


def monthly_net_benefit(metrics: TemplateMetrics, factor: Decimal) -> Money:
    """Месячная выгода шаблона: модель месяца минус ежемесячная стоимость шаблона."""
    return (metrics.baseline_cost - metrics.actual_cost) * factor - metrics.template_fee


@dataclass(frozen=True, slots=True)
class CandidateGroup:
    """Группа однотипных незашаблонированных сообщений.

    `actual_cost` — фактически заплачено за период,
    `templated_cost` — оценка тех же сегментов по средней ставке шаблонированных SMS.
    """

    candidate_id: str
    template_text: str
    messages: int
    segments: int
    actual_cost: Money
    templated_cost: Money
    monthly_saving: Money
    template_fee: Money
    net_monthly: Money
    payback_months: Decimal | None
    confidence: Decimal
    coverage: Decimal
    senders: tuple[str, ...]
    operators: tuple[Operator, ...]
    period: Period
    is_partial_period: bool
    examples: tuple[str, ...] = ()
    status: str = "auto_validated"
    warnings: tuple[str, ...] = ()
    foreign_matches: int = 0
    daily_segments: tuple[DaySegments, ...] = ()

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id обязателен")
        if not self.template_text.strip():
            raise ValueError("Текст шаблона-кандидата не может быть пустым")
        if self.messages < 0 or self.segments < 0:
            raise ValueError("Объёмы кандидата не могут быть отрицательными")
        if self.foreign_matches < 0:
            raise ValueError("Число чужих совпадений не может быть отрицательным")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence должен быть в диапазоне 0..1")
        if not Decimal("0") <= self.coverage <= Decimal("1"):
            raise ValueError("coverage должен быть в диапазоне 0..1")
        ensure_unique_days(self.daily_segments)
        daily_total = sum(item.segments for item in self.daily_segments)
        if daily_total != self.segments:
            raise ValueError("Дневные сегменты кандидата должны совпадать с его объёмом")


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    """Результат прогона анализа по загрузке и конфигурации."""

    run_id: str
    batch_id: str
    config_hash: str
    created_at: datetime
    period: Period
    message_count: int
    matched_message_count: int
    metrics: tuple[TemplateMetrics, ...]
    candidates: tuple[CandidateGroup, ...]
    warnings: tuple[str, ...] = ()
    operator_triggers: tuple[OperatorTrigger, ...] = ()
    daily_segments: tuple[DaySegments, ...] = ()
    daily_templated_segments: tuple[DaySegments, ...] = ()
    # Наблюдаемые ставки периода: по ним центр действий оценивает потери.
    observed_ordinary_rate: Money | None = None
    observed_templated_rate: Money | None = None
    # Сообщения, оплаченные как шаблонированные, но не сопоставленные шаблону.
    unmatched_templated_messages: int = 0
    unmatched_templated_segments: int = 0
    unmatched_templated_cost: Money = field(default_factory=Money.zero)

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id обязателен")
        if not self.config_hash:
            raise ValueError("config_hash обязателен")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at должен быть timezone-aware")
        if self.message_count < 0 or self.matched_message_count < 0:
            raise ValueError("Счётчики сообщений не могут быть отрицательными")
        if self.matched_message_count > self.message_count:
            raise ValueError("Сопоставленных сообщений больше, чем всего")
        if self.unmatched_templated_messages < 0 or self.unmatched_templated_segments < 0:
            raise ValueError("Счётчики шаблонированных без шаблона не могут быть отрицательными")
        ensure_unique_days(self.daily_segments)
        ensure_unique_days(self.daily_templated_segments)
        template_ids = [metrics.template_id for metrics in self.metrics]
        if len(template_ids) != len(set(template_ids)):
            raise ValueError("Метрики должны быть уникальны по template_id")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Кандидаты должны быть уникальны по candidate_id")
        totals = {item.day: item.segments for item in self.daily_segments}
        templated_totals = {item.day: item.segments for item in self.daily_templated_segments}
        for day, segments in templated_totals.items():
            if segments > totals.get(day, 0):
                raise ValueError("Шаблонированных сегментов дня больше, чем всего трафика дня")
        for metrics in self.metrics:
            for item in metrics.daily_segments:
                if item.segments > totals.get(item.day, 0):
                    raise ValueError("Сегменты шаблона по дням не могут превышать трафик дня")

    @property
    def total_net_benefit(self) -> Money:
        return sum((metrics.net_benefit for metrics in self.metrics), Money.zero())

    @property
    def inactive_templates(self) -> int:
        return sum(1 for metrics in self.metrics if not metrics.active)

    @property
    def triggered_message_count(self) -> int:
        return sum(metrics.triggered_messages for metrics in self.metrics)

    @property
    def trigger_rate(self) -> Decimal:
        """Срабатывание по всем шаблонам: тарифицированные как шаблонные / подпавшие под шаблон."""
        if self.matched_message_count == 0:
            return Decimal("0")
        return Decimal(self.triggered_message_count) / Decimal(self.matched_message_count)
