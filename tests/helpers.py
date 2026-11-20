"""Тестовые фабрики."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator

MSK = timezone(timedelta(hours=3))


def make_message(
    message_id: str,
    *,
    segments: int = 1,
    day: int = 1,
    month: int = 11,
    year: int = 2026,
    hour: int = 12,
    recipient: str = "79000000000",
    operator: Operator = Operator.MTS,
    message_class: MessageClass = MessageClass.ORDINARY,
    cost: Money | None = None,
    delivered: bool = True,
) -> SmsMessage:
    return SmsMessage(
        message_id=message_id,
        sent_at=datetime(year, month, day, hour, 0, tzinfo=MSK),
        recipient=recipient,
        operator=operator,
        sender="TEST",
        text="Тестовое сообщение",
        segments=segments,
        message_class=message_class,
        cost=cost or Money.zero(),
        delivered=delivered,
    )
