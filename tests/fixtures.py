"""Генерация синтетических Excel-выгрузок для тестов."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook

STATISTICS_HEADERS = (
    "ID сообщения",
    "ID рассылки",
    "Название рассылки",
    "Пользователь",
    "Имя отправителя",
    "Номер получателя",
    "ФИО получателя",
    "Оператор получателя",
    "Дата попытки отправки",
    "Статус отправки",
    "Текст сообщения",
    "Цена за один сегмент",
    "Стоимость",
    "Количество сегментов в sms",
    "Статус доставки СМС или ММС",
    "Статус доставки в MAX",
    "Причина неотправки sms",
    "Причина недоставки sms",
    "Дата и время доставки",
    "Дата подключения пакета",
    "Тип пакета",
    "Количество sms в пакете при покупке",
    "Канал отправки",
    "Переходы по уникальной ссылке",
    "Канал",
)


def write_statistics_xlsx(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    headers: Sequence[str] = STATISTICS_HEADERS,
) -> Path:
    """Записать xlsx с шапкой в первой строке; пустые колонки заполняются `None`."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append([row.get(header) for header in headers])
    workbook.save(path)
    return path


TEMPLATE_HEADERS = (
    "Название",
    "Текст шаблона",
    "Имя отправителя",
    "Статус",
    "Стоимость",
)


def write_templates_xlsx(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    headers: Sequence[str] = TEMPLATE_HEADERS,
) -> Path:
    """Записать xlsx со списком шаблонов."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(headers))
    for row in rows:
        sheet.append([row.get(header) for header in headers])
    workbook.save(path)
    return path
