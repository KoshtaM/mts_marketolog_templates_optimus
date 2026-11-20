"""Схлопывание биллинговых строк выгрузки в логические сообщения.

Одна отправка может быть представлена несколькими строками с разными
`Тип пакета` / `Цена за один сегмент` / `Стоимость`. Длинная SMS оплачивается
частями: например, 23 + 5 + 15 сегментов. Поэтому стоимость и сегменты
суммируем, расхождения в метаданных фиксируем.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from mts_templates.domain.entities import BillingRow, SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator

TEMPLATED_PACKAGE_MARKER = "шаблонирован"

SEND_ERROR_STATUS = "Ошибка отправки"
DELIVERY_ERROR_STATUS = "Ошибка доставки"
DELIVERED_STATUSES = frozenset({"Успешная доставка"})
PARTIAL_DELIVERY_STATUS = "Частично доставлено"


@dataclass(frozen=True, slots=True)
class RawSmsRow:
    """Нормализованная строка выгрузки, подготовленная адаптером."""

    message_id: str
    sent_at: datetime
    recipient: str
    operator: Operator
    sender: str
    text: str
    segments: int
    cost: Money | None
    price_per_segment: Money | None
    package_type: str | None
    delivered: bool
    send_status: str = ""
    delivery_status: str = ""

    def __post_init__(self) -> None:
        if self.sent_at.tzinfo is None:
            raise ValueError("sent_at должен быть timezone-aware")
        if self.segments < 0:
            raise ValueError("Количество сегментов не может быть отрицательным")


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """Расхождение внутри одной группы строк `ID сообщения`."""

    message_id: str
    field: str
    detail: str


@dataclass(frozen=True, slots=True)
class AggregationResult:
    messages: tuple[SmsMessage, ...]
    issues: tuple[QualityIssue, ...]

    @property
    def duplicate_message_ids(self) -> int:
        return sum(1 for message in self.messages if len(message.billing_rows) > 1)


def classify_message(package_type: str | None) -> MessageClass:
    """Класс сообщения по типу пакета из выгрузки."""
    if package_type and TEMPLATED_PACKAGE_MARKER in package_type.casefold():
        return MessageClass.TEMPLATED
    return MessageClass.ORDINARY


def aggregate_rows(rows: Iterable[RawSmsRow]) -> AggregationResult:
    """Собрать логические сообщения из биллинговых строк в порядке первого появления."""
    groups: dict[str, list[RawSmsRow]] = {}
    for row in rows:
        groups.setdefault(row.message_id, []).append(row)

    messages: list[SmsMessage] = []
    issues: list[QualityIssue] = []

    for message_id, group in groups.items():
        base = group[0]
        messages.append(_build_message(base, group))
        issues.extend(_check_consistency(message_id, group))

    return AggregationResult(messages=tuple(messages), issues=tuple(issues))


def _build_message(base: RawSmsRow, group: list[RawSmsRow]) -> SmsMessage:
    total_cost = sum((row.cost for row in group if row.cost is not None), Money.zero())
    billing_rows = tuple(
        BillingRow(
            package_type=row.package_type or "",
            price_per_segment=row.price_per_segment,
            cost=row.cost or Money.zero(),
            segments=row.segments,
        )
        for row in group
    )
    message_class = (
        MessageClass.TEMPLATED
        if any(classify_message(row.package_type) is MessageClass.TEMPLATED for row in group)
        else MessageClass.ORDINARY
    )

    return SmsMessage(
        message_id=base.message_id,
        sent_at=base.sent_at,
        recipient=base.recipient,
        operator=base.operator,
        sender=base.sender,
        text=base.text,
        segments=sum(row.segments for row in group),
        message_class=message_class,
        cost=total_cost,
        delivered=any(row.delivered for row in group),
        billing_rows=billing_rows,
    )


def _check_consistency(message_id: str, group: list[RawSmsRow]) -> list[QualityIssue]:
    if len(group) == 1:
        return []

    issues: list[QualityIssue] = []
    checks: tuple[tuple[str, set[object]], ...] = (
        ("text", {row.text for row in group}),
        ("recipient", {row.recipient for row in group}),
        ("sent_at", {row.sent_at for row in group}),
        ("operator", {row.operator for row in group}),
        ("sender", {row.sender for row in group}),
    )
    for field, values in checks:
        if len(values) > 1:
            issues.append(
                QualityIssue(
                    message_id=message_id,
                    field=field,
                    detail=f"Разные значения в {len(group)} биллинговых строках",
                )
            )

    if len({row.segments for row in group}) > 1:
        issues.append(
            QualityIssue(
                message_id=message_id,
                field="segments",
                detail="Различается количество сегментов, просуммировано по строкам",
            )
        )
    return issues
