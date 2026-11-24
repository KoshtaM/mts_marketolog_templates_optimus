"""Тесты схлопывания биллинговых строк в логические сообщения."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from mts_templates.domain.analytics.import_aggregation import (
    RawSmsRow,
    aggregate_rows,
    classify_message,
)
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from tests.helpers import MSK

TEMPLATED_PACKAGE = "Подписка. Все операторы (шаблонированный)"
ORDINARY_PACKAGE = "Подписка. Все операторы"


def make_row(
    message_id: str,
    *,
    cost: str | None = "35.00",
    price: str | None = "35.00",
    package_type: str | None = TEMPLATED_PACKAGE,
    segments: int = 1,
    text: str = "Код 1234",
    recipient: str = "79000000000",
    delivered: bool = True,
    send_status: str = "Отправлено",
    delivery_status: str = "Успешная доставка",
) -> RawSmsRow:
    return RawSmsRow(
        message_id=message_id,
        sent_at=datetime(2026, 11, 5, 12, 0, tzinfo=MSK),
        recipient=recipient,
        operator=Operator.MTS,
        sender="TEST",
        text=text,
        segments=segments,
        cost=None if cost is None else Money.from_rub(cost),
        price_per_segment=None if price is None else Money.from_rub(price),
        package_type=package_type,
        delivered=delivered,
        send_status=send_status,
        delivery_status=delivery_status,
    )


def test_single_row_becomes_one_message() -> None:
    result = aggregate_rows([make_row("A")])

    assert len(result.messages) == 1
    assert result.issues == ()
    assert result.messages[0].cost == Money.from_rub("35.00")


def test_duplicate_rows_sum_cost_and_segments() -> None:
    rows = [
        make_row("A", cost="0.00", price="11.00", segments=1),
        make_row("A", cost="35.00", price="35.00", segments=3),
    ]

    result = aggregate_rows(rows)

    assert len(result.messages) == 1
    message = result.messages[0]
    assert message.cost == Money.from_rub("35.00")
    assert message.segments == 4
    assert len(message.billing_rows) == 2
    assert result.duplicate_message_ids == 1
    assert [issue.field for issue in result.issues] == ["segments"]


def test_statuses_take_first_non_empty_value_in_billing_group() -> None:
    rows = [
        make_row("A", send_status="", delivery_status=""),
        make_row("A", send_status="Отправлено", delivery_status="Ошибка доставки"),
    ]

    message = aggregate_rows(rows).messages[0]

    assert message.send_status == "Отправлено"
    assert message.delivery_status == "Ошибка доставки"


def test_rows_without_cost_do_not_break_total() -> None:
    result = aggregate_rows(
        [
            make_row(
                "A",
                cost=None,
                price=None,
                package_type=None,
                segments=0,
                delivered=False,
                send_status="Ошибка отправки",
            ),
        ]
    )

    message = result.messages[0]
    assert message.cost == Money.zero()
    assert message.segments == 0
    assert message.delivered is False


def test_message_class_from_package_type() -> None:
    templated = aggregate_rows([make_row("A")]).messages[0]
    ordinary = aggregate_rows([make_row("B", package_type=ORDINARY_PACKAGE)]).messages[0]

    assert templated.message_class is MessageClass.TEMPLATED
    assert ordinary.message_class is MessageClass.ORDINARY
    assert classify_message(None) is MessageClass.ORDINARY


def test_mixed_package_types_make_message_templated() -> None:
    rows = [
        make_row("A", package_type=None, cost="0.00", price=None, segments=1),
        make_row("A", package_type=TEMPLATED_PACKAGE),
    ]

    message = aggregate_rows(rows).messages[0]

    assert message.message_class is MessageClass.TEMPLATED


def test_metadata_mismatch_is_reported() -> None:
    rows = [
        make_row("A", text="Код 1234"),
        make_row("A", text="Код 9876", recipient="79000000001", delivered=False),
    ]

    result = aggregate_rows(rows)

    fields = {issue.field for issue in result.issues}
    assert fields == {"text", "recipient"}
    assert result.messages[0].delivered is True


def test_aggregation_preserves_first_appearance_order() -> None:
    result = aggregate_rows([make_row("B"), make_row("A"), make_row("B")])

    assert [message.message_id for message in result.messages] == ["B", "A"]


def test_empty_input_gives_no_messages() -> None:
    result = aggregate_rows([])

    assert result.messages == ()
    assert result.issues == ()


def test_cost_uses_decimal_exactness() -> None:
    rows = [
        make_row("A", cost="0.10"),
        make_row("A", cost="0.20"),
        make_row("A", cost="0.30"),
    ]

    total = aggregate_rows(rows).messages[0].cost

    assert total.amount == Decimal("0.60")
