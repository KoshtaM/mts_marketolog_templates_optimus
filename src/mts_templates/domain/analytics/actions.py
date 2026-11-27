"""Центр действий: рабочий список потерь и проблем анализа.

Сервис отвечает на вопрос «где мы теряем деньги и что сделать первым».
Каждый пункт несёт сумму в рублях за месяц (та же месячная модель, что у
кандидатов), объём сообщений и переход к реальным сообщениям.

Потери считаются только по наблюдаемым ставкам периода и никогда не
пересчитываются из прайс-листа: если ставки шаблонированных SMS нет,
денежная оценка не выдумывается.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from mts_templates.domain.analytics.activity import OperatorTrigger, TemplateMetrics
from mts_templates.domain.analytics.analysis import (
    AnalysisRun,
    CandidateGroup,
    monthly_factor,
    monthly_net_benefit,
)
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money, Period

HIGH_LOSS = Money.from_rub("10000")
MEDIUM_LOSS = Money.from_rub("3000")
# Убыток попадает в центр действий, только если он больше четверти стоимости
# шаблона: мелкие колебания выгоды не стоят отдельного пункта рабочего списка.
LOSS_FEE_SHARE = Decimal("0.25")
# Рекомендация «Удалить»/«Добавить» выдаётся, только когда эффект превышает
# три четверти ежемесячной стоимости шаблона.
ACTION_FEE_SHARE = Decimal("0.75")


class Action(StrEnum):
    """Рекомендуемое действие: удалить шаблон или добавить кандидат."""

    DELETE = "delete"
    ADD = "add"


class ActionKind(StrEnum):
    """Тип пункта в центре действий."""

    LOSS_TEMPLATE = "loss_template"
    UNWORKING_TEMPLATE = "unworking_template"
    PROFITABLE_CANDIDATE = "profitable_candidate"
    UNTRIGGERED = "untriggered"
    UNMATCHED_TEMPLATED = "unmatched_templated"


class DrillDown(StrEnum):
    """Куда ведёт переход из пункта центра действий."""

    TEMPLATE = "template"
    UNMATCHED_TEMPLATED = "unmatched_templated"


@dataclass(frozen=True, slots=True)
class ActionItem:
    """Пункт списка: проблема или возможность с денежной оценкой и действием."""

    key: str
    kind: ActionKind
    severity: int
    title: str
    subject: str
    detail: str
    recommendation: str
    monthly_loss: Money
    messages: int
    segments: int
    template_id: str | None = None
    template_name: str = ""
    operator: str | None = None
    drill_down: DrillDown | None = None
    action: Action | None = None
    monthly_benefit: Money = field(default_factory=Money.zero)

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key пункта центра действий обязателен")
        if not 0 <= self.severity <= 3:
            raise ValueError("severity должен быть в диапазоне 0..3")
        if self.messages < 0 or self.segments < 0:
            raise ValueError("Объёмы пункта центра действий не могут быть отрицательными")


@dataclass(frozen=True, slots=True)
class ActionCenter:
    """Готовый рабочий список проблем и возможностей за период загрузки."""

    period: Period
    monthly_factor: Decimal
    items: tuple[ActionItem, ...]
    observed_ordinary_rate: Money | None
    observed_templated_rate: Money | None
    unmatched_templated_messages: int
    unmatched_templated_segments: int
    unmatched_templated_cost: Money
    warnings: tuple[str, ...] = ()
    loss_templates: int = 0
    profitable_candidates: int = 0

    @property
    def total_monthly_loss(self) -> Money:
        return sum((item.monthly_loss for item in self.items), Money.zero())

    @property
    def total_monthly_benefit(self) -> Money:
        return sum((item.monthly_benefit for item in self.items), Money.zero())

    @property
    def untriggered_loss(self) -> Money:
        return _kind_total(self.items, ActionKind.UNTRIGGERED)

    @property
    def untriggered_messages(self) -> int:
        return _kind_messages(self.items, ActionKind.UNTRIGGERED)


def _kind_total(items: Sequence[ActionItem], kind: ActionKind) -> Money:
    return sum((item.monthly_loss for item in items if item.kind is kind), Money.zero())


def _kind_messages(items: Sequence[ActionItem], kind: ActionKind) -> int:
    return sum(item.messages for item in items if item.kind is kind)


def build_action_center(
    run: AnalysisRun,
    templates: Sequence[SmsTemplate],
) -> ActionCenter:
    """Собрать центр действий по прогону анализа и набору шаблонов."""
    by_id = {template.template_id: template for template in templates}
    factor = monthly_factor(run.period)
    warnings: list[str] = []
    items: list[ActionItem] = []

    items.extend(_template_items(run.metrics, by_id, factor))
    operator_items = _operator_items(run.operator_triggers, by_id, run, factor)
    items.extend(operator_items)
    items.extend(_candidate_items(run.candidates))
    unmatched = _unmatched_templated_item(run, factor)
    if unmatched is not None:
        items.append(unmatched)

    if _has_unpriced_losses(operator_items) and run.observed_templated_rate is None:
        warnings.append(
            "Нет наблюдаемой ставки шаблонированных SMS: денежная оценка потерь "
            "срабатывания не рассчитана. Показаны только объёмы сообщений."
        )

    items.sort(key=lambda item: (-_item_impact(item).amount, item.kind.value, item.key))
    return ActionCenter(
        period=run.period,
        monthly_factor=factor,
        items=tuple(items),
        observed_ordinary_rate=run.observed_ordinary_rate,
        observed_templated_rate=run.observed_templated_rate,
        unmatched_templated_messages=run.unmatched_templated_messages,
        unmatched_templated_segments=run.unmatched_templated_segments,
        unmatched_templated_cost=run.unmatched_templated_cost,
        warnings=tuple(warnings),
        loss_templates=sum(
            1
            for item in items
            if item.kind in (ActionKind.LOSS_TEMPLATE, ActionKind.UNWORKING_TEMPLATE)
        ),
        profitable_candidates=sum(
            1 for item in items if item.kind is ActionKind.PROFITABLE_CANDIDATE
        ),
    )


def _template_items(
    metrics: Sequence[TemplateMetrics],
    by_id: Mapping[str, SmsTemplate],
    factor: Decimal,
) -> list[ActionItem]:
    items: list[ActionItem] = []
    for item in metrics:
        template = by_id.get(item.template_id)
        subject = template.text if template is not None else item.template_id
        name = template.name if template is not None else item.template_id
        if item.triggered_messages == 0:
            items.append(_unworking_item(item, subject, name))
            continue
        loss = _monthly_loss(item, factor)
        if not _exceeds_fee_share(loss, item.template_fee):
            continue
        detail = (
            f"Выгода {_money_text(monthly_net_benefit(item, factor))}/мес при "
            f"стоимости шаблона {_money_text(item.template_fee)}/мес и срабатывании "
            f"{_percent(item.trigger_rate)}."
        )
        delete = loss.amount > item.template_fee.amount * ACTION_FEE_SHARE
        items.append(
            ActionItem(
                key=f"loss:{item.template_id}",
                kind=ActionKind.LOSS_TEMPLATE,
                severity=_severity(loss),
                title="Убыточный шаблон",
                subject=subject,
                template_id=item.template_id,
                template_name=name,
                detail=detail,
                recommendation=(
                    "Удалить шаблон: ежемесячная плата почти не окупается экономией на сегментах."
                    if delete
                    else "Отключить шаблон или пересмотреть его необходимость: "
                    "ежемесячная плата выше экономии на сегментах."
                ),
                monthly_loss=loss,
                messages=item.matched_messages,
                segments=item.matched_segments,
                drill_down=DrillDown.TEMPLATE,
                action=Action.DELETE if delete else None,
                monthly_benefit=loss if delete else Money.zero(),
            )
        )
    return items


def _unworking_item(
    metrics: TemplateMetrics,
    subject: str,
    name: str,
) -> ActionItem:
    """Шаблон без единого срабатывания: плата расходуется впустую."""
    if metrics.matched_messages > 0:
        detail = (
            f"{metrics.matched_messages} сообщений подпали под шаблон, но ни одно "
            f"не оплачено как шаблонированное. Плата "
            f"{_money_text(metrics.template_fee)}/мес расходуется впустую."
        )
    else:
        detail = (
            "Ни одно сообщение не подпало под шаблон. "
            f"Плата {_money_text(metrics.template_fee)}/мес расходуется впустую."
        )
    loss = metrics.template_fee
    return ActionItem(
        key=f"unworking:{metrics.template_id}",
        kind=ActionKind.UNWORKING_TEMPLATE,
        severity=_severity(loss) if loss.amount > 0 else 0,
        title="Неработающий",
        subject=subject,
        template_id=metrics.template_id,
        template_name=name,
        detail=detail,
        recommendation=(
            "Удалить шаблон: пока нет срабатываний, ежемесячная плата расходуется "
            "впустую. Перед удалением можно проверить регистрацию, отправителя и текст."
        ),
        monthly_loss=loss,
        messages=metrics.matched_messages,
        segments=metrics.matched_segments,
        drill_down=DrillDown.TEMPLATE,
        action=Action.DELETE,
        monthly_benefit=loss,
    )


def _operator_items(
    triggers: Sequence[OperatorTrigger],
    by_id: Mapping[str, SmsTemplate],
    run: AnalysisRun,
    factor: Decimal,
) -> list[ActionItem]:
    items: list[ActionItem] = []
    for trigger in triggers:
        if not trigger.listed:
            # Операторы вне списка шаблона пока не попадают в центр действий:
            # там нужны дополнительные проверки региона и тарификации.
            continue
        if trigger.untriggered_segments <= 0 and trigger.untriggered_messages <= 0:
            continue
        loss = _loss_estimate(
            trigger.untriggered_cost,
            trigger.untriggered_segments,
            run.observed_templated_rate,
            factor,
        )
        template = by_id.get(trigger.template_id)
        subject = template.text if template is not None else trigger.template_id
        name = template.name if template is not None else trigger.template_id
        items.append(
            ActionItem(
                key=f"untrig:{trigger.template_id}:{trigger.operator.value}",
                kind=ActionKind.UNTRIGGERED,
                severity=_severity(loss),
                title="Срабатывание ниже 100 %",
                subject=subject,
                template_id=trigger.template_id,
                template_name=name,
                operator=trigger.operator.value,
                detail=(
                    f"{trigger.untriggered_messages} сообщений подпали под шаблон и оплачены "
                    f"как обычные, хотя оператор {trigger.operator.value} указан в шаблоне. "
                    "Причина — в регистрации шаблона или определении оператора получателя."
                ),
                recommendation=(
                    "Проверить регистрацию шаблона у оператора и корректность определения "
                    "оператора получателя в выгрузке."
                ),
                monthly_loss=loss,
                messages=trigger.untriggered_messages,
                segments=trigger.untriggered_segments,
                drill_down=DrillDown.TEMPLATE,
            )
        )
    return items


def _candidate_items(candidates: Sequence[CandidateGroup]) -> list[ActionItem]:
    """Выгодные кандидаты: возможность добавить новый шаблон."""
    items: list[ActionItem] = []
    for candidate in candidates:
        if candidate.net_monthly.amount <= candidate.template_fee.amount * ACTION_FEE_SHARE:
            continue
        detail = (
            f"Экономия {_money_text(candidate.monthly_saving)}/мес за вычетом платы "
            f"{_money_text(candidate.template_fee)}/мес даёт "
            f"{_money_text(candidate.net_monthly)}/мес. Сообщений — {candidate.messages}, "
            f"сегментов — {candidate.segments}, уверенность — {_percent(candidate.confidence)}."
        )
        items.append(
            ActionItem(
                key=f"candidate:{candidate.candidate_id}",
                kind=ActionKind.PROFITABLE_CANDIDATE,
                severity=_severity(candidate.net_monthly),
                title="Выгодный кандидат",
                subject=candidate.template_text,
                detail=detail,
                recommendation=(
                    "Проверить текст кандидата и зарегистрировать новый шаблон: "
                    "месячная выгода превышает стоимость шаблона более чем на 75 %."
                ),
                monthly_loss=Money.zero(),
                monthly_benefit=candidate.net_monthly,
                messages=candidate.messages,
                segments=candidate.segments,
                action=Action.ADD,
            )
        )
    return items


def _unmatched_templated_item(run: AnalysisRun, factor: Decimal) -> ActionItem | None:
    if run.unmatched_templated_messages <= 0:
        return None
    detail = (
        f"{run.unmatched_templated_messages} сообщений ({run.unmatched_templated_segments} "
        f"сегментов) оплачены как шаблонированные, но не сопоставились ни с одним "
        f"зарегистрированным шаблоном. Оплачено за период: {_money_text(run.unmatched_templated_cost)}."
    )
    return ActionItem(
        key="unmatched_templated",
        kind=ActionKind.UNMATCHED_TEMPLATED,
        severity=0,
        title="Шаблонировано без шаблона",
        subject="Сообщения без зарегистрированного шаблона",
        detail=detail,
        recommendation=(
            "Проверить, что шаблон зарегистрирован и совпадают имя отправителя и текст: "
            "иначе расходы идут мимо управляемого портфеля шаблонов."
        ),
        monthly_loss=Money.zero(),
        messages=run.unmatched_templated_messages,
        segments=run.unmatched_templated_segments,
        drill_down=DrillDown.UNMATCHED_TEMPLATED,
    )


def _monthly_loss(metrics: TemplateMetrics, factor: Decimal) -> Money:
    """Убыток шаблона в месяц как положительная величина экономии при отключении."""
    net = monthly_net_benefit(metrics, factor)
    return -net if net.amount < 0 else Money.zero()


def _exceeds_fee_share(loss: Money, fee: Money) -> bool:
    """Убыток значим, если больше четверти ежемесячной стоимости шаблона."""
    return loss.amount > fee.amount * LOSS_FEE_SHARE


def _item_impact(item: ActionItem) -> Money:
    """Денежный эффект пункта для сортировки: потеря или выгода действия."""
    return max(item.monthly_benefit, item.monthly_loss, key=lambda value: value.amount)


def _loss_estimate(
    actual_cost: Money,
    segments: int,
    templated_rate: Money | None,
    factor: Decimal,
) -> Money:
    """Потери периода: обычная стоимость минус оценка по шаблонной ставке.

    Оценка ограничена снизу нулём: если фактически заплатили меньше шаблонной
    ставки, потери нет. Месячная модель — та же, что у кандидатов.
    """
    if segments <= 0:
        return Money.zero()
    if templated_rate is None:
        return Money.zero()
    saving = actual_cost - templated_rate * segments
    if saving.amount <= 0:
        return Money.zero()
    return saving * factor


def _has_unpriced_losses(items: Sequence[ActionItem]) -> bool:
    return any(
        item.kind is ActionKind.UNTRIGGERED and item.segments > 0 and item.monthly_loss.amount == 0
        for item in items
    )


def _severity(value: Money) -> int:
    if value.amount >= HIGH_LOSS.amount:
        return 3
    if value.amount >= MEDIUM_LOSS.amount:
        return 2
    return 1


def _money_text(value: Money) -> str:
    return f"{value.rounded().amount:.2f} ₽"


def _percent(value: Decimal) -> str:
    return f"{value * 100:.1f} %"
