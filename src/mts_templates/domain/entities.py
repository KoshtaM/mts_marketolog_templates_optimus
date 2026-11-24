"""Доменные сущности."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from mts_templates.domain.value_objects import MessageClass, Money, Operator

DEFAULT_TEMPLATE_FEE = Money.from_rub("2000.00")


@dataclass(frozen=True, slots=True)
class BillingRow:
    """Одна биллинговая строка выгрузки."""

    package_type: str
    price_per_segment: Money | None
    cost: Money
    segments: int

    def __post_init__(self) -> None:
        if self.segments < 0:
            raise ValueError("Количество сегментов не может быть отрицательным")


@dataclass(frozen=True, slots=True)
class SmsMessage:
    """Логическая отправка: один ID сообщения."""

    message_id: str
    sent_at: datetime
    recipient: str
    operator: Operator
    sender: str
    text: str
    segments: int
    message_class: MessageClass
    cost: Money
    delivered: bool
    billing_rows: tuple[BillingRow, ...] = ()
    send_status: str = ""
    delivery_status: str = ""

    def __post_init__(self) -> None:
        if not self.message_id:
            raise ValueError("message_id обязателен")
        if self.sent_at.tzinfo is None:
            raise ValueError("sent_at должен быть timezone-aware")
        if self.segments < 0:
            raise ValueError("Количество сегментов не может быть отрицательным")
        if not self.recipient:
            raise ValueError("recipient обязателен")
        if self.billing_rows:
            rows_cost = sum((row.cost for row in self.billing_rows), Money.zero())
            if rows_cost.amount != self.cost.amount:
                raise ValueError("Стоимость сообщения должна равняться сумме биллинговых строк")
            rows_segments = sum(row.segments for row in self.billing_rows)
            if self.segments != rows_segments:
                raise ValueError("Количество сегментов сообщения должно равняться сумме строк")


@dataclass(frozen=True, slots=True)
class SmsTemplate:
    """Зарегистрированный SMS-шаблон."""

    template_id: str
    name: str
    text: str
    sender: str
    active: bool = True
    monthly_fee: Money = field(default_factory=lambda: DEFAULT_TEMPLATE_FEE)
    operators: frozenset[Operator] = frozenset()
    traffic_type: str = ""
    example: str = ""

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("template_id обязателен")
        if not self.text.strip():
            raise ValueError("Текст шаблона не может быть пустым")
        if self.monthly_fee.amount < 0:
            raise ValueError("Стоимость шаблона не может быть отрицательной")
