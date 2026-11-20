"""Доменный сценарий анализа: матчинг, метрики, кандидаты.

Сервис работает с доменными типами и не знает про SQLite, Qt и Excel.
Сообщения читаются дважды через фабрику итератора: первый проход — ставки,
второй — матчинг и кандидаты.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from mts_templates.application.dto import AnalysisConfig, ImportBatch
from mts_templates.domain.analytics.activity import TemplateActivity
from mts_templates.domain.analytics.analysis import (
    PARTIAL_PERIOD_DAYS,
    AnalysisRun,
    CandidateGroup,
    monthly_factor,
)
from mts_templates.domain.analytics.baseline import ObservedRates, build_observed_rates
from mts_templates.domain.analytics.csg import (
    CsgCandidate,
    CsgConfig,
    build_signature_groups,
    extract_candidates,
)
from mts_templates.domain.analytics.matching import compile_templates, match_message
from mts_templates.domain.analytics.normalization import sender_key
from mts_templates.domain.entities import SmsMessage, SmsTemplate
from mts_templates.domain.errors import OperationCancelled, TariffError
from mts_templates.domain.tariffs.models import (
    PayPerMessagePlan,
    TariffCatalog,
    TariffKind,
)
from mts_templates.domain.value_objects import MessageClass, Money, Period

WARNING_NO_TEMPLATES = "Шаблоны не импортированы: все сообщения считаются незашаблонированными."
WARNING_NO_ORDINARY_RATE = (
    "Нет средней стоимости сегмента обычных SMS: baseline по умолчанию равен нулю."
)
WARNING_CATALOG_FALLBACK = (
    "Каталог тарифов не дал ставку для части сообщений: использована наблюдаемая ставка."
)
WARNING_NO_TEMPLATED_RATE = (
    "Нет средней стоимости сегмента шаблонированных SMS: стоимость кандидатов "
    "считается по их фактической стоимости."
)
BENEFIT_FORMULA_VERSION = 2
SEGMENTATION_VERSION = 2


def compute_config_hash(
    config: AnalysisConfig,
    templates: Sequence[SmsTemplate],
    *,
    include_candidates: bool = True,
) -> str:
    """Хэш параметров анализа и набора шаблонов."""
    payload = {
        "baseline_mode": config.baseline_mode,
        "benefit_formula": BENEFIT_FORMULA_VERSION,
        "segmentation": SEGMENTATION_VERSION,
        "delivered_only": config.delivered_only,
        "min_support": config.min_support,
        "min_cluster_segments": config.min_cluster_segments,
        "min_text_length": config.min_text_length,
        "max_foreign_matches": config.max_foreign_matches,
        "max_w_words": config.max_w_words,
        "max_d_words": config.max_d_words,
        "max_word_slots_per_merge": config.max_word_slots_per_merge,
        "max_literal_cardinality": config.max_literal_cardinality,
        "max_tail_depth": config.max_tail_depth,
        "punctuation_policy": config.punctuation_policy,
        "fold_yo": config.fold_yo,
        "fold_homoglyphs": config.fold_homoglyphs,
        "sender_case_sensitive": config.sender_case_sensitive,
        "template_fee": str(config.template_fee.amount),
        "include_candidates": include_candidates,
        "templates": sorted(
            (
                template.template_id,
                template.sender,
                template.text,
                template.active,
                sorted(operator.value for operator in template.operators),
            )
            for template in templates
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def compute_analysis(
    *,
    batch: ImportBatch,
    messages: Callable[[], Iterable[SmsMessage]],
    templates: Sequence[SmsTemplate],
    config: AnalysisConfig,
    include_candidates: bool,
    run_id: str,
    config_hash: str,
    created_at: datetime,
    catalog: TariffCatalog | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> AnalysisRun:
    """Посчитать метрики шаблонов и кандидатов за период загрузки."""
    period = _period(batch)
    warnings: list[str] = []

    if not templates:
        warnings.append(WARNING_NO_TEMPLATES)

    observed = build_observed_rates(messages())
    if observed.average_for(MessageClass.ORDINARY) is None:
        warnings.append(WARNING_NO_ORDINARY_RATE)

    baseline_provider = _baseline_provider(config, observed, catalog, warnings)
    policy = config.normalization_policy()

    active_templates = [template for template in templates if template.active]
    compiled = compile_templates(
        active_templates,
        policy,
        sender_case_sensitive=config.sender_case_sensitive,
    )
    wildcard = compiled.get("", ())
    per_sender = {sender: items + wildcard for sender, items in compiled.items() if sender}

    activities = {
        template.template_id: TemplateActivity(template.template_id) for template in templates
    }
    matched_message_count = 0
    untriggered_matches = 0
    untriggered_off_operator = 0
    unmatched_templated = 0
    message_count = 0
    candidate_messages: list[SmsMessage] = []

    for index, message in enumerate(messages(), start=1):
        if should_cancel is not None and index % 1000 == 0:
            _raise_if_cancelled(should_cancel)
        if message.segments <= 0:
            continue
        message_count += 1

        pool = per_sender.get(
            sender_key(message.sender, case_sensitive=config.sender_case_sensitive),
            wildcard,
        )
        template = (
            match_message(message.text, pool, message.operator, policy)
            if pool and message.text.strip()
            else None
        )
        if template is not None:
            matched_message_count += 1
            listed = template.applies_to(message.operator)
            triggered = message.message_class is MessageClass.TEMPLATED
            if not triggered:
                untriggered_matches += 1
                if not listed:
                    untriggered_off_operator += 1
            baseline = baseline_provider(message) if triggered else Money.zero()
            activities[template.template_id].add(message, baseline, operator_listed=listed)
            continue

        if message.message_class is MessageClass.TEMPLATED:
            unmatched_templated += 1
        if _is_candidate(message, config):
            candidate_messages.append(message)

    metrics = tuple(
        activities[template.template_id].to_metrics(monthly_fee=template.monthly_fee)
        for template in sorted(templates, key=lambda item: (not item.active, item.template_id))
    )
    operator_triggers = tuple(
        trigger for activity in activities.values() for trigger in activity.operator_triggers()
    )

    if untriggered_matches:
        warnings.append(
            f"{untriggered_matches} сообщений подпали под шаблон, но оплачены как обычные; "
            f"из них {untriggered_off_operator} — оператор не в списке шаблона. "
            "Подробности — в разбивке по операторам."
        )
    if unmatched_templated:
        warnings.append(
            f"{unmatched_templated} шаблонированных сообщений не подпали ни под один шаблон: "
            "проверьте регистрацию шаблона, имя отправителя и текст."
        )

    candidates: tuple[CandidateGroup, ...] = ()
    if include_candidates:
        _raise_if_cancelled(should_cancel)
        candidates = _find_candidates(
            candidate_messages,
            observed,
            config,
            period,
            warnings,
            should_cancel=should_cancel,
        )

    if period.days < PARTIAL_PERIOD_DAYS:
        warnings.append(
            f"Период анализа неполный ({period.days} дн.): суммы показаны за период, "
            "выгода кандидатов в месяц смоделирована на 30 дней."
        )

    return AnalysisRun(
        run_id=run_id,
        batch_id=batch.id,
        config_hash=config_hash,
        created_at=created_at,
        period=period,
        message_count=message_count,
        matched_message_count=matched_message_count,
        metrics=metrics,
        candidates=candidates,
        warnings=tuple(warnings),
        operator_triggers=operator_triggers,
    )


def _find_candidates(
    messages: Sequence[SmsMessage],
    observed: ObservedRates,
    config: AnalysisConfig,
    period: Period,
    warnings: list[str],
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[CandidateGroup, ...]:
    if not messages:
        return ()

    csg_config = CsgConfig(
        normalization=config.normalization_policy(),
        sender_case_sensitive=config.sender_case_sensitive,
        min_support=config.min_support,
        min_segments=config.min_cluster_segments,
        min_literal_length=config.min_text_length,
        max_w_words=config.max_w_words,
        max_d_words=config.max_d_words,
        max_foreign_matches=config.max_foreign_matches,
        max_word_slots_per_merge=config.max_word_slots_per_merge,
        max_literal_cardinality=config.max_literal_cardinality,
        max_tail_depth=config.max_tail_depth,
    )
    _raise_if_cancelled(should_cancel)
    groups = build_signature_groups(messages, csg_config)
    _raise_if_cancelled(should_cancel)
    extraction = extract_candidates(groups, csg_config)
    warnings.extend(extraction.warnings)

    templated_rate = observed.average_for(MessageClass.TEMPLATED)
    if templated_rate is None:
        warnings.append(WARNING_NO_TEMPLATED_RATE)

    month_factor = monthly_factor(period)
    candidates = [
        _candidate_from_csg(
            candidate,
            templated_rate,
            config.template_fee,
            period,
            month_factor,
        )
        for candidate in extraction.candidates
    ]
    candidates.sort(key=lambda item: (-item.net_monthly.amount, item.candidate_id))
    return tuple(candidates)


def _candidate_from_csg(
    candidate: CsgCandidate,
    templated_rate: Money | None,
    template_fee: Money,
    period: Period,
    month_factor: Decimal,
) -> CandidateGroup:
    """Кандидат: экономия = фактическая стоимость группы − оценка по шаблону.

    Оценка по шаблону — средняя стоимость сегмента шаблонированных SMS × сегменты
    группы; стоимость шаблона вычитается отдельно из месячной экономии.
    """
    templated_cost = (
        templated_rate * candidate.segments if templated_rate is not None else candidate.cost
    )
    saving_period = candidate.cost - templated_cost
    monthly_saving = saving_period * month_factor
    net_monthly = monthly_saving - template_fee
    payback = template_fee.amount / monthly_saving.amount if monthly_saving.amount > 0 else None
    examples = tuple(message.text for message in candidate.messages[:3])
    return CandidateGroup(
        candidate_id=_candidate_id(candidate.sender_key, candidate.template_text),
        template_text=candidate.template_text,
        messages=candidate.message_count,
        segments=candidate.segments,
        actual_cost=candidate.cost,
        templated_cost=templated_cost,
        monthly_saving=monthly_saving,
        template_fee=template_fee,
        net_monthly=net_monthly,
        payback_months=payback,
        confidence=candidate.confidence,
        coverage=candidate.coverage,
        senders=candidate.raw_senders,
        operators=candidate.operators,
        period=period,
        is_partial_period=period.days < PARTIAL_PERIOD_DAYS,
        examples=examples,
        status=candidate.status.value,
        warnings=candidate.warnings,
        foreign_matches=candidate.foreign_matches,
    )


def _candidate_id(sender_key_value: str, template_text: str) -> str:
    digest = hashlib.sha256(f"{sender_key_value}\x1f{template_text}".encode()).hexdigest()
    return digest[:12]


def _is_candidate(message: SmsMessage, config: AnalysisConfig) -> bool:
    if message.message_class is not MessageClass.ORDINARY:
        return False
    if not message.text.strip():
        return False
    return not (config.delivered_only and not message.delivered)


def _baseline_provider(
    config: AnalysisConfig,
    observed: ObservedRates,
    catalog: TariffCatalog | None,
    warnings: list[str],
) -> Callable[[SmsMessage], Money]:
    if config.baseline_mode == "catalog" and catalog is not None:
        fallback_used = False

        def catalog_baseline(message: SmsMessage) -> Money:
            nonlocal fallback_used
            rate = _catalog_rate(catalog, message)
            if rate is None:
                fallback_used = True
                rate = observed.rate_for(message.operator, message.segments)
            if rate is None:
                return Money.zero()
            return rate * max(message.segments, 1)

        def provider(message: SmsMessage) -> Money:
            cost = catalog_baseline(message)
            if fallback_used and WARNING_CATALOG_FALLBACK not in warnings:
                warnings.append(WARNING_CATALOG_FALLBACK)
            return cost

        return provider

    rate = observed.average_for(MessageClass.ORDINARY)
    if rate is None:
        return lambda _message: Money.zero()

    def observed_baseline(message: SmsMessage) -> Money:
        return rate * message.segments

    return observed_baseline


def _catalog_rate(catalog: TariffCatalog, message: SmsMessage) -> Money | None:
    try:
        plan = catalog.resolve(
            day=message.sent_at.date(),
            message_class=MessageClass.ORDINARY,
            operator=message.operator,
            kind=TariffKind.PAY_PER_MESSAGE,
        )
    except TariffError:
        return None
    if not isinstance(plan, PayPerMessagePlan):
        return None
    try:
        return plan.rate_for(message.operator)
    except TariffError:
        return None


def _period(batch: ImportBatch) -> Period:
    start = batch.period_from or batch.imported_at
    end = batch.period_to or batch.imported_at
    return Period(start=start, end=end)


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise OperationCancelled("Операция отменена пользователем")
