"""Центр действий: рабочий список убытков и возможностей анализа.

Сервис отвечает на вопрос «где мы теряем деньги и что сделать первым».
В таблицу попадают только пункты с убытком или выгодой: убыточные шаблоны
и выгодные кандидаты. Каждый пункт несёт сумму в рублях за месяц (та же
месячная модель, что у кандидатов), объём сообщений и переход к сообщениям.

Убыток и выгода взаимно исключаются: шаблон заполняет `monthly_loss`,
кандидат — `monthly_benefit`. Информационные статусы «Срабатывание ниже
100 %» и «Шаблонировано без шаблона» в таблицу не попадают; последний
остаётся предупреждением вне таблицы.

Убыток шаблона — его ежемесячная плата за вычетом наблюдаемой выгоды от
экономии сегментов; выгода кандидата — месячная экономия за вычетом платы.
Ставки берутся из периода, а не из прайс-листа.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from mts_templates.domain.analytics.activity import TemplateMetrics
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


class DrillDown(StrEnum):
    """Куда ведёт переход из пункта центра действий."""

    TEMPLATE = "template"


@dataclass(frozen=True, slots=True)
class ActionItem:
    """Пункт списка: убыток или выгода с денежной оценкой и действием.

    `monthly_loss` и `monthly_benefit` не заполняются одновременно.
    """

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
        if self.monthly_loss.amount > 0 and self.monthly_benefit.amount > 0:
            raise ValueError("Шаблон не может быть одновременно выгодным и убыточным")


@dataclass(frozen=True, slots=True)
class ActionCenter:
    """Готовый рабочий список убытков и возможностей за период загрузки."""

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


def build_action_center(
    run: AnalysisRun,
    templates: Sequence[SmsTemplate],
) -> ActionCenter:
    """Собрать центр действий по прогону анализа и набору шаблонов."""
    by_id = {template.template_id: template for template in templates}
    factor = monthly_factor(run.period)
    items: list[ActionItem] = []

    items.extend(_template_items(run.metrics, by_id, factor))
    items.extend(_candidate_items(run.candidates))

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
            f"Убыток {_money_text(loss)}/мес при стоимости шаблона "
            f"{_money_text(item.template_fee)}/мес и срабатывании "
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
                monthly_benefit=Money.zero(),
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
        monthly_benefit=Money.zero(),
    )


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
