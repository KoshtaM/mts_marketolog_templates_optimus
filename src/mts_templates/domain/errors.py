"""Доменные исключения."""

from __future__ import annotations


class DomainError(Exception):
    """Базовая ошибка домена."""


class TariffError(DomainError):
    """Ошибка тарифной модели или расчёта стоимости."""


class StatisticsImportError(DomainError):
    """Ошибка импорта статистики."""


class TemplateAnalysisError(DomainError):
    """Ошибка анализа шаблонов."""


class TemplateSyntaxError(DomainError):
    """Текст шаблона нарушает правила составления шаблонов МТС."""


class OperationCancelled(DomainError):
    """Длительная операция отменена пользователем."""
