"""Use case: анализ активности шаблонов и поиск кандидатов."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from mts_templates.application.dto import (
    AnalysisConfig,
    AnalysisView,
    AnalyzeRequest,
)
from mts_templates.application.ports import (
    AnalysisRepository,
    ImportRepository,
    MessageQueryRepository,
    TemplateRepository,
)
from mts_templates.application.services.analysis_service import (
    compute_analysis,
    compute_config_hash,
)
from mts_templates.application.services.analysis_view import to_analysis_view
from mts_templates.domain.analytics.analysis import AnalysisRun
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.errors import TemplateAnalysisError
from mts_templates.domain.tariffs.models import TariffCatalog

logger = logging.getLogger(__name__)


class AnalyzeTemplates:
    """Считает метрики шаблонов и кандидатов, кэшируя прогон по конфигурации."""

    def __init__(
        self,
        imports: ImportRepository,
        messages: MessageQueryRepository,
        templates: TemplateRepository,
        analysis: AnalysisRepository,
        config_provider: Callable[[], AnalysisConfig],
        catalog: TariffCatalog | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._imports = imports
        self._messages = messages
        self._templates = templates
        self._analysis = analysis
        self._config_provider = config_provider
        self._catalog = catalog
        self._clock = clock

    def execute(
        self,
        request: AnalyzeRequest,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> AnalysisView:
        run, templates = self.execute_run(request, should_cancel=should_cancel)
        return to_analysis_view(run, templates)

    def execute_run(
        self,
        request: AnalyzeRequest,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[AnalysisRun, tuple[SmsTemplate, ...]]:
        """Доменный прогон анализа: нужен сценариям, которым мало `AnalysisView`."""
        batch = self._imports.get(request.batch_id)
        if batch is None:
            raise TemplateAnalysisError(f"Загрузка статистики не найдена: {request.batch_id}")

        templates = tuple(self._templates.list_all())
        config = self._config_provider()
        config_hash = compute_config_hash(
            config, templates, include_candidates=request.include_candidates
        )

        if not request.force:
            cached = self._analysis.find(batch.id, config_hash)
            if cached is not None:
                logger.info("Анализ взят из кэша: batch=%s hash=%s", batch.id, config_hash)
                return cached, templates

        run = compute_analysis(
            batch=batch,
            messages=lambda: self._messages.iter_messages(batch.id),
            templates=templates,
            config=config,
            include_candidates=request.include_candidates,
            run_id=str(uuid.uuid4()),
            config_hash=config_hash,
            created_at=self._clock(),
            catalog=self._catalog,
            should_cancel=should_cancel,
        )
        self._analysis.save(run)
        logger.info(
            "Анализ выполнен: batch=%s шаблонов=%d кандидатов=%d",
            batch.id,
            len(run.metrics),
            len(run.candidates),
        )
        return run, templates
