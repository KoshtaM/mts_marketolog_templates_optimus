"""Use case: управление загрузками статистики.

Загрузка (`ImportBatch`) — техническая запись контекста импорта: имя и метка
периода нужны для чистой истории сравнения месяцев, удаление — для гигиены
базы и персональных данных. Исходный Excel-файл на диске не удаляется:
путь может указывать на файл пользователя, а не на копию приложения.
"""

from __future__ import annotations

from mts_templates.application.dto import ImportBatch
from mts_templates.application.ports import ImportRepository

MAX_NAME_LENGTH = 200
MAX_PERIOD_LABEL_LENGTH = 100


class RenameBatch:
    """Задать или сбросить пользовательское название загрузки."""

    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    def execute(self, batch_id: str, name: str | None) -> ImportBatch | None:
        return self._imports.rename(
            batch_id,
            _optional_text(name, "Название загрузки", MAX_NAME_LENGTH),
        )


class SetBatchPeriodLabel:
    """Задать или сбросить текстовую метку периода загрузки."""

    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    def execute(self, batch_id: str, period_label: str | None) -> ImportBatch | None:
        return self._imports.set_period_label(
            batch_id,
            _optional_text(period_label, "Метка периода", MAX_PERIOD_LABEL_LENGTH),
        )


class DeleteBatch:
    """Удалить одну загрузку вместе с сообщениями и прогонами анализа."""

    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    def execute(self, batch_id: str) -> bool:
        return self._imports.delete(batch_id)


class DeleteAllBatches:
    """Удалить все загрузки; шаблоны и настройки остаются."""

    def __init__(self, imports: ImportRepository) -> None:
        self._imports = imports

    def execute(self) -> int:
        return self._imports.delete_all()


def _optional_text(value: str | None, field: str, limit: int) -> str | None:
    """Нормализовать подпись: пустая строка означает «сбросить»."""
    if value is None:
        return None
    text = " ".join(value.split())
    if len(text) > limit:
        raise ValueError(f"{field}: не длиннее {limit} символов")
    return text or None
