"""Дрейф текста шаблона: сообщения изменились и собрались в кандидата."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mts_templates.domain.analytics.activity import TemplateMetrics
from mts_templates.domain.analytics.analysis import CandidateGroup
from mts_templates.domain.analytics.drift import (
    DriftFragmentKind,
    detect_template_drifts,
)
from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Money, Operator, Period

MSK = timezone(timedelta(hours=3))


def _period() -> Period:
    start = datetime(2026, 11, 1, tzinfo=MSK)
    return Period(start=start, end=start + timedelta(days=29))


def _template(
    *,
    template_id: str = "t1",
    text: str = "Ваш код %d",
    sender: str = "TEST",
    active: bool = True,
) -> SmsTemplate:
    return SmsTemplate(
        template_id=template_id,
        name="Шаблон",
        text=text,
        sender=sender,
        active=active,
        operators=frozenset({Operator.MTS}),
    )


def _metrics(
    *,
    template_id: str = "t1",
    matched_messages: int = 0,
) -> TemplateMetrics:
    return TemplateMetrics(
        template_id=template_id,
        matched_messages=matched_messages,
        matched_segments=matched_messages,
        delivered_messages=matched_messages,
        unique_recipients=matched_messages,
        actual_cost=Money.zero(),
        baseline_cost=Money.zero(),
        template_fee=Money.from_rub("2000"),
        net_benefit=Money.from_rub("-2000"),
        triggered_messages=0,
        off_operator_messages=0,
        trigger_rate=Decimal("0"),
        active=matched_messages > 0,
    )


def _candidate(
    *,
    candidate_id: str = "c1",
    text: str = "Ваш новый код %d",
    senders: tuple[str, ...] = ("TEST",),
    messages: int = 10,
) -> CandidateGroup:
    return CandidateGroup(
        candidate_id=candidate_id,
        template_text=text,
        messages=messages,
        segments=0,
        actual_cost=Money.zero(),
        templated_cost=Money.zero(),
        monthly_saving=Money.zero(),
        template_fee=Money.from_rub("2000"),
        net_monthly=Money.from_rub("-2000"),
        payback_months=None,
        confidence=Decimal("0.9"),
        coverage=Decimal("0.8"),
        senders=senders,
        operators=(Operator.MTS,),
        period=_period(),
        is_partial_period=False,
        daily_segments=(),
    )


def test_drift_detects_inserted_word_and_shows_where() -> None:
    drift = detect_template_drifts((_metrics(),), (_candidate(),), (_template(),))[0]

    assert drift.template_id == "t1"
    assert drift.candidate_id == "c1"
    assert drift.similarity == Decimal("0.8571")
    assert drift.removed == ()
    assert drift.added == ("новый",)
    assert [(item.kind, item.text) for item in drift.template_fragments] == [
        (DriftFragmentKind.EQUAL, "Ваш код %d"),
    ]
    assert [(item.kind, item.text) for item in drift.candidate_fragments] == [
        (DriftFragmentKind.EQUAL, "Ваш"),
        (DriftFragmentKind.ADDED, "новый"),
        (DriftFragmentKind.EQUAL, "код %d"),
    ]


def test_drift_detects_replaced_word() -> None:
    drift = detect_template_drifts(
        (_metrics(),),
        (_candidate(text="Ваш пароль %d"),),
        (_template(),),
    )[0]

    assert drift.removed == ("код",)
    assert drift.added == ("пароль",)
    assert drift.changed_tokens == 2
    assert drift.similarity == Decimal("0.6667")
    assert [(item.kind, item.text) for item in drift.template_fragments] == [
        (DriftFragmentKind.EQUAL, "Ваш"),
        (DriftFragmentKind.REMOVED, "код"),
        (DriftFragmentKind.EQUAL, "%d"),
    ]
    assert [(item.kind, item.text) for item in drift.candidate_fragments] == [
        (DriftFragmentKind.EQUAL, "Ваш"),
        (DriftFragmentKind.ADDED, "пароль"),
        (DriftFragmentKind.EQUAL, "%d"),
    ]


def test_no_drift_for_other_sender() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(senders=("OTHER",)),),
            (_template(),),
        )
        == ()
    )


def test_no_drift_when_template_still_matches_messages() -> None:
    assert (
        detect_template_drifts(
            (_metrics(matched_messages=5),),
            (_candidate(),),
            (_template(),),
        )
        == ()
    )


def test_no_drift_for_inactive_template() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(),),
            (_template(active=False),),
        )
        == ()
    )


def test_no_drift_for_far_text() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(text="Скидка двадцать процентов на весь заказ"),),
            (_template(),),
        )
        == ()
    )


def test_punctuation_only_change_is_not_a_drift() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(text="Ваш код: %d"),),
            (_template(),),
        )
        == ()
    )


def test_variable_range_is_not_a_drift() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(text="Ваш код %d"),),
            (_template(text="Ваш код %d{1,3}"),),
        )
        == ()
    )


def test_too_short_common_part_is_not_a_drift() -> None:
    assert (
        detect_template_drifts(
            (_metrics(),),
            (_candidate(text="Пароль %d"),),
            (_template(text="Код %d"),),
        )
        == ()
    )


def test_best_candidate_wins() -> None:
    drift = detect_template_drifts(
        (_metrics(),),
        (
            _candidate(candidate_id="far", text="Ваш новый пароль %d", messages=100),
            _candidate(candidate_id="near", text="Ваш новый код %d", messages=10),
        ),
        (_template(),),
    )[0]

    assert drift.candidate_id == "near"


def test_each_candidate_is_used_only_once() -> None:
    drifts = detect_template_drifts(
        (
            _metrics(template_id="t1"),
            _metrics(template_id="t2"),
        ),
        (_candidate(text="Ваш новый код подтверждения %d"),),
        (
            _template(template_id="t1"),
            _template(template_id="t2", text="Ваш новый код %d"),
        ),
    )

    assert [drift.template_id for drift in drifts] == ["t2"]


def test_drift_keeps_candidate_text() -> None:
    drift = detect_template_drifts((_metrics(),), (_candidate(),), (_template(),))[0]

    assert drift.candidate_text == "Ваш новый код %d"
    assert drift.total_tokens == 4
    assert drift.changed_tokens == 1
