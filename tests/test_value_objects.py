"""Тесты value objects."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mts_templates.domain.value_objects import Money, Operator


def test_money_adds_and_rounds_half_up() -> None:
    assert (Money.from_rub("10.005").rounded()).amount == Decimal("10.01")
    assert (Money.from_rub("10.004").rounded()).amount == Decimal("10.00")


def test_money_arithmetic() -> None:
    assert Money.from_rub("10.50") + Money.from_rub("2.25") == Money.from_rub("12.75")
    assert Money.from_rub("10.50") - Money.from_rub("2.25") == Money.from_rub("8.25")
    assert Money.from_rub("10.50") * 2 == Money.from_rub("21.00")
    assert Money.from_rub("10.50") / 2 == Money.from_rub("5.25")
    assert -Money.from_rub("10.50") == Money.from_rub("-10.50")


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]


def test_money_division_by_zero() -> None:
    with pytest.raises(ZeroDivisionError):
        Money.from_rub("10") / 0


def test_operator_normalization() -> None:
    assert Operator.from_raw("MTS") is Operator.MTS
    assert Operator.from_raw("megafon") is Operator.MEGAFON
    assert Operator.from_raw(" t2 ") is Operator.T2
    assert Operator.from_raw("Tele2") is Operator.T2
    assert Operator.from_raw("unknown-operator") is Operator.UNKNOWN
    assert Operator.from_raw(None) is Operator.UNKNOWN
