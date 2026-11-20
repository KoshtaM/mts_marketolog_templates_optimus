"""Тесты загрузки каталога тарифов из TOML."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from mts_templates.domain.errors import TariffError
from mts_templates.domain.tariffs.models import (
    PackagePlan,
    PayPerMessagePlan,
    SubscriptionPlan,
    TariffCatalog,
    TariffKind,
)
from mts_templates.domain.value_objects import MessageClass, Operator
from mts_templates.infrastructure.tariffs.toml_catalog import load_tariff_catalog

CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "tariffs.toml"


@pytest.fixture
def catalog() -> TariffCatalog:
    return load_tariff_catalog(CATALOG_PATH)


def test_catalog_has_all_kinds(catalog: TariffCatalog) -> None:
    kinds = {plan.kind for plan in catalog.plans}
    assert kinds == {
        TariffKind.PACKAGE,
        TariffKind.SUBSCRIPTION,
        TariffKind.PAY_PER_MESSAGE,
    }


def test_historical_subscription_is_resolved_by_period(catalog: TariffCatalog) -> None:
    october = catalog.resolve(
        day=date(2026, 10, 15),
        message_class=MessageClass.ORDINARY,
        operator=Operator.MTS,
        kind=TariffKind.SUBSCRIPTION,
    )
    november = catalog.resolve(
        day=date(2026, 11, 15),
        message_class=MessageClass.ORDINARY,
        operator=Operator.MTS,
        kind=TariffKind.SUBSCRIPTION,
    )

    assert isinstance(october, SubscriptionPlan)
    assert isinstance(november, SubscriptionPlan)
    assert october.tariff_id == "subscription-ordinary-2026-10"
    assert november.tariff_id == "subscription-ordinary-2026-11"
    assert october.blocks[1].price.amount == Decimal("42.00")
    assert november.blocks[1].price.amount == Decimal("52.00")


def test_operator_specific_subscription_wins(catalog: TariffCatalog) -> None:
    plan = catalog.resolve(
        day=date(2026, 11, 15),
        message_class=MessageClass.TEMPLATED,
        operator=Operator.MTS,
        kind=TariffKind.SUBSCRIPTION,
    )

    assert plan.tariff_id == "subscription-templated-mts"


def test_package_effective_rate(catalog: TariffCatalog) -> None:
    plan = catalog.resolve(
        day=date(2026, 11, 15),
        message_class=MessageClass.ORDINARY,
        operator=Operator.MTS,
        kind=TariffKind.PACKAGE,
    )

    assert isinstance(plan, PackagePlan)
    assert plan.effective_rate().amount == Decimal("9.60")


def test_pay_per_message_rates(catalog: TariffCatalog) -> None:
    plan = catalog.resolve(
        day=date(2026, 11, 15),
        message_class=MessageClass.ORDINARY,
        operator=Operator.MEGAFON,
        kind=TariffKind.PAY_PER_MESSAGE,
    )

    assert isinstance(plan, PayPerMessagePlan)
    assert plan.rate_for(Operator.MEGAFON).amount == Decimal("31.90")
    assert plan.rate_for(Operator.UNKNOWN).amount == Decimal("7.70")


def test_missing_file_gives_empty_catalog(tmp_path: Path) -> None:
    catalog = load_tariff_catalog(tmp_path / "absent.toml")

    assert catalog.plans == ()


def test_invalid_kind_fails(tmp_path: Path) -> None:
    path = tmp_path / "tariffs.toml"
    path.write_text(
        """
[[tariff]]
id = "x"
kind = "unknown"
name = "X"
message_class = "ordinary"
""",
        encoding="utf-8",
    )

    with pytest.raises(TariffError, match="неизвестный вид"):
        load_tariff_catalog(path)
