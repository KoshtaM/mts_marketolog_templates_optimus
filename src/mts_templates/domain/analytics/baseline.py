"""Базовая стоимость: наблюдаемые и каталожные ставки.

Baseline — сколько стоила бы отправка тех же сообщений по обычному тарифу.
По умолчанию — средняя стоимость сегмента обычных SMS периода, умноженная на
сегменты срабатываний. Средняя стоимость сегмента считается по всем сообщениям
класса (включая нулевые списания внутри оплаченного блока), поэтому совпадает
с показателем дашборда «Средняя стоимость сегмента».
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator

MAX_SEGMENT_BUCKET = 3


def segment_bucket(segments: int) -> int:
    """Схлопнуть сегменты в бакет, чтобы не мельчить статистику."""
    return min(max(segments, 1), MAX_SEGMENT_BUCKET)


@dataclass(frozen=True, slots=True)
class ObservedRates:
    """Эффективные ставки за SMS-сегмент, извлечённые из фактических данных."""

    rates: Mapping[tuple[MessageClass, Operator, int], Money]
    class_rates: Mapping[MessageClass, Money]

    def rate_for(self, operator: Operator, segments: int) -> Money | None:
        """Ставка обычного сообщения: класс+оператор+бакет → класс целиком."""
        return self.rate_for_class(MessageClass.ORDINARY, operator, segments)

    def rate_for_class(
        self, message_class: MessageClass, operator: Operator, segments: int
    ) -> Money | None:
        exact = self.rates.get((message_class, operator, segment_bucket(segments)))
        if exact is not None:
            return exact
        return self.class_rates.get(message_class)

    def average_for(self, message_class: MessageClass) -> Money | None:
        """Средняя стоимость сегмента класса по всем сообщениям периода."""
        return self.class_rates.get(message_class)


def build_observed_rates(messages: Iterable[SmsMessage]) -> ObservedRates:
    """Посчитать эффективные ставки из фактических данных.

    `rates` — ставки по парам «оператор + бакет сегментов» для доставленных
    сообщений с ненулевой стоимостью (нужны для каталожного режима и fallback).
    `class_rates` — средняя стоимость сегмента класса по всем сообщениям с
    сегментами: это и есть значение дашборда «Средняя стоимость сегмента».
    """
    totals: dict[tuple[MessageClass, Operator, int], tuple[Money, int]] = defaultdict(
        lambda: (Money.zero(), 0)
    )
    class_totals: dict[MessageClass, tuple[Money, int]] = defaultdict(lambda: (Money.zero(), 0))

    for message in messages:
        if message.segments <= 0:
            continue
        class_cost, class_segments = class_totals[message.message_class]
        class_totals[message.message_class] = (
            class_cost + message.cost,
            class_segments + message.segments,
        )
        if not message.delivered or message.cost.amount <= 0:
            continue
        key = (message.message_class, message.operator, segment_bucket(message.segments))
        cost, segments = totals[key]
        totals[key] = (cost + message.cost, segments + message.segments)

    rates = {key: cost / segments for key, (cost, segments) in totals.items() if segments > 0}
    class_rates = {
        message_class: cost / segments
        for message_class, (cost, segments) in class_totals.items()
        if segments > 0
    }
    return ObservedRates(rates=rates, class_rates=class_rates)
