"""Активность шаблонов и метрики за период."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator


@dataclass(frozen=True, slots=True)
class OperatorTrigger:
    """Сообщения, подпавшие под шаблон, у одного оператора получателя."""

    template_id: str
    operator: Operator
    listed: bool
    matched_messages: int
    triggered_messages: int
    matched_segments: int = 0


@dataclass(frozen=True, slots=True)
class TemplateMetrics:
    """Метрики одного шаблона за период.

    `matched_messages` — сообщения, подпавшие под шаблон по тексту и отправителю.
    `triggered_messages` — из них оплаченные по тарифу шаблонированных SMS.
    `trigger_rate` = `triggered_messages / matched_messages`.
    """

    template_id: str
    matched_messages: int
    matched_segments: int
    delivered_messages: int
    unique_recipients: int
    triggered_messages: int
    off_operator_messages: int
    actual_cost: Money
    baseline_cost: Money
    template_fee: Money
    net_benefit: Money
    trigger_rate: Decimal
    active: bool


@dataclass(slots=True)
class _OperatorCounts:
    listed: bool
    matched: int = 0
    matched_segments: int = 0
    triggered: int = 0


@dataclass(slots=True)
class TemplateActivity:
    """Накопитель метрик шаблона во время потокового прохода по сообщениям.

    Стоимость и baseline — только по срабатываниям (оплата по тарифу шаблонированных SMS).
    """

    template_id: str
    matched_messages: int = 0
    matched_segments: int = 0
    delivered_messages: int = 0
    triggered_messages: int = 0
    off_operator_messages: int = 0
    actual_cost: Money = field(default_factory=Money.zero)
    baseline_cost: Money = field(default_factory=Money.zero)
    recipients: set[str] = field(default_factory=set)
    by_operator: dict[Operator, _OperatorCounts] = field(default_factory=dict)

    def add(self, message: SmsMessage, baseline_cost: Money, *, operator_listed: bool) -> None:
        triggered = message.message_class is MessageClass.TEMPLATED
        self.matched_messages += 1
        self.matched_segments += message.segments
        self.delivered_messages += int(message.delivered)
        self.recipients.add(message.recipient)
        if not operator_listed:
            self.off_operator_messages += 1

        counts = self.by_operator.setdefault(
            message.operator, _OperatorCounts(listed=operator_listed)
        )
        counts.matched += 1
        counts.matched_segments += message.segments
        if triggered:
            counts.triggered += 1
            self.triggered_messages += 1
            self.actual_cost = self.actual_cost + message.cost
            self.baseline_cost = self.baseline_cost + baseline_cost

    def operator_triggers(self) -> tuple[OperatorTrigger, ...]:
        return tuple(
            OperatorTrigger(
                template_id=self.template_id,
                operator=operator,
                listed=counts.listed,
                matched_messages=counts.matched,
                triggered_messages=counts.triggered,
                matched_segments=counts.matched_segments,
            )
            for operator, counts in sorted(self.by_operator.items(), key=lambda item: item[0].value)
        )

    def to_metrics(self, *, monthly_fee: Money, months: int = 1) -> TemplateMetrics:
        if months < 1:
            raise ValueError("months должен быть >= 1")

        fee = monthly_fee * months
        active = self.matched_messages > 0
        trigger_rate = (
            Decimal(self.triggered_messages) / Decimal(self.matched_messages)
            if active
            else Decimal("0")
        )
        net_benefit = self.baseline_cost - self.actual_cost - fee if active else -fee
        return TemplateMetrics(
            template_id=self.template_id,
            matched_messages=self.matched_messages,
            matched_segments=self.matched_segments,
            delivered_messages=self.delivered_messages,
            unique_recipients=len(self.recipients),
            triggered_messages=self.triggered_messages,
            off_operator_messages=self.off_operator_messages,
            actual_cost=self.actual_cost,
            baseline_cost=self.baseline_cost if active else Money.zero(),
            template_fee=fee,
            net_benefit=net_benefit,
            trigger_rate=trigger_rate,
            active=active,
        )
