"""Use case: поиск кандидатов на регистрацию шаблонов."""

from __future__ import annotations

from collections.abc import Callable

from mts_templates.application.dto import AnalyzeRequest, CandidateView
from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates


class FindCandidates:
    """Возвращает только кандидатов, переиспользуя общий сценарий анализа."""

    def __init__(self, analyzer: AnalyzeTemplates) -> None:
        self._analyzer = analyzer

    def execute(
        self,
        batch_id: str,
        *,
        force: bool = False,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[CandidateView, ...]:
        view = self._analyzer.execute(
            AnalyzeRequest(batch_id=batch_id, include_candidates=True, force=force),
            should_cancel=should_cancel,
        )
        return view.candidates
