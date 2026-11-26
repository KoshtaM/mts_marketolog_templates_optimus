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
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from mts_templates.domain.analytics.activity import OperatorTrigger, TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun, monthly_factor, monthly_net_benefit
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money, Period

HIGH_LOSS = Money.from_rub("10000")
MEDIUM_LOSS = Money.from_rub("3000")


class ActionKind(StrEnum):
    """Тип проблемы в центре действий."""

    LOSS_TEMPLATE = "loss_template"
    OFF_OPERATOR = "off_operator"
    UNTRIGGERED = "untriggered"
    UNMATCHED_TEMPLATED = "unmatched_templated"


class DrillDown(StrEnum):
    """Куда ведёт переход из пункта центра действий."""

    TEMPLATE = "template"
    UNMATCHED_TEMPLATED = "unmatched_templated"


@dataclass(frozen=True, slots=True)
class ActionItem:
    """Одна проблема с денежной оценкой и рекомендацией."""

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

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key пункта центра действий обязателен")
        if not 0 <= self.severity <= 3:
            raise ValueError("severity должен быть в диапазоне 0..3")
        if self.messages < 0 or self.segments < 0:
            raise ValueError("Объёмы пункта центра действий не могут быть отрицательными")


@dataclass(frozen=True, slots=True)
class ActionCenter:
    """Готовый рабочий список проблем за период загрузки."""

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

    @property
    def total_monthly_loss(self) -> Money:
        return sum((item.monthly_loss for item in self.items), Money.zero())

    @property
    def off_operator_loss(self) -> Money:
        return _kind_total(self.items, ActionKind.OFF_OPERATOR)

    @property
    def untriggered_loss(self) -> Money:
        return _kind_total(self.items, ActionKind.UNTRIGGERED)

    @property
    def off_operator_messages(self) -> int:
        return _kind_messages(self.items, ActionKind.OFF_OPERATOR)

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

    items.extend(_loss_template_items(run.metrics, by_id, factor))
    operator_items = _operator_items(run.operator_triggers, by_id, run, factor)
    items.extend(operator_items)
    unmatched = _unmatched_templated_item(run, factor)
    if unmatched is not None:
        items.append(unmatched)

    if _has_unpriced_losses(operator_items) and run.observed_templated_rate is None:
        warnings.append(
            "Нет наблюдаемой ставки шаблонированных SMS: денежная оценка потерь "
            "срабатывания не рассчитана. Показаны только объёмы сообщений."
        )

    items.sort(key=lambda item: (-item.monthly_loss.amount, item.kind.value, item.key))
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
            1 for metrics in run.metrics if _monthly_loss(metrics, factor).amount > 0
        ),
    )


def _loss_template_items(
    metrics: Sequence[TemplateMetrics],
    by_id: Mapping[str, SmsTemplate],
    factor: Decimal,
) -> list[ActionItem]:
    items: list[ActionItem] = []
    for item in metrics:
        loss = _monthly_loss(item, factor)
        if loss.amount <= 0:
            continue
        template = by_id.get(item.template_id)
        subject = template.text if template is not None else item.template_id
        name = template.name if template is not None else item.template_id
        detail = (
            f"Выгода {_money_text(monthly_net_benefit(item, factor))}/мес при "
            f"стоимости шаблона {_money_text(item.template_fee)}/мес и срабатывании "
            f"{_percent(item.trigger_rate)}."
        )
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
                    "Отключить шаблон или пересмотреть его необходимость: "
                    "ежемесячная плата выше экономии на сегментах."
                ),
                monthly_loss=loss,
                messages=item.matched_messages,
                segments=item.matched_segments,
                drill_down=DrillDown.TEMPLATE,
            )
        )
    return items


def _operator_items(
    triggers: Sequence[OperatorTrigger],
    by_id: Mapping[str, SmsTemplate],
    run: AnalysisRun,
    factor: Decimal,
) -> list[ActionItem]:
    items: list[ActionItem] = []
    for trigger in triggers:
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
        kind = ActionKind.OFF_OPERATOR if not trigger.listed else ActionKind.UNTRIGGERED
        if kind is ActionKind.OFF_OPERATOR:
            title = "Оператор вне списка шаблона"
            detail = (
                f"{trigger.untriggered_messages} сообщений подпали под шаблон, но "
                f"оператор {trigger.operator.value} не входит в список операторов "
                "регистрации. Сообщения оплачены как обычные SMS."
            )
            recommendation = (
                "Добавить оператора в регистрацию шаблона: срабатывание вырастет, "
                "а сегмент будет стоить по тарифу шаблонированных SMS."
            )
        else:
            title = "Срабатывание ниже 100 %"
            detail = (
                f"{trigger.untriggered_messages} сообщений подпали под шаблон и оплачены "
                f"как обычные, хотя оператор {trigger.operator.value} указан в шаблоне. "
                "Причина — в регистрации шаблона или определении оператора получателя."
            )
            recommendation = (
                "Проверить регистрацию шаблона у оператора и корректность определения "
                "оператора получателя в выгрузке."
            )
        items.append(
            ActionItem(
                key=f"{'off' if kind is ActionKind.OFF_OPERATOR else 'untrig'}:"
                f"{trigger.template_id}:{trigger.operator.value}",
                kind=kind,
                severity=_severity(loss),
                title=title,
                subject=subject,
                template_id=trigger.template_id,
                template_name=name,
                operator=trigger.operator.value,
                detail=detail,
                recommendation=recommendation,
                monthly_loss=loss,
                messages=trigger.untriggered_messages,
                segments=trigger.untriggered_segments,
                drill_down=DrillDown.TEMPLATE,
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
        item.kind in (ActionKind.OFF_OPERATOR, ActionKind.UNTRIGGERED)
        and item.segments > 0
        and item.monthly_loss.amount == 0
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
