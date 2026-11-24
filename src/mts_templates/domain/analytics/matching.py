"""Сопоставление сообщений с зарегистрированными шаблонами по правилам МТС.

Сообщение подпадает под шаблон, если совпали имя отправителя (отбор пула) и текст
проходит грамматику шаблона. Оператор на подпадание не влияет: он определяет,
оплатит ли МТС сообщение как шаблонированное. Fuzzy-совпадений нет.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    sender_key,
)
from mts_templates.domain.analytics.template_syntax import (
    TemplatePattern,
    compile_pattern,
    normalize_for_matching,
)
from mts_templates.domain.entities import SmsMessage, SmsTemplate
from mts_templates.domain.value_objects import MessageClass, Operator


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    """Шаблон, готовый к сопоставлению."""

    template_id: str
    sender: str
    operators: frozenset[Operator]
    pattern: TemplatePattern

    def applies_to(self, operator: Operator) -> bool:
        return not self.operators or operator in self.operators

    @property
    def specificity(self) -> tuple[int, int]:
        return self.pattern.literal_length, -self.pattern.variable_count


def compile_template(
    template: SmsTemplate, policy: NormalizationPolicy = DEFAULT_NORMALIZATION
) -> CompiledTemplate:
    return CompiledTemplate(
        template_id=template.template_id,
        sender=template.sender,
        operators=template.operators,
        pattern=compile_pattern(template.text, policy),
    )


def compile_templates(
    templates: Iterable[SmsTemplate],
    policy: NormalizationPolicy = DEFAULT_NORMALIZATION,
    *,
    sender_case_sensitive: bool = False,
) -> dict[str, tuple[CompiledTemplate, ...]]:
    """Скомпилировать шаблоны и разложить по ключу имени отправителя."""
    by_sender: dict[str, list[CompiledTemplate]] = defaultdict(list)
    for template in templates:
        key = sender_key(template.sender, case_sensitive=sender_case_sensitive)
        by_sender[key].append(compile_template(template, policy))
    return {key: tuple(items) for key, items in by_sender.items()}


def match_message(
    text: str,
    templates: Sequence[CompiledTemplate],
    operator: Operator | None = None,
    policy: NormalizationPolicy = DEFAULT_NORMALIZATION,
) -> CompiledTemplate | None:
    """Шаблон, под который подпадает текст, или None.

    Оператор не участвует в подпадании: его соответствие списку шаблона
    проверяется отдельно, чтобы выявлять несработавшие шаблоны. Он используется
    только как разрешение ничьей: если два шаблона с одинаковым отправителем
    покрывают текст одинаково (тексты различаются регистром, пунктуацией или
    пробелами), выбирается тот, в списке операторов которого есть получатель.
    При нескольких совпадениях выигрывает более длинная постоянная часть, затем
    меньшее число переменных.
    """
    normalized = normalize_for_matching(text, policy)
    if not normalized:
        return None
    hits = [template for template in templates if template.pattern.fullmatch(normalized)]
    if not hits:
        return None
    best = max(template.specificity for template in hits)
    candidates = [template for template in hits if template.specificity == best]
    if operator is not None:
        for template in candidates:
            if template.applies_to(operator):
                return template
    return candidates[0]


def resolve_template(
    message: SmsMessage,
    compiled: Mapping[str, tuple[CompiledTemplate, ...]],
    policy: NormalizationPolicy = DEFAULT_NORMALIZATION,
    *,
    sender_case_sensitive: bool = False,
) -> CompiledTemplate | None:
    """Шаблон, подпавший под сообщение; выбор при нескольких совпадениях — как в анализе."""
    wildcard = compiled.get("", ())
    key = sender_key(message.sender, case_sensitive=sender_case_sensitive)
    pool = compiled.get(key, ()) + wildcard if key else wildcard
    if not pool or not message.text.strip():
        return None
    return match_message(message.text, pool, message.operator, policy)


def matches_candidate_pattern(
    message: SmsMessage,
    pattern: TemplatePattern,
    sender_keys: frozenset[str],
    policy: NormalizationPolicy = DEFAULT_NORMALIZATION,
    *,
    sender_case_sensitive: bool = False,
) -> bool:
    """Подпадает ли сообщение под шаблон-кандидат: отправитель и полный текст."""
    key = sender_key(message.sender, case_sensitive=sender_case_sensitive)
    if key not in sender_keys:
        return False
    return pattern.fullmatch(normalize_for_matching(message.text, policy))


def is_candidate_message(message: SmsMessage, *, delivered_only: bool) -> bool:
    """Сообщение, из которого может быть собран кандидат по правилам 11."""
    return (
        message.message_class is MessageClass.ORDINARY
        and message.segments > 0
        and bool(message.text.strip())
        and (not delivered_only or message.delivered)
    )
