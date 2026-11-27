"""Порты приложения: адаптеры подставляются в composition root."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from mts_templates.application.dto import (
    BatchStatistics,
    DailySegments,
    ExportReportResult,
    ImportBatch,
    OperatorStatistics,
    ReportBundle,
    SegmentationStatistics,
    StoredStatistics,
    TemplateColumnMapping,
    TemplateFilePreview,
    TemplateReadResult,
)
from mts_templates.application.settings import AppSettings
from mts_templates.domain.analytics.analysis import AnalysisRun
from mts_templates.domain.analytics.import_aggregation import RawSmsRow
from mts_templates.domain.entities import SmsMessage, SmsTemplate


class StatisticsReader(Protocol):
    """Читает Excel-выгрузку статистики и отдаёт нормализованные строки."""

    def read(self, path: Path, warnings: list[str]) -> Iterable[RawSmsRow]:
        """Строки выгрузки; предупреждения дописываются в `warnings`."""
        ...


class TemplateReader(Protocol):
    """Читает список зарегистрированных шаблонов."""

    def preview(self, path: Path, limit: int = 10) -> TemplateFilePreview: ...

    def read(
        self, path: Path, mapping: TemplateColumnMapping | None = None
    ) -> TemplateReadResult: ...


class ImportRepository(Protocol):
    """Хранилище загрузок статистики."""

    def find_batch(self, source_sha256: str) -> ImportBatch | None: ...

    def get(self, batch_id: str) -> ImportBatch | None: ...

    def list_batches(self) -> tuple[ImportBatch, ...]: ...

    def save(self, stored: StoredStatistics) -> None: ...

    def rename(self, batch_id: str, name: str | None) -> ImportBatch | None: ...

    def set_period_label(self, batch_id: str, period_label: str | None) -> ImportBatch | None: ...

    def delete(self, batch_id: str) -> bool: ...

    def delete_all(self) -> int: ...


class TemplateRepository(Protocol):
    """Хранилище зарегистрированных шаблонов."""

    def list_all(self) -> tuple[SmsTemplate, ...]: ...

    def find(self, template_id: str) -> SmsTemplate | None: ...

    def count(self) -> int: ...

    def count_active(self) -> int: ...

    def replace_all(self, templates: list[SmsTemplate]) -> tuple[int, int, int]:
        """Заменить набор шаблонов; вернуть `(добавлено, обновлено, удалено)`."""
        ...


class MessageQueryRepository(Protocol):
    """Чтение сообщений и агрегатов по загрузке."""

    def iter_messages(self, batch_id: str) -> Iterator[SmsMessage]: ...

    def statistics(self, batch_id: str) -> BatchStatistics: ...

    def operator_statistics(self, batch_id: str) -> tuple[OperatorStatistics, ...]: ...

    def segmentation_statistics(self, batch_id: str) -> SegmentationStatistics: ...

    def daily_segments(self, batch_id: str) -> tuple[DailySegments, ...]: ...


class AnalysisRepository(Protocol):
    """Хранилище прогонов анализа."""

    def find(self, batch_id: str, config_hash: str) -> AnalysisRun | None: ...

    def latest(self, batch_id: str) -> AnalysisRun | None: ...

    def save(self, run: AnalysisRun) -> None: ...

    def invalidate_all(self) -> None:
        """Удалить кэш прогонов: набор шаблонов изменился."""
        ...


class ReportWriter(Protocol):
    """Пишет Excel-отчёт по результатам анализа."""

    def write(self, path: Path, bundle: ReportBundle) -> ExportReportResult: ...


class SettingsStore(Protocol):
    """Хранилище настроек приложения."""

    def load(self) -> AppSettings: ...

    def save(self, settings: AppSettings) -> None: ...
