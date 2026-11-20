"""Загрузка каталога тарифов из TOML.

Ставки не хардкодятся в коде: файл `config/tariffs.toml` описывает пакеты,
подписки и оплату по факту с периодами действия.
"""

from __future__ import annotations

import tomllib
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from mts_templates.domain.errors import TariffError
from mts_templates.domain.tariffs.models import (
    BlockMode,
    PackagePlan,
    PayPerMessagePlan,
    PricingMode,
    RateTier,
    SubscriptionBlock,
    SubscriptionPlan,
    TariffCatalog,
    TariffPlan,
)
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from mts_templates.infrastructure.config import config_dir

TARIFFS_FILE_NAME = "tariffs.toml"


def default_catalog_path() -> Path:
    return config_dir() / TARIFFS_FILE_NAME


def load_tariff_catalog(path: Path | None = None) -> TariffCatalog:
    """Прочитать каталог тарифов; отсутствующий файл — пустой каталог."""
    source = path or default_catalog_path()
    if not source.is_file():
        return TariffCatalog(plans=())

    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise TariffError(f"Не удалось прочитать каталог тарифов {source}: {exc}") from exc

    entries = raw.get("tariff", [])
    if not isinstance(entries, list):
        raise TariffError("Секция [[tariff]] должна быть массивом таблиц")

    plans: list[TariffPlan] = []
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise TariffError(f"Тариф №{index}: ожидалась таблица")
        plans.append(_build_plan(entry, index))
    return TariffCatalog(plans=tuple(plans))


def _build_plan(entry: dict[str, Any], index: int) -> TariffPlan:
    kind = _text(entry, "kind", index)
    tariff_id = _text(entry, "id", index)
    name = _text(entry, "name", index)
    message_class = _message_class(entry, index)
    effective_from = _optional_date(entry.get("effective_from"), index)
    effective_to = _optional_date(entry.get("effective_to"), index)
    operator_scope = _operators(entry.get("operators"))

    if kind == "package":
        return PackagePlan(
            tariff_id=tariff_id,
            name=name,
            message_class=message_class,
            effective_from=effective_from,
            effective_to=effective_to,
            operator_scope=operator_scope,
            package_size=int(entry["package_size"]),
            pricing_mode=PricingMode(str(entry.get("pricing_mode", "uniform"))),
            tiers=tuple(_tier(item, index) for item in entry.get("tiers", [])),
            overage_rates=_rates(entry.get("overage")),
        )
    if kind == "subscription":
        return SubscriptionPlan(
            tariff_id=tariff_id,
            name=name,
            message_class=message_class,
            effective_from=effective_from,
            effective_to=effective_to,
            operator_scope=operator_scope,
            blocks=tuple(_block(item, index) for item in entry.get("blocks", [])),
            charge_per_segment=bool(entry.get("charge_per_segment", False)),
        )
    if kind == "pay_per_message":
        return PayPerMessagePlan(
            tariff_id=tariff_id,
            name=name,
            message_class=message_class,
            effective_from=effective_from,
            effective_to=effective_to,
            operator_scope=operator_scope,
            rates=_rates(entry.get("rates")),
            default_rate=_optional_money(entry.get("default_rate"), index),
        )
    raise TariffError(f"Тариф №{index}: неизвестный вид {kind!r}")


def _tier(raw: object, index: int) -> RateTier:
    item = _table(raw, index, "tier")
    return RateTier(
        from_segment=int(item["from"]),
        to_segment=int(item["to"]) if item.get("to") is not None else None,
        price=_money(item.get("price"), index),
    )


def _block(raw: object, index: int) -> SubscriptionBlock:
    item = _table(raw, index, "block")
    return SubscriptionBlock(
        from_message=int(item["from"]),
        to_message=int(item["to"]) if item.get("to") is not None else None,
        price=_money(item.get("price"), index),
        mode=BlockMode(str(item.get("mode", "block_start"))),
    )


def _table(raw: object, index: int, name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TariffError(f"Тариф №{index}: {name} должен быть таблицей")
    return raw


def _text(entry: dict[str, Any], key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TariffError(f"Тариф №{index}: поле {key} обязательно")
    return value.strip()


def _message_class(entry: dict[str, Any], index: int) -> MessageClass:
    raw = str(entry.get("message_class", "ordinary"))
    try:
        return MessageClass(raw)
    except ValueError as exc:
        raise TariffError(f"Тариф №{index}: неизвестный класс сообщения {raw!r}") from exc


def _optional_date(value: object, index: int) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise TariffError(f"Тариф №{index}: некорректная дата {value!r}") from exc


def _operators(value: object) -> frozenset[Operator] | None:
    if not value:
        return None
    if not isinstance(value, list):
        raise TariffError("Список операторов должен быть массивом строк")
    return frozenset(Operator.from_raw(str(item)) for item in value)


def _rates(value: object) -> dict[Operator, Money]:
    if not value:
        return {}
    if not isinstance(value, dict):
        raise TariffError("Ставки операторов должны быть таблицей")
    return {
        Operator.from_raw(str(operator)): _money(amount, 0) for operator, amount in value.items()
    }


def _money(value: object, index: int) -> Money:
    if value is None:
        raise TariffError(f"Тариф №{index}: не задана цена")
    try:
        return Money(Decimal(str(value).replace(",", ".")))
    except (InvalidOperation, ValueError) as exc:
        raise TariffError(f"Тариф №{index}: некорректная цена {value!r}") from exc


def _optional_money(value: object, index: int) -> Money | None:
    return None if value is None else _money(value, index)
