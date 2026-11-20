"""Тесты оплаты по факту."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mts_templates.domain.errors import TariffError
from mts_templates.domain.tariffs.models import PayPerMessagePlan
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from tests.helpers import make_message


def make_plan() -> PayPerMessagePlan:
    return PayPerMessagePlan(
        tariff_id="pay-per-message",
        name="Оплата по факту",
        message_class=MessageClass.ORDINARY,
        rates={
            Operator.MTS: Money.from_rub("7.54"),
            Operator.MEGAFON: Money.from_rub("31.90"),
        },
    )


def test_pay_per_message_multiplies_by_segments() -> None:
    plan = make_plan()
    messages = [
        make_message("1", segments=1),
        make_message("2", segments=2),
        make_message("3", segments=1),
    ]

    result = plan.calculate(messages)

    assert result.total.rounded().amount == Decimal("30.16")


def test_pay_per_message_default_rate() -> None:
    plan = PayPerMessagePlan(
        tariff_id="pay-per-message-default",
        name="Оплата по факту",
        message_class=MessageClass.ORDINARY,
        rates={},
        default_rate=Money.from_rub("7.70"),
    )

    result = plan.calculate([make_message("1", operator=Operator.UNKNOWN)])

    assert result.total.rounded().amount == Decimal("7.70")


def test_pay_per_message_unknown_operator() -> None:
    with pytest.raises(TariffError):
        make_plan().calculate([make_message("1", operator=Operator.UNKNOWN)])
