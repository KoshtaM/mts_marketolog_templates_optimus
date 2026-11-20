"""Расчёт экономической выгоды шаблонов и кандидатов."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from mts_templates.domain.value_objects import Money


@dataclass(frozen=True, slots=True)
class TemplateBenefit:
    """Выгода зарегистрированного шаблона."""

    active: bool
    actual_message_cost: Money
    template_fee: Money
    baseline_cost: Money
    net_benefit: Money


@dataclass(frozen=True, slots=True)
class CandidateBenefit:
    """Прогноз выгоды для шаблона-кандидата."""

    monthly_saving: Money
    template_fee: Money
    net_monthly: Money
    payback_months: Decimal | None
    break_even_messages: int | None


def calculate_template_benefit(
    *,
    actual_message_cost: Money,
    baseline_cost: Money,
    template_fee: Money,
    months: int = 1,
    active: bool = True,
) -> TemplateBenefit:
    """Выгода шаблона за период.

    Для неактивного шаблона сообщений нет: baseline = 0, убыток равен
    стоимости поддержания шаблона.
    """
    if months < 1:
        raise ValueError("months должен быть >= 1")

    fee = template_fee * months
    if not active:
        return TemplateBenefit(
            active=False,
            actual_message_cost=Money.zero(),
            template_fee=fee,
            baseline_cost=Money.zero(),
            net_benefit=Money.zero() - fee,
        )

    actual = actual_message_cost + fee
    return TemplateBenefit(
        active=True,
        actual_message_cost=actual_message_cost,
        template_fee=fee,
        baseline_cost=baseline_cost,
        net_benefit=baseline_cost - actual,
    )


def calculate_candidate_benefit(
    *,
    ordinary_cost_per_message: Money,
    templated_cost_per_message: Money,
    monthly_messages: int,
    template_fee: Money,
) -> CandidateBenefit:
    """Прогноз выгоды от регистрации шаблона."""
    if monthly_messages < 0:
        raise ValueError("monthly_messages не может быть отрицательным")

    saving_per_message = ordinary_cost_per_message - templated_cost_per_message
    monthly_saving = saving_per_message * monthly_messages
    net_monthly = monthly_saving - template_fee

    if saving_per_message.amount <= 0:
        return CandidateBenefit(
            monthly_saving=monthly_saving,
            template_fee=template_fee,
            net_monthly=net_monthly,
            payback_months=None,
            break_even_messages=None,
        )

    payback = template_fee.amount / saving_per_message.amount
    break_even = int(
        (template_fee.amount / saving_per_message.amount).quantize(
            Decimal("1"), rounding=ROUND_CEILING
        )
    )
    return CandidateBenefit(
        monthly_saving=monthly_saving,
        template_fee=template_fee,
        net_monthly=net_monthly,
        payback_months=payback,
        break_even_messages=break_even,
    )
