"""Доменные value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

KOPECK = Decimal("0.01")


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """Денежная сумма в рублях. Внутри — Decimal, без float."""

    amount: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Money не принимает float: используйте Decimal или str")
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal("0"))

    @classmethod
    def from_rub(cls, value: str | int | Decimal) -> Money:
        return cls(Decimal(str(value)))

    def rounded(self) -> Money:
        return Money(self.amount.quantize(KOPECK, rounding=ROUND_HALF_UP))

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount - other.amount)

    def __neg__(self) -> Money:
        return Money(-self.amount)

    def __mul__(self, factor: int | Decimal) -> Money:
        if isinstance(factor, float):
            raise TypeError("Money не умножается на float")
        return Money(self.amount * Decimal(factor))

    def __truediv__(self, divisor: int | Decimal) -> Money:
        if isinstance(divisor, float):
            raise TypeError("Money не делится на float")
        if divisor == 0:
            raise ZeroDivisionError("Деление Money на ноль")
        return Money(self.amount / Decimal(divisor))

    def __str__(self) -> str:
        return f"{self.rounded().amount:.2f}"


class Operator(StrEnum):
    """Оператор получателя в терминах выгрузки МТС."""

    MTS = "MTS"
    MEGAFON = "Megafon"
    BEELINE = "Beeline"
    T2 = "Tele2"
    OTHER_RF = "Other_RF"
    ROSTELECOM = "Rostelecom"
    SBERTELECOM = "Sbertelecom"
    SMARTS_MOTIV = "Smarts_motiv"
    INTERNATIONAL = "International"
    UNKNOWN = "Unknown"

    @classmethod
    def from_raw(cls, value: str | None) -> Operator:
        if not value:
            return cls.UNKNOWN
        mapping = {
            "mts": cls.MTS,
            "megafon": cls.MEGAFON,
            "beeline": cls.BEELINE,
            "tele2": cls.T2,
            "t2": cls.T2,
            "т2": cls.T2,
            "теле2": cls.T2,
            "мтс": cls.MTS,
            "мегафон": cls.MEGAFON,
            "билайн": cls.BEELINE,
            "ростелеком": cls.ROSTELECOM,
            "сбертелеком": cls.SBERTELECOM,
            "other_rf": cls.OTHER_RF,
            "rostelecom": cls.ROSTELECOM,
            "sbertelecom": cls.SBERTELECOM,
            "smarts_motiv": cls.SMARTS_MOTIV,
            "international": cls.INTERNATIONAL,
        }
        return mapping.get(value.strip().casefold(), cls.UNKNOWN)


class MessageClass(StrEnum):
    """Класс сообщения: обычное или шаблонированное."""

    ORDINARY = "ordinary"
    TEMPLATED = "templated"


@dataclass(frozen=True, slots=True)
class Period:
    """Интервал времени с часовым поясом включительно."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Границы периода должны быть timezone-aware")
        if self.end < self.start:
            raise ValueError("Конец периода не может быть раньше начала")

    @property
    def days(self) -> int:
        return max((self.end.date() - self.start.date()).days + 1, 1)

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end
