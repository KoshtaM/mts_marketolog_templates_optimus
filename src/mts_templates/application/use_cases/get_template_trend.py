"""Use case: история шаблона по прогонам анализа."""

from __future__ import annotations

from mts_templates.application.ports import AnalysisRepository
from mts_templates.domain.analytics.trend import TemplateTrend, build_template_trend


class GetTemplateTrend:
    """Собирает тренд шаблона по сохранённым прогонам разных загрузок."""

    def __init__(self, analysis: AnalysisRepository) -> None:
        self._analysis = analysis

    def execute(self, template_id: str) -> TemplateTrend:
        runs = self._analysis.list_runs()
        return build_template_trend(runs, template_id)
