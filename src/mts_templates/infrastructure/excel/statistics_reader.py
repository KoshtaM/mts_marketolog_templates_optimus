"""Чтение Excel-выгрузки статистики МТС-Маркетолога."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import polars as pl

from mts_templates.domain.analytics.import_aggregation import (
    DELIVERED_STATUSES,
    RawSmsRow,
)
from mts_templates.domain.errors import StatisticsImportError
from mts_templates.domain.value_objects import Money, Operator

MSK = timezone(timedelta(hours=3))

COL_MESSAGE_ID = "ID сообщения"
COL_SENDER = "Имя отправителя"
COL_RECIPIENT = "Номер получателя"
COL_OPERATOR = "Оператор получателя"
COL_SENT_AT = "Дата попытки отправки"
COL_SEND_STATUS = "Статус отправки"
COL_TEXT = "Текст сообщения"
COL_PRICE = "Цена за один сегмент"
COL_COST = "Стоимость"
COL_SEGMENTS = "Количество сегментов в sms"
COL_DELIVERY_STATUS = "Статус доставки СМС или ММС"
COL_PACKAGE_TYPE = "Тип пакета"

REQUIRED_COLUMNS = (
    COL_MESSAGE_ID,
    COL_SENDER,
    COL_RECIPIENT,
    COL_OPERATOR,
    COL_SENT_AT,
    COL_SEND_STATUS,
    COL_TEXT,
    COL_PRICE,
    COL_COST,
    COL_SEGMENTS,
    COL_DELIVERY_STATUS,
    COL_PACKAGE_TYPE,
)

EMPTY_MARKERS = frozenset({"", "-", "None", "nan"})
NAIVE_DATES_WARNING = "В части строк дата без часового пояса: подставлен +03:00 (МСК)."


def normalize_header(value: str) -> str:
    """Снять BOM, лишние пробелы и неразрывные пробелы."""
    cleaned = value.replace("\ufeff", "").replace("\xa0", " ")
    return " ".join(cleaned.split())


class ExcelStatisticsReader:
    """Адаптер статистики: Excel → `RawSmsRow`."""

    def read(self, path: Path, warnings: list[str]) -> Iterable[RawSmsRow]:
        return self._iterate(path, warnings)

    def _iterate(self, path: Path, warnings: list[str]) -> Iterator[RawSmsRow]:
        frame = self._load(path)
        naive_dates = False

        for line_number, record in enumerate(frame.iter_rows(named=True), start=2):
            message_id = _text(record[COL_MESSAGE_ID])
            if not message_id:
                continue

            sent_at = _parse_datetime(record[COL_SENT_AT], line_number)
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=MSK)
                naive_dates = True

            delivery_status = _text(record[COL_DELIVERY_STATUS])
            yield RawSmsRow(
                message_id=message_id,
                sent_at=sent_at,
                recipient=_text(record[COL_RECIPIENT]),
                operator=Operator.from_raw(_text(record[COL_OPERATOR])),
                sender=_text(record[COL_SENDER]),
                text=_text(record[COL_TEXT]),
                segments=_parse_int(record[COL_SEGMENTS], COL_SEGMENTS, line_number),
                cost=_parse_money(record[COL_COST], COL_COST, line_number),
                price_per_segment=_parse_money(record[COL_PRICE], COL_PRICE, line_number),
                package_type=_text(record[COL_PACKAGE_TYPE]) or None,
                delivered=delivery_status in DELIVERED_STATUSES,
                send_status=_text(record[COL_SEND_STATUS]),
                delivery_status=delivery_status,
            )

        if naive_dates:
            warnings.append(NAIVE_DATES_WARNING)

    def _load(self, path: Path) -> pl.DataFrame:
        if not path.is_file():
            raise StatisticsImportError(f"Файл не найден: {path.name}")

        try:
            frame = pl.read_excel(path, engine="calamine", infer_schema_length=0)
        except Exception as exc:  # polars/fastexcel поднимают разные типы
            raise StatisticsImportError(f"Не удалось прочитать Excel: {exc}") from exc

        frame = frame.rename({column: normalize_header(column) for column in frame.columns})
        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise StatisticsImportError("В файле нет обязательных колонок: " + ", ".join(missing))
        return frame


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_datetime(value: object, line_number: int) -> datetime:
    raw = _text(value)
    if raw in EMPTY_MARKERS:
        raise StatisticsImportError(f"Строка {line_number}: пустая дата отправки")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise StatisticsImportError(
            f"Строка {line_number}: не удалось разобрать дату {raw!r}"
        ) from exc


def _parse_int(value: object, column: str, line_number: int) -> int:
    raw = _text(value)
    if raw in EMPTY_MARKERS:
        return 0
    try:
        return int(Decimal(raw.replace(",", ".").replace(" ", "")))
    except (InvalidOperation, ValueError) as exc:
        raise StatisticsImportError(
            f"Строка {line_number}: некорректное значение {column}={raw!r}"
        ) from exc


def _parse_money(value: object, column: str, line_number: int) -> Money | None:
    raw = _text(value)
    if raw in EMPTY_MARKERS:
        return None
    try:
        amount = Decimal(raw.replace(",", ".").replace("\xa0", "").replace(" ", ""))
    except InvalidOperation as exc:
        raise StatisticsImportError(
            f"Строка {line_number}: некорректное значение {column}={raw!r}"
        ) from exc
    return Money(amount)
