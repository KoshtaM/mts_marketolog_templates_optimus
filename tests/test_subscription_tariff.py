"""Тесты подписочного тарифа."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mts_templates.domain.tariffs.models import (
    BlockMode,
    SubscriptionBlock,
    SubscriptionPlan,
)
from mts_templates.domain.value_objects import MessageClass, Money
from tests.helpers import make_message


def make_ordinary_plan(charge_per_segment: bool = False) -> SubscriptionPlan:
    return SubscriptionPlan(
        tariff_id="subscription-ordinary",
        name="Обычные SMS на всех операторов РФ",
        message_class=MessageClass.ORDINARY,
        charge_per_segment=charge_per_segment,
        blocks=(
            SubscriptionBlock(1, 5, Money.from_rub("33.00"), BlockMode.BLOCK_START),
            SubscriptionBlock(6, 20, Money.from_rub("52.00"), BlockMode.BLOCK_START),
            SubscriptionBlock(21, None, Money.from_rub("8.50"), BlockMode.PER_MESSAGE),
        ),
    )


def make_templated_plan() -> SubscriptionPlan:
    return SubscriptionPlan(
        tariff_id="subscription-templated",
        name="Шаблонированные SMS на операторов РФ",
        message_class=MessageClass.TEMPLATED,
        blocks=(
            SubscriptionBlock(1, 5, Money.from_rub("11.00"), BlockMode.BLOCK_START),
            SubscriptionBlock(6, 20, Money.from_rub("35.00"), BlockMode.BLOCK_START),
            SubscriptionBlock(21, 21, Money.from_rub("15.00"), BlockMode.PER_MESSAGE),
            SubscriptionBlock(22, None, Money.from_rub("0.00"), BlockMode.PER_MESSAGE),
        ),
    )


def test_ordinary_subscription_blocks() -> None:
    plan = make_ordinary_plan()
    messages = [make_message(str(index), hour=index) for index in range(1, 23)]

    result = plan.calculate(messages)

    # 33 (1-5) + 52 (6-20) + 8.5 * 2 (21-22)
    assert result.total.rounded().amount == Decimal("102.00")


def test_templated_subscription_blocks() -> None:
    plan = make_templated_plan()
    messages = [
        make_message(str(index), hour=index, message_class=MessageClass.TEMPLATED)
        for index in range(1, 23)
    ]

    result = plan.calculate(messages)

    # 11 (1-5) + 35 (6-20) + 15 (21) + 0 (22+)
    assert result.total.rounded().amount == Decimal("61.00")


def test_subscription_resets_per_recipient() -> None:
    plan = make_ordinary_plan()
    messages = [
        *[make_message(f"a{index}", hour=index, recipient="79000000001") for index in range(1, 7)],
        make_message("b1", hour=7, recipient="79000000002"),
    ]

    result = plan.calculate(messages)

    # 33 + 52 для первого получателя, 33 для второго
    assert result.total.rounded().amount == Decimal("118.00")


def test_subscription_resets_per_month() -> None:
    plan = make_ordinary_plan()
    messages = [
        *[make_message(f"jan{index}", month=1, hour=index) for index in range(1, 6)],
        make_message("feb1", month=2, hour=1),
    ]

    result = plan.calculate(messages)

    assert result.total.rounded().amount == Decimal("66.00")


def test_subscription_can_charge_per_segment() -> None:
    plan = make_ordinary_plan(charge_per_segment=True)
    result = plan.calculate([make_message("1", segments=2)])

    # Первый блок 33 за сообщение, но charge_per_segment умножает на 2
    assert result.total.rounded().amount == Decimal("66.00")


def test_subscription_blocks_must_be_contiguous() -> None:
    with pytest.raises(ValueError):
        SubscriptionPlan(
            tariff_id="bad",
            name="Плохие блоки",
            message_class=MessageClass.ORDINARY,
            blocks=(
                SubscriptionBlock(1, 5, Money.from_rub("33.00")),
                SubscriptionBlock(7, None, Money.from_rub("8.50")),
            ),
        )


def test_subscription_last_block_must_be_unbounded() -> None:
    with pytest.raises(ValueError):
        SubscriptionPlan(
            tariff_id="bad",
            name="Плохие блоки",
            message_class=MessageClass.ORDINARY,
            blocks=(SubscriptionBlock(1, 5, Money.from_rub("33.00")),),
        )


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (1, "33.00"),
        (5, "0.00"),
        (6, "52.00"),
        (20, "0.00"),
        (21, "8.50"),
        (22, "8.50"),
    ],
)
def test_ordinary_subscription_block_boundaries(position: int, expected: str) -> None:
    plan = make_ordinary_plan()
    messages = [make_message(str(index), hour=index) for index in range(1, position + 1)]

    result = plan.calculate(messages)

    assert result.charges[-1].cost.rounded().amount == Decimal(expected)
