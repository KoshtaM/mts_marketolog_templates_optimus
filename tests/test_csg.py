"""Тесты детерминированного поиска шаблонов-кандидатов (MTS-CSG)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from mts_templates.domain.analytics.canonical import signature_of
from mts_templates.domain.analytics.csg import (
    CandidateStatus,
    CsgConfig,
    build_signature_groups,
    extract_candidates,
    lint_template,
    merge_signature_groups,
)
from mts_templates.domain.analytics.normalization import (
    PUNCTUATION_SPACE,
    NormalizationPolicy,
    normalize,
    sender_key,
)
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator

MSK = timezone(timedelta(hours=3))


def message(
    message_id: str,
    text: str,
    *,
    sender: str = "TEST",
    segments: int = 1,
) -> SmsMessage:
    return SmsMessage(
        message_id=message_id,
        sent_at=datetime(2026, 11, 1, 12, 0, tzinfo=MSK),
        recipient="79000000000",
        operator=Operator.MTS,
        sender=sender,
        text=text,
        segments=segments,
        message_class=MessageClass.ORDINARY,
        cost=Money.zero(),
        delivered=True,
    )


def texts_of(candidate) -> tuple[str, ...]:
    return tuple(item.template_text for item in candidate)


def by_text(extraction, text: str):
    found = [item for item in extraction.candidates if item.template_text == text]
    assert len(found) == 1, f"кандидат {text!r} не найден среди {texts_of(extraction.candidates)}"
    return found[0]


# --- Нормализация -----------------------------------------------------------


def test_default_normalization_deletes_punctuation_and_lowercases() -> None:
    policy = NormalizationPolicy()
    assert normalize("Ваш код: 1234!", policy) == "ваш код 1234"


def test_punctuation_policy_space_keeps_word_boundaries() -> None:
    policy = NormalizationPolicy(punctuation=PUNCTUATION_SPACE)
    assert normalize("код-1234", policy) == "код 1234"


def test_fold_yo_is_opt_in() -> None:
    policy = NormalizationPolicy()
    assert normalize("ёж", policy) == "ёж"
    assert normalize("ёж", NormalizationPolicy(fold_yo=True)) == "еж"


def test_sender_key_folds_case_by_default() -> None:
    assert sender_key("TEST") == sender_key("test")
    assert sender_key("TEST", case_sensitive=True) != sender_key("test", case_sensitive=True)


# --- Канонические сигнатуры --------------------------------------------------


def test_signature_ignores_number_values() -> None:
    first = signature_of("Код 1234", NormalizationPolicy())
    second = signature_of("код 5678", NormalizationPolicy())
    assert first.key == second.key


def test_signature_marks_number_run_and_words() -> None:
    signature = signature_of("Запись на 18.11.2026 13:15 по адресу", NormalizationPolicy())
    kinds = [element.kind.value for element in signature.elements]
    values = [element.value for element in signature.elements]
    assert kinds.count("num_run") == 1
    assert "запись" in values and "адресу" in values


def test_signature_treats_url_email_phone_as_word() -> None:
    for text in (
        "Перейдите на сайт https://example.ru и проверьте",
        "Напишите на mail@example.ru для записи",
        "Позвоните по номеру 89001234567 для записи",
    ):
        signature = signature_of(text, NormalizationPolicy())
        assert any(element.kind.value == "word_var" for element in signature.elements), text


# --- Линтер -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("%w+", "w_plus"),
        ("%w{1,1}", "redundant_range"),
        ("%d{1,1}", "redundant_range"),
        ("%x", "unknown_variable"),
        ("код | 1234", "pipe"),
        ("%w %w", "adjacent_groups"),
        ("%w{1,3} %w{1,3}", "adjacent_groups"),
        ("%w", "no_literal"),
        ("код", "short_literal"),
    ],
)
def test_lint_rejects_forbidden_constructions(text: str, code: str) -> None:
    issues = lint_template(text, CsgConfig())
    assert any(issue.code == code for issue in issues), (text, issues)


def test_lint_accepts_date_and_time_as_two_numbers() -> None:
    assert lint_template("запись на %d %d по адресу г", CsgConfig()) == ()


# --- Точная группировка и статусы -------------------------------------------


def test_exact_group_becomes_auto_validated_candidate() -> None:
    messages = [message(f"m{index}", "Ваш код 1234 для входа", segments=1) for index in range(6)]
    extraction = extract_candidates(build_signature_groups(messages, CsgConfig()), CsgConfig())
    candidate = by_text(extraction, "ваш код %d для входа")
    assert candidate.status is CandidateStatus.AUTO_VALIDATED
    assert candidate.foreign_matches == 0


def test_groups_require_min_support_and_segments() -> None:
    messages = [message(f"m{index}", "Ваш код 1234 для входа") for index in range(3)]
    config = CsgConfig()
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    assert extraction.candidates == ()


def test_varying_number_counts_emit_group_variable() -> None:
    messages = [
        message("m1", "Ваш код 12 для входа"),
        message("m2", "Ваш код 34 56 для входа"),
        message("m3", "Ваш код 78 90 12 для входа"),
        message("m4", "Ваш код 34 56 78 90 для входа"),
        message("m5", "Ваш код 12 34 56 78 90 12 для входа"),
        message("m6", "Ваш код 34 для входа"),
    ]
    config = CsgConfig()
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    assert "%d{1,6}" in texts_of(extraction.candidates)[0]


def test_sender_case_sensitive_splits_groups() -> None:
    messages = [
        message(f"t{index}", "Ваш код 1234 для входа", sender="TEST") for index in range(5)
    ] + [message(f"l{index}", "Ваш код 1234 для входа", sender="test") for index in range(5)]
    config = CsgConfig(sender_case_sensitive=True)
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    candidates = [
        item for item in extraction.candidates if item.template_text == "ваш код %d для входа"
    ]
    assert len(candidates) == 2
    assert {candidate.sender for candidate in candidates} == {"TEST", "test"}
    assert all(candidate.status is CandidateStatus.AUTO_VALIDATED for candidate in candidates)


def test_sender_case_folding_warns_about_merged_senders() -> None:
    messages = [
        message(f"t{index}", "Ваш код 1234 для входа", sender="TEST") for index in range(3)
    ] + [message(f"l{index}", "Ваш код 1234 для входа", sender="test") for index in range(3)]
    config = CsgConfig()
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    candidate = by_text(extraction, "ваш код %d для входа")
    assert candidate.status is CandidateStatus.WARNING_SAVED
    assert {message.sender for message in candidate.messages} == {"TEST", "test"}


def test_template_must_cover_all_group_messages() -> None:
    messages = [
        message("m1", "Запись на 18.11 13:15 по адресу г Пермь"),
        message("m2", "Запись на 19.11 09:00 по адресу г Пермь"),
        message("m3", "Запись на 20.11 10:30 по адресу г Пермь"),
        message("m4", "Запись на 21.11 11:45 по адресу г Пермь"),
        message("m5", "Запись на 22.11 12:00 по адресу г Пермь"),
    ]
    config = CsgConfig()
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    assert texts_of(extraction.candidates) == ("запись на %d %d по адресу г пермь",)


# --- Слияние литеральных участков -------------------------------------------


def merged_extraction(messages: list[SmsMessage], config: CsgConfig | None = None):
    config = config or CsgConfig()
    return extract_candidates(build_signature_groups(messages, config), config)


def appointment_messages(count: int, *, start: int = 0, suffix: str = "") -> list[SmsMessage]:
    cities = ["Пермь Пермская", "Киров Гостиный", "Орел Орловская", "Тула Пролетарская"]
    names = ["Иванова И И", "Петрова П П", "Сидорова С С", "Кузнецова К К"]
    return [
        message(
            f"m{start + index}",
            f"Запись на 1{index % 10}.11 1{index % 10}:15 по адресу г {cities[index % 4]}"
            f" специалист {names[(index + start) % 4]} возьмите паспорт{suffix}",
        )
        for index in range(count)
    ]


def test_single_slot_with_few_variants_stays_literal() -> None:
    messages = [
        message(
            f"m{index}",
            f"Баланс {operation} на {index}00 рублей с карты 1{index}",
        )
        for index in range(6)
        for operation in ("пополнен", "списан")
    ]
    config = CsgConfig()
    merged = merge_signature_groups(build_signature_groups(messages, config), config)
    assert merged == ()


def test_slot_merge_requires_human_approval() -> None:
    messages = appointment_messages(6)
    extraction = merged_extraction(messages)
    candidate = by_text(
        extraction,
        "запись на %d %d по адресу г %w{1,2} специалист %w{1,3} возьмите паспорт",
    )
    assert candidate.status is CandidateStatus.NEEDS_HUMAN_APPROVAL
    assert candidate.confidence == Decimal("0.9")


def test_tail_suffix_splits_brand_variants() -> None:
    plain = appointment_messages(8, start=0)
    branded = appointment_messages(8, start=10, suffix=" DOCTORLIGHT")
    extraction = merged_extraction(plain + branded)
    assert "запись на %d %d по адресу г %w{1,2} специалист %w{1,3} возьмите паспорт" in texts_of(
        extraction.candidates
    )
    assert (
        "запись на %d %d по адресу г %w{1,2} специалист %w{1,3} возьмите паспорт doctorlight"
        in texts_of(extraction.candidates)
    )


def test_anchor_keeps_constant_word_inside_slot() -> None:
    messages = appointment_messages(8)
    extraction = merged_extraction(messages)
    merged = [
        item
        for item in extraction.candidates
        if item.status is CandidateStatus.NEEDS_HUMAN_APPROVAL
    ]
    assert merged, texts_of(extraction.candidates)
    assert all("специалист" in item.template_text for item in merged)


# --- Защита от чужих совпадений и поглощение --------------------------------


def test_merge_rejected_on_foreign_match() -> None:
    own = appointment_messages(8)
    foreign = [
        message(f"f{index}", f"Курсы записи на 1{index}.11 начнутся специалист ждёт вас")
        for index in range(8)
    ]
    extraction = merged_extraction(own + foreign)
    merged = [
        item
        for item in extraction.candidates
        if item.status is CandidateStatus.NEEDS_HUMAN_APPROVAL
    ]
    assert merged, texts_of(extraction.candidates)
    own_ids = {item.message_id for item in own}
    for item in merged:
        assert all(message.message_id in own_ids for message in item.messages)


def test_exact_candidate_absorbs_fully_covered_groups() -> None:
    messages = [message(f"m{index}", "Ваш код 1234 для входа", segments=1) for index in range(6)]
    config = CsgConfig()
    extraction = extract_candidates(build_signature_groups(messages, config), config)
    candidate = by_text(extraction, "ваш код %d для входа")
    assert len(candidate.groups) == 1
    assert candidate.message_count == 6
