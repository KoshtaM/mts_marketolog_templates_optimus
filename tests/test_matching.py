"""Тесты сопоставления сообщений с шаблонами по правилам МТС."""

from __future__ import annotations

from dataclasses import replace

from mts_templates.domain.analytics.matching import (
    CompiledTemplate,
    compile_template,
    compile_templates,
    is_candidate_message,
    match_message,
    matches_candidate_pattern,
    resolve_template,
)
from mts_templates.domain.analytics.template_syntax import compile_pattern
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import MessageClass, Operator
from tests.helpers import make_message


def _template(
    template_id: str,
    text: str,
    *,
    sender: str = "TEST",
    operators: frozenset[Operator] = frozenset(),
) -> SmsTemplate:
    return SmsTemplate(
        template_id=template_id,
        name=template_id,
        text=text,
        sender=sender,
        operators=operators,
    )


def _compiled(
    template_id: str, text: str, operators: frozenset[Operator] = frozenset()
) -> CompiledTemplate:
    return compile_template(_template(template_id, text, operators=operators))


def _matched_id(text: str, templates: tuple[CompiledTemplate, ...]) -> str | None:
    hit = match_message(text, templates)
    return None if hit is None else hit.template_id


def test_exact_text_matches() -> None:
    template = _compiled("t1", "Оплата получена")

    assert _matched_id("Оплата получена", (template,)) == "t1"


def test_number_variable_matches_single_token() -> None:
    template = _compiled("t1", "Ваш код %d")

    assert _matched_id("Ваш код 1234", (template,)) == "t1"


def test_number_variable_rejects_letters() -> None:
    template = _compiled("t1", "Ваш код %d")

    assert _matched_id("Ваш код abc", (template,)) is None


def test_word_group_matches_one_to_n_words() -> None:
    template = _compiled("t1", "Результат исследования Вашего клеща %w{1,7}")

    assert _matched_id("Результат исследования Вашего клеща отрицательный.", (template,)) == "t1"


def test_word_group_limit_is_enforced() -> None:
    template = _compiled("t1", "Заказ %w{1,2} готов")

    assert _matched_id("Заказ один два три готов", (template,)) is None


def test_punctuation_and_case_are_ignored() -> None:
    template = _compiled("t1", "%w{1,3} Ваши результаты готовы.")

    assert _matched_id("Казакова З Р, ваши результаты готовы", (template,)) == "t1"


def test_date_and_time_are_two_number_variables() -> None:
    template = _compiled("t1", "Запись на %d %d по адресу %w{1,3}")

    assert _matched_id("Запись на 12.08.2026 17:40 по адресу Киров, Ленина 5", (template,)) == "t1"


def test_number_sequence_matches_several_numbers() -> None:
    template = _compiled("t1", "Запись по телефону: %d+")

    assert _matched_id("Запись по телефону: 711-100, 255-100.", (template,)) == "t1"


def test_partial_text_does_not_match() -> None:
    template = _compiled("t1", "Ваш код %d")

    assert _matched_id("Ваш код 1234, никому не сообщайте", (template,)) is None


def test_operator_list_does_not_affect_matching() -> None:
    """Оператор влияет на тарификацию, а не на подпадание под шаблон."""
    template = _compiled("t1", "Ваш код %d", operators=frozenset({Operator.MEGAFON}))

    hit = match_message("Ваш код 1234", (template,))

    assert hit is not None
    assert hit.template_id == "t1"
    assert hit.applies_to(Operator.MEGAFON)
    assert not hit.applies_to(Operator.MTS)


def test_empty_operator_list_applies_to_all_operators() -> None:
    template = _compiled("t1", "Ваш код %d")

    assert template.applies_to(Operator.T2)


def test_more_specific_template_wins() -> None:
    short = _compiled("short", "Код %d")
    long = _compiled("long", "Код подтверждения %d")

    assert _matched_id("Код подтверждения 1234", (short, long)) == "long"


def test_suffix_variant_is_not_merged_with_base_template() -> None:
    base_text = "Запись на %w{1,2} по адресу %w{1,6} Возьмите паспорт"
    base = _compiled("base", base_text, frozenset({Operator.MTS, Operator.BEELINE}))
    suffix = _compiled("suffix", f"{base_text} — DOCTORLIGHT", frozenset({Operator.T2}))

    with_suffix = "Запись на УЗИ по адресу Ленина 5 Возьмите паспорт — DOCTORLIGHT"
    without_suffix = "Запись на УЗИ по адресу Ленина 5 Возьмите паспорт"

    assert _matched_id(with_suffix, (base, suffix)) == "suffix"
    assert _matched_id(without_suffix, (base, suffix)) == "base"


def test_tied_patterns_prefer_template_listing_operator() -> None:
    mts = _compiled("mts", "Ваш код %d", operators=frozenset({Operator.MTS}))
    beeline = _compiled("beeline", "ВАШ КОД %d", operators=frozenset({Operator.BEELINE}))

    listed = match_message("Ваш код 1234", (mts, beeline), Operator.BEELINE)
    fallback = match_message("Ваш код 1234", (mts, beeline), Operator.T2)

    assert listed is not None and listed.template_id == "beeline"
    assert fallback is not None and fallback.template_id == "mts"


def test_compile_templates_groups_by_sender() -> None:
    compiled = compile_templates(
        [
            _template("t1", "Оплата получена", sender="TEST"),
            _template("t2", "Код %d", sender="TEST"),
            _template("t3", "Универсальный шаблон", sender=""),
        ]
    )

    assert set(compiled) == {"test", ""}
    assert len(compiled["test"]) == 2


def test_compile_templates_respects_sender_case() -> None:
    compiled = compile_templates(
        [
            _template("t1", "Оплата получена", sender="TEST"),
            _template("t2", "Оплата получена", sender="test"),
        ],
        sender_case_sensitive=True,
    )

    assert set(compiled) == {"TEST", "test"}


def test_message_without_text_is_not_matched() -> None:
    template = _compiled("t1", "Ваш код %d")

    assert _matched_id("   ", (template,)) is None


def test_resolve_template_also_checks_universal_templates() -> None:
    """Универсальные шаблоны работают и для сообщений с конкретным отправителем."""
    compiled = compile_templates(
        [
            _template("sender", "Оплата получена", sender="TEST"),
            _template("universal", "Универсальный шаблон", sender=""),
        ]
    )
    message = replace(make_message("m"), text="Универсальный шаблон")

    hit = resolve_template(message, compiled)

    assert hit is not None and hit.template_id == "universal"


def test_candidate_pattern_requires_sender_and_full_match() -> None:
    pattern = compile_pattern("Заказ %d готов к выдаче")
    message = replace(make_message("m"), text="Заказ 1234 готов к выдаче")

    assert matches_candidate_pattern(message, pattern, frozenset({"test"}))
    assert not matches_candidate_pattern(message, pattern, frozenset({"other"}))
    assert not matches_candidate_pattern(
        replace(message, text="Заказ 1234 готов к выдаче, срочно"), pattern, frozenset({"test"})
    )


def test_candidate_message_filters_class_segments_and_delivery() -> None:
    ordinary = make_message("m", message_class=MessageClass.ORDINARY, delivered=True)
    templated = replace(ordinary, message_class=MessageClass.TEMPLATED)
    zero_segments = replace(ordinary, segments=0)
    undelivered = replace(ordinary, delivered=False)

    assert is_candidate_message(ordinary, delivered_only=True)
    assert is_candidate_message(undelivered, delivered_only=False)
    assert not is_candidate_message(templated, delivered_only=True)
    assert not is_candidate_message(zero_segments, delivered_only=True)
    assert not is_candidate_message(undelivered, delivered_only=True)
