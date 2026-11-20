"""Форматирование значений для UI. Деньги и даты форматируются только здесь."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from mts_templates.domain.value_objects import Money, Operator

OPERATOR_ORDER = (
    Operator.MTS.value,
    Operator.MEGAFON.value,
    Operator.BEELINE.value,
    Operator.T2.value,
    Operator.ROSTELECOM.value,
    Operator.SBERTELECOM.value,
    Operator.SMARTS_MOTIV.value,
    Operator.OTHER_RF.value,
    Operator.INTERNATIONAL.value,
    Operator.UNKNOWN.value,
)
OPERATOR_SHORT_NAMES = {
    Operator.MTS.value: "МТС",
    Operator.MEGAFON.value: "МегаФон",
    Operator.BEELINE.value: "Билайн",
    Operator.T2.value: "Tele2",
    Operator.ROSTELECOM.value: "Ростелеком",
    Operator.SBERTELECOM.value: "СберТел",
    Operator.SMARTS_MOTIV.value: "Смартс",
    Operator.OTHER_RF.value: "Др. РФ",
    Operator.INTERNATIONAL.value: "Межд.",
    Operator.UNKNOWN.value: "Неизв.",
}


def format_money(money: Money | None) -> str:
    if money is None:
        return "—"
    return f"{money.rounded().amount:,.2f} ₽".replace(",", " ")


def format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def format_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def format_date(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y")


def format_period(start: datetime | None, end: datetime | None) -> str:
    if start is None or end is None:
        return "—"
    return f"{format_date(start)} — {format_date(end)}"


def format_average_segments(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f} сегм."


def format_operators(operators: Sequence[str]) -> str:
    """Компактный список операторов шаблона; пустой список — «все»."""
    if not operators:
        return "все"

    def order(name: str) -> tuple[int, str]:
        if name in OPERATOR_ORDER:
            return OPERATOR_ORDER.index(name), name
        return len(OPERATOR_ORDER), name

    ordered = sorted(operators, key=order)
    return ", ".join(OPERATOR_SHORT_NAMES.get(name, name) for name in ordered)


def format_average(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def format_bool_icon(value: bool) -> str:
    """Галочка вместо «да» и крестик вместо «нет»; цвет задаёт модель таблицы."""
    return "✔" if value else "✘"
