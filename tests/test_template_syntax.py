"""Тесты синтаксиса шаблонов МТС: разбор, запреты и операторы."""

from __future__ import annotations

import re

import pytest

from mts_templates.domain.analytics.template_syntax import (
    compile_pattern,
    normalize_for_matching,
    parse_operators,
)
from mts_templates.domain.errors import TemplateSyntaxError
from mts_templates.domain.value_objects import Operator


@pytest.mark.parametrize(
    "text",
    [
        "Новый пароль %w",
        "Заказ: %w{1,10} %d на сумму %d руб принят",
        "Вы записаны на приём %d+ в %d+ По адресу: %w{1,6} Возьмите паспорт",
        "%d - код подтверждения телефона",
        "Результаты исследований %w{1,3} по номеру направления %d от %d+ готовы",
        "Исследование проводится натощак (%w часов голода)",
    ],
)
def test_valid_templates_compile(text: str) -> None:
    compile_pattern(text)


@pytest.mark.parametrize(
    ("text", "message_fragment"),
    [
        ("Ваш код %w+", "%w+"),
        ("Ваш код %w{1,1}", "%w"),
        ("Ваш код %d{1,1}", "%d"),
        ("Список %w{1,21}", "больше 20"),
        ("Список %w{2,5}", "начинаться с 1"),
        ("Код %s", "Неизвестная переменная"),
        ("Заказ %w{1,3} %d+ готов", "подряд"),
        ("Заказ %d+ %w{1,3} готов", "подряд"),
        ("%d %d", "постоянный текст"),
        ("   ", "пуст"),
    ],
)
def test_forbidden_constructions_are_rejected(text: str, message_fragment: str) -> None:
    with pytest.raises(TemplateSyntaxError, match=re.escape(message_fragment)):
        compile_pattern(text)


def test_single_number_variables_may_follow_each_other() -> None:
    compile_pattern("Дата %d %d готово")


def test_punctuation_around_variable_is_ignored() -> None:
    pattern = compile_pattern("Ваш код: %d.")

    assert pattern.fullmatch(normalize_for_matching("Ваш код 4455!"))


def test_word_variable_does_not_match_across_spaces() -> None:
    pattern = compile_pattern("Привет, %w!")

    assert pattern.fullmatch(normalize_for_matching("Привет, Иван!"))
    assert not pattern.fullmatch(normalize_for_matching("Привет, Иван Петров!"))


def test_pattern_counts_literals_and_variables() -> None:
    pattern = compile_pattern("Ваш код %d и %w{1,3}")

    assert pattern.variable_count == 2
    assert pattern.literal_length == len("ваш") + len("код") + len("и")


def test_identity_keeps_case_punctuation_and_spaces() -> None:
    base = compile_pattern("Ваш код %d")

    assert base.identity == "Ваш код %d"
    assert compile_pattern("ВАШ КОД %d").identity != base.identity
    assert compile_pattern("Ваш код %d!").identity != base.identity
    assert compile_pattern("Ваш  код %d").identity != base.identity


def test_identity_does_not_affect_matching() -> None:
    upper = compile_pattern("ВАШ КОД %d")

    assert upper.identity == "ВАШ КОД %d"
    assert upper.fullmatch(normalize_for_matching("Ваш код 1234"))


def test_parse_operators_maps_registry_names() -> None:
    operators, unknown = parse_operators("МТС/Мегафон/Билайн/Ростелеком/t2")

    assert operators == frozenset(
        {Operator.MTS, Operator.MEGAFON, Operator.BEELINE, Operator.ROSTELECOM, Operator.T2}
    )
    assert unknown == ()


def test_parse_operators_reports_unknown_names() -> None:
    operators, unknown = parse_operators("МТС/Неизвестный")

    assert operators == frozenset({Operator.MTS})
    assert unknown == ("Неизвестный",)


def test_empty_operator_list_is_empty_set() -> None:
    assert parse_operators("   ") == (frozenset(), ())
