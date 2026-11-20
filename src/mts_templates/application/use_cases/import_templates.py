"""Use case: импорт списка зарегистрированных шаблонов."""

from __future__ import annotations

from pathlib import Path

from mts_templates.application.dto import (
    ImportTemplatesRequest,
    TemplateFilePreview,
    TemplateImportReport,
)
from mts_templates.application.ports import (
    AnalysisRepository,
    TemplateReader,
    TemplateRepository,
)
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.errors import TemplateAnalysisError

DUPLICATES_WARNING = (
    "В файле есть повторяющиеся шаблоны (тот же отправитель и текст): оставлена первая запись."
)


class PreviewTemplateFile:
    """Показать колонки и первые строки файла для диалога сопоставления."""

    def __init__(self, reader: TemplateReader) -> None:
        self._reader = reader

    def execute(self, path: Path, limit: int = 10) -> TemplateFilePreview:
        return self._reader.preview(path, limit)


class ImportTemplates:
    """Заменяет набор шаблонов выгрузкой; прогоны анализа сбрасываются."""

    def __init__(
        self,
        reader: TemplateReader,
        repository: TemplateRepository,
        analysis: AnalysisRepository,
    ) -> None:
        self._reader = reader
        self._repository = repository
        self._analysis = analysis

    def execute(self, request: ImportTemplatesRequest) -> TemplateImportReport:
        if not request.path.is_file():
            raise TemplateAnalysisError(f"Файл не найден: {request.path}")

        result = self._reader.read(request.path, request.mapping)
        if not result.templates:
            details = "; ".join(result.warnings[:3])
            raise TemplateAnalysisError(
                "В файле не найдено ни одного подходящего шаблона"
                + (f": {details}" if details else "")
            )

        unique: dict[tuple[str, str], SmsTemplate] = {}
        duplicates = 0
        for template in result.templates:
            key = (template.sender, template.text)
            if key in unique:
                duplicates += 1
                continue
            unique[key] = template

        inserted, updated, removed = self._repository.replace_all(list(unique.values()))
        self._analysis.invalidate_all()
        warnings: list[str] = list(result.warnings)
        if duplicates:
            warnings.append(DUPLICATES_WARNING)

        return TemplateImportReport(
            imported=inserted,
            updated=updated,
            removed=removed,
            duplicates=duplicates,
            skipped_empty=0,
            warnings=tuple(warnings),
        )
