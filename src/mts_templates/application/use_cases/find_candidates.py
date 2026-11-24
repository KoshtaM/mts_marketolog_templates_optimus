"""Use case: поиск кандидатов на регистрацию шаблонов."""

from __future__ import annotations

from collections.abc import Callable

from mts_templates.application.dto import AnalysisView, AnalyzeRequest
from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates


class FindCandidates:
    """Возвращает результат анализа с кандидатами, переиспользуя общий сценарий."""

    def __init__(self, analyzer: AnalyzeTemplates) -> None:
        self._analyzer = analyzer

    def execute(
        self,
        batch_id: str,
        *,
        force: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AnalysisView:
        return self._analyzer.execute(
            AnalyzeRequest(batch_id=batch_id, include_candidates=True, force=force),
            should_cancel=should_cancel,
        )
