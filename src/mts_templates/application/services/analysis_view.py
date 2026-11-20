"""Сборка DTO представления из доменного прогона анализа."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from mts_templates.application.dto import (
    AnalysisView,
    CandidateView,
    OperatorTriggerView,
    TemplateMetricsView,
)
from mts_templates.domain.analytics.analysis import (
    PARTIAL_PERIOD_DAYS,
    AnalysisRun,
    monthly_factor,
    monthly_net_benefit,
)
from mts_templates.domain.entities import SmsTemplate


def _scale(value: int, factor: Decimal) -> int:
    """Масштабировать целый объём до месяца с округлением половины вверх."""
    return int((Decimal(value) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_analysis_view(run: AnalysisRun, templates: Sequence[SmsTemplate]) -> AnalysisView:
    """Дополнить метрики реквизитами шаблонов для UI и отчёта."""
    by_id = {template.template_id: template for template in templates}
    factor = monthly_factor(run.period)
    metrics = tuple(
        TemplateMetricsView(
            template_id=item.template_id,
            name=by_id[item.template_id].name if item.template_id in by_id else item.template_id,
            sender=by_id[item.template_id].sender if item.template_id in by_id else "",
            text=by_id[item.template_id].text if item.template_id in by_id else "",
            operators=tuple(
                sorted(operator.value for operator in by_id[item.template_id].operators)
            )
            if item.template_id in by_id
            else (),
            active=item.active,
            matched_messages=item.matched_messages,
            matched_segments=item.matched_segments,
            delivered_messages=item.delivered_messages,
            unique_recipients=item.unique_recipients,
            triggered_messages=item.triggered_messages,
            off_operator_messages=item.off_operator_messages,
            actual_cost=item.actual_cost,
            baseline_cost=item.baseline_cost,
            template_fee=item.template_fee,
            net_benefit=item.net_benefit,
            trigger_rate=float(item.trigger_rate),
            monthly_messages=_scale(item.matched_messages, factor),
            monthly_segments=_scale(item.matched_segments, factor),
            monthly_actual_cost=item.actual_cost * factor,
            monthly_baseline_cost=item.baseline_cost * factor,
            monthly_net_benefit=monthly_net_benefit(item, factor),
        )
        for item in run.metrics
    )
    candidates = tuple(
        CandidateView(
            candidate_id=candidate.candidate_id,
            template_text=candidate.template_text,
            messages=candidate.messages,
            segments=candidate.segments,
            actual_cost=candidate.actual_cost,
            templated_cost=candidate.templated_cost,
            monthly_messages=_scale(candidate.messages, factor),
            monthly_segments=_scale(candidate.segments, factor),
            monthly_actual_cost=candidate.actual_cost * factor,
            monthly_templated_cost=candidate.templated_cost * factor,
            monthly_saving=candidate.monthly_saving,
            template_fee=candidate.template_fee,
            net_monthly=candidate.net_monthly,
            payback_months=float(candidate.payback_months)
            if candidate.payback_months is not None
            else None,
            confidence=float(candidate.confidence),
            coverage=float(candidate.coverage),
            senders=candidate.senders,
            operators=tuple(operator.value for operator in candidate.operators),
            period_from=candidate.period.start,
            period_to=candidate.period.end,
            is_partial_period=candidate.is_partial_period,
            examples=candidate.examples,
            status=candidate.status,
            warnings=candidate.warnings,
            foreign_matches=candidate.foreign_matches,
        )
        for candidate in run.candidates
    )
    operator_triggers = _operator_trigger_views(run, by_id)
    return AnalysisView(
        run_id=run.run_id,
        batch_id=run.batch_id,
        created_at=run.created_at,
        period_from=run.period.start,
        period_to=run.period.end,
        message_count=run.message_count,
        matched_message_count=run.matched_message_count,
        triggered_message_count=run.triggered_message_count,
        total_net_benefit=run.total_net_benefit,
        inactive_templates=run.inactive_templates,
        trigger_rate=float(run.trigger_rate),
        metrics=metrics,
        candidates=candidates,
        warnings=run.warnings,
        operator_triggers=operator_triggers,
        is_partial_period=run.period.days < PARTIAL_PERIOD_DAYS,
    )


def _operator_trigger_views(
    run: AnalysisRun, by_id: dict[str, SmsTemplate]
) -> tuple[OperatorTriggerView, ...]:
    """Разбивка по операторам с долей подпавших сегментов внутри шаблона."""
    segments_by_template: dict[str, int] = {}
    for item in run.operator_triggers:
        segments_by_template[item.template_id] = (
            segments_by_template.get(item.template_id, 0) + item.matched_segments
        )

    views: list[OperatorTriggerView] = []
    for item in run.operator_triggers:
        total_segments = segments_by_template.get(item.template_id, 0)
        template = by_id.get(item.template_id)
        views.append(
            OperatorTriggerView(
                template_id=item.template_id,
                template_name=template.name if template is not None else "",
                sender=template.sender if template is not None else "",
                operator=item.operator.value,
                listed=item.listed,
                matched_messages=item.matched_messages,
                triggered_messages=item.triggered_messages,
                matched_segments=item.matched_segments,
                share=item.matched_segments / total_segments if total_segments else 0.0,
            )
        )
    return tuple(views)
