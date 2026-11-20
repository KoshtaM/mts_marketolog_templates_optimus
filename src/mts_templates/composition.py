"""Сборка зависимостей приложения в одном месте."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mts_templates.application.dto import AnalysisConfig
from mts_templates.application.settings import AppSettings
from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates
from mts_templates.application.use_cases.dashboard import GetDashboardSummary, ListBatches
from mts_templates.application.use_cases.export_report import ExportReport
from mts_templates.application.use_cases.find_candidates import FindCandidates
from mts_templates.application.use_cases.import_statistics import ImportStatistics
from mts_templates.application.use_cases.import_templates import (
    ImportTemplates,
    PreviewTemplateFile,
)
from mts_templates.domain.tariffs.models import TariffCatalog
from mts_templates.infrastructure.config import TomlSettingsStore, load_settings
from mts_templates.infrastructure.excel.report_writer import ExcelReportWriter
from mts_templates.infrastructure.excel.statistics_reader import ExcelStatisticsReader
from mts_templates.infrastructure.excel.templates_reader import ExcelTemplateReader
from mts_templates.infrastructure.persistence.sqlite.analysis_repository import (
    SqliteAnalysisRepository,
)
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.query_repository import (
    SqliteMessageQueryRepository,
)
from mts_templates.infrastructure.persistence.sqlite.repositories import (
    SqliteImportRepository,
)
from mts_templates.infrastructure.persistence.sqlite.template_repository import (
    SqliteTemplateRepository,
)
from mts_templates.infrastructure.tariffs.toml_catalog import load_tariff_catalog


@dataclass(frozen=True, slots=True)
class Container:
    """Готовые к использованию сервисы приложения."""

    settings: AppSettings
    settings_store: TomlSettingsStore
    database: Database
    catalog: TariffCatalog
    import_statistics: ImportStatistics
    preview_templates: PreviewTemplateFile
    import_templates: ImportTemplates
    analyze_templates: AnalyzeTemplates
    find_candidates: FindCandidates
    list_batches: ListBatches
    dashboard: GetDashboardSummary
    export_report: ExportReport
    config_provider: Callable[[], AnalysisConfig]


def analysis_config(settings: AppSettings) -> AnalysisConfig:
    """Перевести настройки приложения в параметры анализа."""
    return AnalysisConfig(
        baseline_mode=settings.baseline_mode,
        delivered_only=settings.delivered_only,
        min_support=settings.min_support,
        min_cluster_segments=settings.min_cluster_segments,
        min_text_length=settings.min_text_length,
        max_foreign_matches=settings.max_foreign_matches,
        max_w_words=settings.max_w_words,
        max_d_words=settings.max_d_words,
        max_word_slots_per_merge=settings.max_word_slots_per_merge,
        max_literal_cardinality=settings.max_literal_cardinality,
        max_tail_depth=settings.max_tail_depth,
        punctuation_policy=settings.punctuation_policy,
        fold_yo=settings.fold_yo,
        fold_homoglyphs=settings.fold_homoglyphs,
        sender_case_sensitive=settings.sender_case_sensitive,
        template_fee=settings.template_fee,
    )


def build_container(
    database_path: str | Path | None = None,
    settings: AppSettings | None = None,
) -> Container:
    """Собрать контейнер; путь к БД по умолчанию — из настроек."""
    resolved_settings = settings or load_settings()
    database = Database(database_path or resolved_settings.database_path)
    database.migrate()
    settings_store = TomlSettingsStore(resolved_settings.data_dir)

    imports = SqliteImportRepository(database)
    templates = SqliteTemplateRepository(database)
    messages = SqliteMessageQueryRepository(database)
    analysis = SqliteAnalysisRepository(database)
    catalog = load_tariff_catalog()

    def config_provider() -> AnalysisConfig:
        return analysis_config(settings_store.load())

    analyzer = AnalyzeTemplates(
        imports=imports,
        messages=messages,
        templates=templates,
        analysis=analysis,
        config_provider=config_provider,
        catalog=catalog,
    )
    return Container(
        settings=resolved_settings,
        settings_store=settings_store,
        database=database,
        catalog=catalog,
        import_statistics=ImportStatistics(
            reader=ExcelStatisticsReader(),
            repository=imports,
        ),
        preview_templates=PreviewTemplateFile(ExcelTemplateReader()),
        import_templates=ImportTemplates(ExcelTemplateReader(), templates, analysis),
        analyze_templates=analyzer,
        find_candidates=FindCandidates(analyzer),
        list_batches=ListBatches(imports),
        dashboard=GetDashboardSummary(imports, messages, templates, analysis),
        export_report=ExportReport(
            imports=imports,
            messages=messages,
            templates=templates,
            analysis=analysis,
            writer=ExcelReportWriter(),
            config_provider=config_provider,
        ),
        config_provider=config_provider,
    )
