"""Преобразование DTO приложения в JSON-структуры для веб-интерфейса.

Деньги отдаются строками с двумя знаками после запятой: JavaScript получает
точное десятичное представление и форматирует сумму только на выводе.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from mts_templates.application.dto import (
    ActionCenterView,
    ActionItemView,
    AnalysisView,
    BatchStatistics,
    CandidateView,
    DailySegments,
    DashboardSummary,
    ImportBatch,
    ImportReport,
    OperatorStatistics,
    OperatorTriggerView,
    SegmentationStatistics,
    TemplateFilePreview,
    TemplateImportReport,
    TemplateMetricsView,
)
from mts_templates.application.settings import AppSettings
from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.domain.analytics.import_aggregation import QualityIssue
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.theme_catalog import Theme


def money(value: Money | None) -> str | None:
    """Денежная сумма в виде строки; `None` остаётся `None`."""
    return None if value is None else str(value)


def moment(value: datetime | None) -> str | None:
    """Момент времени в ISO 8601 с часовым поясом."""
    return None if value is None else value.isoformat()


def day(value: date) -> str:
    return value.isoformat()


def day_segments_to_dict(item: DaySegments) -> dict[str, Any]:
    """Активность шаблона или кандидата: только день и сегменты."""
    return {"day": day(item.day), "segments": item.segments}


def daily_segments_to_dict(item: DailySegments) -> dict[str, Any]:
    """Трафик дня с разбивкой по операторам."""
    return {
        "day": day(item.day),
        "segments": item.segments,
        "operators": [
            {"operator": operator.operator, "segments": operator.segments}
            for operator in item.operators
        ],
    }


def batch_to_dict(batch: ImportBatch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "source_path": batch.source_path,
        "source_name": Path(batch.source_path).name,
        "source_sha256": batch.source_sha256,
        "kind": batch.kind,
        "imported_at": moment(batch.imported_at),
        "row_count": batch.row_count,
        "message_count": batch.message_count,
        "total_cost": money(batch.total_cost),
        "period_from": moment(batch.period_from),
        "period_to": moment(batch.period_to),
        "status": batch.status,
        "warnings": list(batch.warnings),
        "segment_count": batch.segment_count,
        "duplicate_message_ids": batch.duplicate_message_ids,
        "delivered_rows": batch.delivered_rows,
        "partial_delivered_rows": batch.partial_delivered_rows,
        "send_error_rows": batch.send_error_rows,
        "delivery_error_rows": batch.delivery_error_rows,
        "empty_package_rows": batch.empty_package_rows,
    }


def issue_to_dict(issue: QualityIssue) -> dict[str, Any]:
    return {
        "message_id": issue.message_id,
        "field": issue.field,
        "detail": issue.detail,
    }


def import_report_to_dict(report: ImportReport) -> dict[str, Any]:
    return {
        "batch": batch_to_dict(report.batch),
        "reused": report.reused,
        "duplicate_message_ids": report.duplicate_message_ids,
        "segment_count": report.segment_count,
        "delivered_rows": report.delivered_rows,
        "partial_delivered_rows": report.partial_delivered_rows,
        "send_error_rows": report.send_error_rows,
        "delivery_error_rows": report.delivery_error_rows,
        "empty_package_rows": report.empty_package_rows,
        "issues": [issue_to_dict(issue) for issue in report.issues],
        "has_issues": report.has_issues,
    }


def template_preview_to_dict(preview: TemplateFilePreview) -> dict[str, Any]:
    suggested = (
        {key: value for key, value in asdict(preview.suggested).items() if value is not None}
        if preview.suggested is not None
        else None
    )
    return {
        "source_name": preview.path.name,
        "columns": list(preview.columns),
        "sample_rows": list(preview.sample_rows),
        "suggested": suggested,
    }


def template_import_report_to_dict(report: TemplateImportReport) -> dict[str, Any]:
    return {
        "imported": report.imported,
        "updated": report.updated,
        "duplicates": report.duplicates,
        "skipped_empty": report.skipped_empty,
        "removed": report.removed,
        "warnings": list(report.warnings),
    }


def template_to_dict(template: SmsTemplate) -> dict[str, Any]:
    return {
        "template_id": template.template_id,
        "name": template.name,
        "text": template.text,
        "sender": template.sender,
        "active": template.active,
        "monthly_fee": money(template.monthly_fee),
        "operators": sorted(operator.value for operator in template.operators),
        "traffic_type": template.traffic_type,
        "example": template.example,
    }


def metrics_to_dict(metrics: TemplateMetricsView) -> dict[str, Any]:
    return {
        "template_id": metrics.template_id,
        "name": metrics.name,
        "sender": metrics.sender,
        "text": metrics.text,
        "operators": list(metrics.operators),
        "active": metrics.active,
        "matched_messages": metrics.matched_messages,
        "matched_segments": metrics.matched_segments,
        "delivered_messages": metrics.delivered_messages,
        "unique_recipients": metrics.unique_recipients,
        "triggered_messages": metrics.triggered_messages,
        "off_operator_messages": metrics.off_operator_messages,
        "actual_cost": money(metrics.actual_cost),
        "baseline_cost": money(metrics.baseline_cost),
        "template_fee": money(metrics.template_fee),
        "net_benefit": money(metrics.net_benefit),
        "trigger_rate": metrics.trigger_rate,
        "monthly_messages": metrics.monthly_messages,
        "monthly_segments": metrics.monthly_segments,
        "monthly_actual_cost": money(metrics.monthly_actual_cost),
        "monthly_baseline_cost": money(metrics.monthly_baseline_cost),
        "monthly_net_benefit": money(metrics.monthly_net_benefit),
        "share_of_all_segments": metrics.share_of_all_segments,
        "share_of_templated_segments": metrics.share_of_templated_segments,
        "daily_segments": [day_segments_to_dict(item) for item in metrics.daily_segments],
    }


def candidate_to_dict(candidate: CandidateView) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "template_text": candidate.template_text,
        "messages": candidate.messages,
        "segments": candidate.segments,
        "actual_cost": money(candidate.actual_cost),
        "templated_cost": money(candidate.templated_cost),
        "monthly_messages": candidate.monthly_messages,
        "monthly_segments": candidate.monthly_segments,
        "monthly_actual_cost": money(candidate.monthly_actual_cost),
        "monthly_templated_cost": money(candidate.monthly_templated_cost),
        "monthly_saving": money(candidate.monthly_saving),
        "template_fee": money(candidate.template_fee),
        "net_monthly": money(candidate.net_monthly),
        "payback_months": candidate.payback_months,
        "confidence": candidate.confidence,
        "coverage": candidate.coverage,
        "senders": list(candidate.senders),
        "operators": list(candidate.operators),
        "period_from": moment(candidate.period_from),
        "period_to": moment(candidate.period_to),
        "is_partial_period": candidate.is_partial_period,
        "examples": list(candidate.examples),
        "status": candidate.status,
        "warnings": list(candidate.warnings),
        "foreign_matches": candidate.foreign_matches,
        "share_of_all_segments": candidate.share_of_all_segments,
        "daily_segments": [day_segments_to_dict(item) for item in candidate.daily_segments],
    }


def operator_trigger_to_dict(item: OperatorTriggerView) -> dict[str, Any]:
    return {
        "template_id": item.template_id,
        "template_name": item.template_name,
        "sender": item.sender,
        "operator": item.operator,
        "listed": item.listed,
        "matched_messages": item.matched_messages,
        "triggered_messages": item.triggered_messages,
        "matched_segments": item.matched_segments,
        "share": item.share,
        "trigger_rate": item.trigger_rate,
    }


def analysis_to_dict(view: AnalysisView) -> dict[str, Any]:
    return {
        "run_id": view.run_id,
        "batch_id": view.batch_id,
        "created_at": moment(view.created_at),
        "period_from": moment(view.period_from),
        "period_to": moment(view.period_to),
        "message_count": view.message_count,
        "matched_message_count": view.matched_message_count,
        "triggered_message_count": view.triggered_message_count,
        "total_net_benefit": money(view.total_net_benefit),
        "total_monthly_net_benefit": money(view.total_monthly_net_benefit),
        "total_segments": view.total_segments,
        "templated_segments": view.templated_segments,
        "inactive_templates": view.inactive_templates,
        "trigger_rate": view.trigger_rate,
        "is_partial_period": view.is_partial_period,
        "metrics": [metrics_to_dict(item) for item in view.metrics],
        "candidates": [candidate_to_dict(item) for item in view.candidates],
        "operator_triggers": [operator_trigger_to_dict(item) for item in view.operator_triggers],
        "warnings": list(view.warnings),
        "daily_total_segments": [day_segments_to_dict(item) for item in view.daily_total_segments],
        "daily_templated_segments": [
            day_segments_to_dict(item) for item in view.daily_templated_segments
        ],
    }


def action_item_to_dict(item: ActionItemView) -> dict[str, Any]:
    return {
        "key": item.key,
        "kind": item.kind,
        "severity": item.severity,
        "title": item.title,
        "subject": item.subject,
        "template_id": item.template_id,
        "template_name": item.template_name,
        "operator": item.operator,
        "detail": item.detail,
        "recommendation": item.recommendation,
        "monthly_loss": money(item.monthly_loss),
        "messages": item.messages,
        "segments": item.segments,
        "drill_down": item.drill_down,
    }


def action_center_to_dict(view: ActionCenterView) -> dict[str, Any]:
    return {
        "batch_id": view.batch_id,
        "period_from": moment(view.period_from),
        "period_to": moment(view.period_to),
        "is_partial_period": view.is_partial_period,
        "monthly_factor": view.monthly_factor,
        "total_monthly_loss": money(view.total_monthly_loss),
        "loss_templates": view.loss_templates,
        "off_operator_loss": money(view.off_operator_loss),
        "untriggered_loss": money(view.untriggered_loss),
        "off_operator_messages": view.off_operator_messages,
        "untriggered_messages": view.untriggered_messages,
        "unmatched_templated_messages": view.unmatched_templated_messages,
        "unmatched_templated_segments": view.unmatched_templated_segments,
        "unmatched_templated_cost": money(view.unmatched_templated_cost),
        "observed_ordinary_rate": money(view.observed_ordinary_rate),
        "observed_templated_rate": money(view.observed_templated_rate),
        "items": [action_item_to_dict(item) for item in view.items],
        "warnings": list(view.warnings),
    }


def statistics_to_dict(statistics: BatchStatistics | None) -> dict[str, Any] | None:
    if statistics is None:
        return None
    return {
        "message_count": statistics.message_count,
        "segments": statistics.segments,
        "cost": money(statistics.cost),
        "delivered": statistics.delivered,
        "ordinary_messages": statistics.ordinary_messages,
        "ordinary_segments": statistics.ordinary_segments,
        "ordinary_cost": money(statistics.ordinary_cost),
        "ordinary_rate": money(statistics.ordinary_rate),
        "templated_messages": statistics.templated_messages,
        "templated_segments": statistics.templated_segments,
        "templated_cost": money(statistics.templated_cost),
        "templated_rate": money(statistics.templated_rate),
        "senders": statistics.senders,
        "average_cost": money(statistics.average_cost),
        "ordinary_average_cost": money(statistics.ordinary_average_cost),
        "templated_average_cost": money(statistics.templated_average_cost),
        "average_segment_cost": money(statistics.average_segment_cost),
        "ordinary_average_segment_cost": money(statistics.ordinary_average_segment_cost),
        "templated_average_segment_cost": money(statistics.templated_average_segment_cost),
        "delivered_share": statistics.delivered_share,
        "ordinary_share": statistics.ordinary_share,
        "templated_share": statistics.templated_share,
        "ordinary_segment_share": statistics.ordinary_segment_share,
        "templated_segment_share": statistics.templated_segment_share,
        "average_segments": statistics.average_segments,
    }


def operator_statistics_to_dict(item: OperatorStatistics) -> dict[str, Any]:
    return {
        "operator": item.operator,
        "messages": item.messages,
        "segments": item.segments,
        "cost": money(item.cost),
        "average_segment_cost": money(item.average_segment_cost),
    }


def segmentation_to_dict(segmentation: SegmentationStatistics | None) -> dict[str, Any] | None:
    if segmentation is None:
        return None
    return {
        "subscribers": segmentation.subscribers,
        "subscriber_segments": segmentation.subscriber_segments,
        "subscriber_messages": segmentation.subscriber_messages,
        "average_subscriber_segments": segmentation.average_subscriber_segments,
        "average_subscriber_messages": segmentation.average_subscriber_messages,
        "subscribers_by_segments": [
            {"segments": item.segments, "count": item.count, "share": item.share}
            for item in segmentation.subscribers_by_segments
        ],
        "subscribers_by_operator": [
            {
                "operator": item.operator,
                "subscribers": item.subscribers,
                "share": item.share,
            }
            for item in segmentation.subscribers_by_operator
        ],
        "messages_by_segments": [
            {"segments": item.segments, "count": item.count, "share": item.share}
            for item in segmentation.messages_by_segments
        ],
        "zero_segment_messages": segmentation.zero_segment_messages,
    }


def dashboard_to_dict(summary: DashboardSummary) -> dict[str, Any]:
    return {
        "batches": [batch_to_dict(item) for item in summary.batches],
        "batch": batch_to_dict(summary.batch) if summary.batch is not None else None,
        "statistics": statistics_to_dict(summary.statistics),
        "template_count": summary.template_count,
        "active_templates": summary.active_templates,
        "inactive_templates": summary.inactive_templates,
        "candidates": summary.candidates,
        "total_monthly_net_benefit": money(summary.total_monthly_net_benefit),
        "profitable_candidates": summary.profitable_candidates,
        "profitable_candidates_benefit": money(summary.profitable_candidates_benefit),
        "loss_templates_benefit": money(summary.loss_templates_benefit),
        "potential_benefit": money(summary.potential_benefit),
        "warnings": list(summary.warnings),
        "operators": [operator_statistics_to_dict(item) for item in summary.operators],
        "segmentation": segmentation_to_dict(summary.segmentation),
        "daily_segments": [daily_segments_to_dict(item) for item in summary.daily_segments],
    }


def settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    return {
        "data_dir": str(settings.data_dir),
        "database_path": str(settings.database_path),
        "template_fee": money(settings.template_fee),
        "min_support": settings.min_support,
        "min_cluster_segments": settings.min_cluster_segments,
        "min_text_length": settings.min_text_length,
        "max_foreign_matches": settings.max_foreign_matches,
        "max_w_words": settings.max_w_words,
        "max_d_words": settings.max_d_words,
        "max_word_slots_per_merge": settings.max_word_slots_per_merge,
        "max_literal_cardinality": settings.max_literal_cardinality,
        "max_tail_depth": settings.max_tail_depth,
        "punctuation_policy": settings.punctuation_policy,
        "fold_yo": settings.fold_yo,
        "fold_homoglyphs": settings.fold_homoglyphs,
        "sender_case_sensitive": settings.sender_case_sensitive,
        "baseline_mode": settings.baseline_mode,
        "delivered_only": settings.delivered_only,
        "benefit_thresholds": [str(level) for level in settings.benefit_thresholds.levels],
        "theme": settings.theme,
    }


def theme_to_dict(theme: Theme) -> dict[str, Any]:
    palette = asdict(theme.palette)
    return {
        "id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "palette": palette,
        "font_family": theme.font_family,
        "font_heading": theme.heading_font,
        "font_mono": theme.mono_font,
        "font_size": theme.font_size,
        "radius": theme.radius,
        "border_width": theme.border_width,
        "spacing_scale": theme.spacing_scale,
        "hard_shadow": theme.hard_shadow,
        "bold_text": theme.bold_text,
    }
