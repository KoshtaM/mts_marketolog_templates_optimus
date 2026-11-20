"""Use case: экспорт Excel-отчёта по загрузке и последнему анализу."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from mts_templates.application.dto import (
    AnalysisConfig,
    ExportReportRequest,
    ExportReportResult,
    ReportBundle,
)
from mts_templates.application.ports import (
    AnalysisRepository,
    ImportRepository,
    MessageQueryRepository,
    ReportWriter,
    TemplateRepository,
)
from mts_templates.application.services.analysis_view import to_analysis_view
from mts_templates.domain.errors import TemplateAnalysisError


class ExportReport:
    """Собирает данные в приложении, а запись файла делегирует адаптеру."""

    def __init__(
        self,
        imports: ImportRepository,
        messages: MessageQueryRepository,
        templates: TemplateRepository,
        analysis: AnalysisRepository,
        writer: ReportWriter,
        config_provider: Callable[[], AnalysisConfig],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._imports = imports
        self._messages = messages
        self._templates = templates
        self._analysis = analysis
        self._writer = writer
        self._config_provider = config_provider
        self._clock = clock

    def execute(self, request: ExportReportRequest) -> ExportReportResult:
        batch = self._imports.get(request.batch_id)
        if batch is None:
            raise TemplateAnalysisError(f"Загрузка статистики не найдена: {request.batch_id}")

        templates = self._templates.list_all()
        run = self._analysis.latest(batch.id)
        bundle = ReportBundle(
            batch=batch,
            statistics=self._messages.statistics(batch.id),
            analysis=to_analysis_view(run, templates) if run is not None else None,
            baseline_mode=self._config_provider().baseline_mode,
            template_fee=self._config_provider().template_fee,
            generated_at=self._clock(),
        )
        return self._writer.write(request.path, bundle)
