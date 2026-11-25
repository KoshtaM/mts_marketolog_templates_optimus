"""Use case: список зарегистрированных шаблонов для интерфейса."""

from __future__ import annotations

from mts_templates.application.ports import TemplateRepository
from mts_templates.domain.entities import SmsTemplate


class ListTemplates:
    """Отдаёт текущий набор шаблонов без анализа сообщений."""

    def __init__(self, repository: TemplateRepository) -> None:
        self._repository = repository

    def execute(self) -> tuple[SmsTemplate, ...]:
        return self._repository.list_all()
