"""Use case: центр действий по выбранной загрузке статистики."""

from __future__ import annotations

from collections.abc import Callable

from mts_templates.application.dto import ActionCenterView, AnalyzeRequest
from mts_templates.application.services.analysis_view import to_action_center_view
from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates
from mts_templates.domain.analytics.actions import build_action_center


class GetActionCenter:
    """Собирает рабочий список проблем из доменного прогона анализа.

    Прогон берётся из того же кэша, что и вкладки «Шаблоны» и «Кандидаты»:
    отдельного расчёта и отдельной схемы хранения не вводится.
    """

    def __init__(self, analyze: AnalyzeTemplates) -> None:
        self._analyze = analyze

    def execute(
        self,
        batch_id: str,
        *,
        force: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ActionCenterView:
        run, templates = self._analyze.execute_run(
            AnalyzeRequest(batch_id=batch_id, include_candidates=True, force=force),
            should_cancel=should_cancel,
        )
        center = build_action_center(run, templates)
        return to_action_center_view(center, run)
