"""Пакетная, подписочная модели и оплата по факту.

Фактическая стоимость уже отправленных сообщений берётся из статистики.
Эти модели нужны для прогноза и для проверки аномалий.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from itertools import pairwise

from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.errors import TariffError
from mts_templates.domain.value_objects import MessageClass, Money, Operator


class TariffKind(StrEnum):
    PACKAGE = "package"
    SUBSCRIPTION = "subscription"
    PAY_PER_MESSAGE = "pay_per_message"


class PricingMode(StrEnum):
    """Как применяются tier'ы пакета."""

    UNIFORM = "uniform"
    MARGINAL = "marginal"


class BlockMode(StrEnum):
    """Когда списывается стоимость блока подписки."""

    BLOCK_START = "block_start"
    PER_MESSAGE = "per_message"


@dataclass(frozen=True, slots=True)
class RateTier:
    """Диапазон объёма пакета и цена за SMS."""

    from_segment: int
    to_segment: int | None
    price: Money

    def __post_init__(self) -> None:
        if self.from_segment < 1:
            raise ValueError("from_segment должен быть >= 1")
        if self.to_segment is not None and self.to_segment < self.from_segment:
            raise ValueError("to_segment не может быть меньше from_segment")
        if self.price.amount < 0:
            raise ValueError("Цена не может быть отрицательной")

    def contains(self, volume: int) -> bool:
        return volume >= self.from_segment and (
            self.to_segment is None or volume <= self.to_segment
        )


@dataclass(frozen=True, slots=True)
class SubscriptionBlock:
    """Блок сообщений одному получателю."""

    from_message: int
    to_message: int | None
    price: Money
    mode: BlockMode = BlockMode.BLOCK_START

    def __post_init__(self) -> None:
        if self.from_message < 1:
            raise ValueError("from_message должен быть >= 1")
        if self.to_message is not None and self.to_message < self.from_message:
            raise ValueError("to_message не может быть меньше from_message")
        if self.price.amount < 0:
            raise ValueError("Цена не может быть отрицательной")

    def contains(self, sequence_number: int) -> bool:
        return sequence_number >= self.from_message and (
            self.to_message is None or sequence_number <= self.to_message
        )


@dataclass(frozen=True, slots=True)
class MessageCharge:
    message_id: str
    cost: Money


@dataclass(frozen=True, slots=True)
class TariffResult:
    plan_id: str
    total: Money
    charges: tuple[MessageCharge, ...]
    overage_segments: int = 0


@dataclass(frozen=True, slots=True)
class PackagePlan:
    """Предоплаченный пакет SMS.

    `calculate` моделирует расходование пакета: внутри пакета — effective rate,
    сверх пакета — overage rate. Это соответствует смыслу `Стоимость` в
    статистике, а не кассовому платежу за пакет.
    """

    tariff_id: str
    name: str
    message_class: MessageClass
    package_size: int
    pricing_mode: PricingMode
    tiers: tuple[RateTier, ...]
    overage_rates: Mapping[Operator, Money] = field(default_factory=dict)
    effective_from: date | None = None
    effective_to: date | None = None
    operator_scope: frozenset[Operator] | None = None

    @property
    def kind(self) -> TariffKind:
        return TariffKind.PACKAGE

    def __post_init__(self) -> None:
        if self.package_size < 1:
            raise ValueError("package_size должен быть >= 1")
        if not self.tiers:
            raise ValueError("Нужен хотя бы один tier")
        ordered = tuple(sorted(self.tiers, key=lambda tier: tier.from_segment))
        object.__setattr__(self, "tiers", ordered)
        if ordered[0].from_segment != 1:
            raise ValueError("Первый tier должен начинаться с 1")
        for previous, current in pairwise(ordered):
            if previous.to_segment is None:
                raise ValueError("Unbounded tier должен быть последним")
            if current.from_segment != previous.to_segment + 1:
                raise ValueError("Tier'ы не должны пересекаться или иметь разрывы")
        if self.pricing_mode is PricingMode.UNIFORM and self._tier_for(self.package_size) is None:
            raise ValueError("package_size не попадает ни в один tier")

    def _tier_for(self, volume: int) -> RateTier | None:
        return next((tier for tier in self.tiers if tier.contains(volume)), None)

    def _marginal_total(self) -> Money:
        total = Money.zero()
        for tier in self.tiers:
            upper = self.package_size
            if tier.to_segment is not None:
                upper = min(upper, tier.to_segment)
            if upper < tier.from_segment:
                continue
            count = upper - tier.from_segment + 1
            total = total + tier.price * count
        return total

    def effective_rate(self) -> Money:
        if self.pricing_mode is PricingMode.UNIFORM:
            tier = self._tier_for(self.package_size)
            if tier is None:
                raise TariffError(f"Нет tier'а для объёма пакета {self.package_size}")
            return tier.price
        return self._marginal_total() / self.package_size

    def calculate(self, messages: Sequence[SmsMessage]) -> TariffResult:
        rate = self.effective_rate()
        remaining = self.package_size
        overage_segments = 0
        charges: list[MessageCharge] = []

        for message in sorted(messages, key=lambda item: (item.sent_at, item.message_id)):
            if message.segments <= 0:
                charges.append(MessageCharge(message.message_id, Money.zero()))
                continue

            inside = min(message.segments, remaining)
            outside = message.segments - inside
            overage_rate = self.overage_rates.get(message.operator, rate)
            cost = rate * inside + overage_rate * outside

            remaining -= inside
            overage_segments += outside
            charges.append(MessageCharge(message.message_id, cost))

        total = sum((charge.cost for charge in charges), Money.zero())
        return TariffResult(
            plan_id=self.tariff_id,
            total=total,
            charges=tuple(charges),
            overage_segments=overage_segments,
        )


@dataclass(frozen=True, slots=True)
class SubscriptionPlan:
    """Подписка: блоки сообщений одному получателю за календарный месяц."""

    tariff_id: str
    name: str
    message_class: MessageClass
    blocks: tuple[SubscriptionBlock, ...]
    charge_per_segment: bool = False
    effective_from: date | None = None
    effective_to: date | None = None
    operator_scope: frozenset[Operator] | None = None

    @property
    def kind(self) -> TariffKind:
        return TariffKind.SUBSCRIPTION

    def __post_init__(self) -> None:
        if not self.blocks:
            raise ValueError("Нужен хотя бы один блок")
        ordered = tuple(sorted(self.blocks, key=lambda block: block.from_message))
        object.__setattr__(self, "blocks", ordered)
        if ordered[0].from_message != 1:
            raise ValueError("Первый блок должен начинаться с 1")
        for previous, current in pairwise(ordered):
            if previous.to_message is None:
                raise ValueError("Последний блок должен быть единственным без верхней границы")
            if current.from_message != previous.to_message + 1:
                raise ValueError("Блоки не должны пересекаться или иметь разрывы")
        if ordered[-1].to_message is not None:
            raise ValueError("Последний блок должен быть без верхней границы")

    def _block_for(self, sequence_number: int) -> SubscriptionBlock:
        block = next((item for item in self.blocks if item.contains(sequence_number)), None)
        if block is None:
            raise TariffError(f"Нет блока для сообщения №{sequence_number}")
        return block

    def calculate(self, messages: Sequence[SmsMessage]) -> TariffResult:
        counters: dict[tuple[str, int, int], int] = defaultdict(int)
        charges: list[MessageCharge] = []

        for message in sorted(messages, key=lambda item: (item.sent_at, item.message_id)):
            key = (message.recipient, message.sent_at.year, message.sent_at.month)
            counters[key] += 1
            sequence_number = counters[key]
            block = self._block_for(sequence_number)

            if block.mode is BlockMode.BLOCK_START:
                cost = block.price if sequence_number == block.from_message else Money.zero()
            else:
                cost = block.price

            if self.charge_per_segment and message.segments > 0:
                cost = cost * message.segments

            charges.append(MessageCharge(message.message_id, cost))

        total = sum((charge.cost for charge in charges), Money.zero())
        return TariffResult(plan_id=self.tariff_id, total=total, charges=tuple(charges))


@dataclass(frozen=True, slots=True)
class PayPerMessagePlan:
    """Оплата по факту: фиксированная цена за SMS-сегмент."""

    tariff_id: str
    name: str
    message_class: MessageClass
    rates: Mapping[Operator, Money]
    default_rate: Money | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    operator_scope: frozenset[Operator] | None = None

    @property
    def kind(self) -> TariffKind:
        return TariffKind.PAY_PER_MESSAGE

    def rate_for(self, operator: Operator) -> Money:
        rate = self.rates.get(operator, self.default_rate)
        if rate is None:
            raise TariffError(f"Нет ставки для оператора {operator}")
        return rate

    def calculate(self, messages: Sequence[SmsMessage]) -> TariffResult:
        charges = tuple(
            MessageCharge(message.message_id, self.rate_for(message.operator) * message.segments)
            for message in sorted(messages, key=lambda item: (item.sent_at, item.message_id))
        )
        total = sum((charge.cost for charge in charges), Money.zero())
        return TariffResult(plan_id=self.tariff_id, total=total, charges=charges)


type TariffPlan = PackagePlan | SubscriptionPlan | PayPerMessagePlan


@dataclass(frozen=True, slots=True)
class TariffCatalog:
    """Набор тарифов с выбором по дате, классу и оператору."""

    plans: tuple[TariffPlan, ...]

    def resolve(
        self,
        *,
        day: date,
        message_class: MessageClass,
        operator: Operator,
        kind: TariffKind | None = None,
    ) -> TariffPlan:
        candidates: list[TariffPlan] = []
        for plan in self.plans:
            if plan.message_class is not message_class:
                continue
            if kind is not None and plan.kind is not kind:
                continue
            if plan.effective_from is not None and day < plan.effective_from:
                continue
            if plan.effective_to is not None and day > plan.effective_to:
                continue
            if plan.operator_scope is not None and operator not in plan.operator_scope:
                continue
            candidates.append(plan)

        if not candidates:
            raise TariffError(
                f"Нет тарифа: day={day}, class={message_class}, operator={operator}, kind={kind}"
            )
        return max(
            candidates,
            key=lambda plan: (
                plan.effective_from or date.min,
                -(len(plan.operator_scope) if plan.operator_scope is not None else 10**6),
            ),
        )
