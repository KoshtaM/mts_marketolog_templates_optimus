"""Инварианты агрегатов и сущностей."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from mts_templates.domain.entities import BillingRow, SmsMessage, SmsTemplate
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from tests.helpers import MSK, make_message


def make_message_with_rows(
    *,
    cost: str,
    segments: int,
    rows: tuple[BillingRow, ...],
) -> SmsMessage:
    return SmsMessage(
        message_id="A",
        sent_at=datetime(2026, 11, 5, 12, 0, tzinfo=MSK),
        recipient="79000000000",
        operator=Operator.MTS,
        sender="TEST",
        text="Код 1234",
        segments=segments,
        message_class=MessageClass.TEMPLATED,
        cost=Money.from_rub(cost),
        delivered=True,
        billing_rows=rows,
    )


def test_message_cost_must_equal_billing_rows_sum() -> None:
    rows = (
        BillingRow("Пакет", Money.from_rub("11.00"), Money.zero(), 1),
        BillingRow("Пакет", Money.from_rub("35.00"), Money.from_rub("35.00"), 1),
    )

    with pytest.raises(ValueError, match="сумме биллинговых строк"):
        make_message_with_rows(cost="11.00", segments=1, rows=rows)


def test_message_segments_must_be_sum_of_billing_rows() -> None:
    rows = (
        BillingRow("Пакет", Money.zero(), Money.zero(), 1),
        BillingRow("Пакет", Money.zero(), Money.zero(), 3),
    )

    with pytest.raises(ValueError, match="сумме строк"):
        make_message_with_rows(cost="0.00", segments=1, rows=rows)


def test_message_accepts_consistent_billing_rows() -> None:
    rows = (
        BillingRow("Пакет", Money.from_rub("11.00"), Money.zero(), 1),
        BillingRow("Пакет", Money.from_rub("35.00"), Money.from_rub("35.00"), 3),
    )

    message = make_message_with_rows(cost="35.00", segments=4, rows=rows)

    assert message.cost == Money.from_rub("35.00")
    assert message.segments == 4


def test_message_requires_timezone_aware_date() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SmsMessage(
            message_id="A",
            sent_at=datetime(2026, 11, 5, 12, 0),
            recipient="79000000000",
            operator=Operator.MTS,
            sender="TEST",
            text="Код 1234",
            segments=1,
            message_class=MessageClass.ORDINARY,
            cost=Money.zero(),
            delivered=True,
        )


def test_message_rejects_negative_segments() -> None:
    with pytest.raises(ValueError, match="отрицательным"):
        make_message("A", segments=-1)


def test_message_requires_id_and_recipient() -> None:
    with pytest.raises(ValueError, match="message_id"):
        SmsMessage(
            message_id="",
            sent_at=datetime(2026, 11, 5, 12, 0, tzinfo=MSK),
            recipient="79000000000",
            operator=Operator.MTS,
            sender="TEST",
            text="Код 1234",
            segments=1,
            message_class=MessageClass.ORDINARY,
            cost=Money.zero(),
            delivered=True,
        )


def test_template_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="Текст шаблона"):
        SmsTemplate(template_id="t1", name="Пустой", text="   ", sender="TEST")


def test_template_rejects_negative_fee() -> None:
    with pytest.raises(ValueError, match="отрицательной"):
        SmsTemplate(
            template_id="t1",
            name="Шаблон",
            text="Код {code}",
            sender="TEST",
            monthly_fee=Money.from_rub("-1.00"),
        )


def test_template_defaults_to_two_thousand_rubles() -> None:
    template = SmsTemplate(template_id="t1", name="Шаблон", text="Код {code}", sender="TEST")

    assert template.monthly_fee.amount == Decimal("2000.00")
    assert template.active is True
