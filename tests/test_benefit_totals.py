"""Суммы выгоды: только прибыльные кандидаты, только убыточные шаблоны, потенциал."""

from __future__ import annotations

from decimal import Decimal

from mts_templates.application.dto import DashboardSummary
from mts_templates.application.use_cases.dashboard import (
    negative_benefit,
    positive_benefit,
    profitable_candidates_count,
)
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.dashboard_page import (
    BENEFIT_SAVING_FONT_SIZE,
    _benefit_hint,
    _benefit_hint_html,
    _benefit_tooltip,
    _candidates_hint,
    _saving_text,
)


def test_positive_benefit_sums_only_profit() -> None:
    total = positive_benefit(
        (
            Money.from_rub("100.00"),
            Money.from_rub("-30.00"),
            Money.from_rub("0"),
            Money.from_rub("25.50"),
        )
    )

    assert total.amount == Decimal("125.50")


def test_negative_benefit_sums_only_loss() -> None:
    total = negative_benefit(
        (
            Money.from_rub("100.00"),
            Money.from_rub("-30.00"),
            Money.from_rub("-20.00"),
            Money.from_rub("0"),
        )
    )

    assert total.amount == Decimal("-50.00")


def test_sums_of_empty_sequences_are_zero() -> None:
    assert positive_benefit(()).amount == Decimal("0")
    assert negative_benefit(()).amount == Decimal("0")
    assert profitable_candidates_count(()) == 0


def test_profitable_candidates_count_ignores_zero_and_loss() -> None:
    count = profitable_candidates_count(
        (
            Money.from_rub("100.00"),
            Money.from_rub("-30.00"),
            Money.from_rub("0"),
            Money.from_rub("25.50"),
        )
    )

    assert count == 2


def _summary(
    *,
    total: Money | None,
    candidates: int = 0,
    profitable_candidates: int = 0,
    profitable: Money | None = None,
    losses: Money | None = None,
    potential: Money | None = None,
) -> DashboardSummary:
    return DashboardSummary(
        batches=(),
        batch=None,
        statistics=None,
        template_count=0,
        active_templates=0,
        inactive_templates=0,
        candidates=candidates,
        total_monthly_net_benefit=total,
        profitable_candidates=profitable_candidates,
        profitable_candidates_benefit=profitable,
        loss_templates_benefit=losses,
        potential_benefit=potential,
    )


def test_candidates_hint_without_analysis() -> None:
    assert _candidates_hint(_summary(total=None)) == "по последнему анализу"


def test_candidates_hint_shows_profitable_count() -> None:
    hint = _candidates_hint(
        _summary(
            total=Money.from_rub("500.00"),
            candidates=337,
            profitable_candidates=120,
            profitable=Money.from_rub("1500.00"),
        )
    )

    assert hint.startswith("по последнему анализу<br>выгодных: ")
    assert "120" in hint
    assert f"color: {active_palette().positive}" in hint
    assert f"font-size: {BENEFIT_SAVING_FONT_SIZE}px" in hint


def test_benefit_hint_when_analysis_is_absent() -> None:
    assert _benefit_hint(_summary(total=None)) == ""


def test_benefit_hint_without_potential() -> None:
    assert _benefit_hint(_summary(total=Money.from_rub("500.00"))) == ""


def test_benefit_hint_combines_savings_into_one_line() -> None:
    hint = _benefit_hint(
        _summary(
            total=Money.from_rub("500.00"),
            profitable=Money.from_rub("1500.00"),
            losses=Money.from_rub("-600.00"),
            potential=Money.from_rub("2100.00"),
        )
    )

    assert hint.splitlines() == [
        "потенциал: +2 100.00 ₽ в месяц",
        "внедрение кандидатов +1 500.00 ₽ · удаление убыточных шаблонов +600.00 ₽",
    ]


def test_benefit_tooltip_keeps_explanation_first() -> None:
    tooltip = _benefit_tooltip(
        _summary(
            total=Money.from_rub("500.00"),
            profitable=Money.from_rub("1500.00"),
            losses=Money.from_rub("-600.00"),
            potential=Money.from_rub("2100.00"),
        )
    )

    assert tooltip.splitlines() == [
        "в месяц, после вычета стоимости шаблонов",
        "потенциал: +2 100.00 ₽ в месяц",
        "внедрение кандидатов +1 500.00 ₽ · удаление убыточных шаблонов +600.00 ₽",
    ]


def test_benefit_hint_html_highlights_savings() -> None:
    html = _benefit_hint_html(
        _summary(
            total=Money.from_rub("500.00"),
            profitable=Money.from_rub("1500.00"),
            losses=Money.from_rub("-600.00"),
            potential=Money.from_rub("2100.00"),
        )
    )

    assert html.count("<br>") == 1
    for amount in ("+2 100.00 ₽", "+1 500.00 ₽", "+600.00 ₽"):
        assert f"{active_palette().positive}; font-size: {BENEFIT_SAVING_FONT_SIZE}px" in html
        assert amount in html
    assert "внедрение кандидатов" in html
    assert "удаление убыточных шаблонов" in html
    assert "после вычета стоимости шаблонов" not in html


def test_benefit_hint_html_without_potential() -> None:
    html = _benefit_hint_html(_summary(total=Money.from_rub("500.00")))

    assert html == ""
    assert "<span" not in html


def test_saving_text_marks_negative_amounts() -> None:
    assert _saving_text(Money.from_rub("100.00")) == "+100.00 ₽"
    assert _saving_text(Money.from_rub("-100.00")) == "−100.00 ₽"
