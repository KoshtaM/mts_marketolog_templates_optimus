#!/usr/bin/env python3
"""Профилирование Excel-выгрузки статистики МТС-Маркетолога.

Скрипт не изменяет файл и не печатает персональные данные: только агрегаты,
количества и предупреждения. Для работы нужен только openpyxl.

Пример:
    uv run --with openpyxl python profile_statistics.py november.xlsx
    uv run --with openpyxl python profile_statistics.py november.xlsx --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook

REQUIRED_COLUMNS = [
    "ID сообщения",
    "Дата попытки отправки",
    "Текст сообщения",
    "Оператор получателя",
    "Статус отправки",
    "Статус доставки СМС или ММС",
    "Цена за один сегмент",
    "Стоимость",
    "Количество сегментов в sms",
    "Тип пакета",
    "Номер получателя",
    "Имя отправителя",
]

MONEY_COLUMNS = {"Цена за один сегмент", "Стоимость"}
INT_COLUMNS = {"Количество сегментов в sms", "Количество sms в пакете при покупке"}

PACKAGE_TEMPLATED = "Подписка. Все операторы (шаблонированный)"
PACKAGE_ORDINARY = "Подписка. Все операторы"


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def as_datetime(value: Any) -> datetime | None:
    moscow = timezone(timedelta(hours=3))
    if isinstance(value, datetime):
        parsed = value
    else:
        text = as_text(value)
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=moscow)
    return parsed.astimezone(moscow)


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def rate(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def message_class(package: str) -> str:
    if not package:
        return "error"
    if "шаблонированный" in package.lower():
        return "templated"
    return "ordinary"


def metadata_hash(text: str, phone: str, sent_at: str, segments: int) -> str:
    raw = f"{text}\x1f{phone}\x1f{sent_at}\x1f{segments}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class IdState:
    rows: int = 0
    cost: Decimal = Decimal("0")
    segments: int = 0
    classes: set[str] = field(default_factory=set)
    delivered: bool = False
    failed: bool = False
    first_cost: Decimal | None = None
    different_cost: bool = False
    first_meta: str | None = None
    metadata_conflict: bool = False


def profile(path: Path) -> dict[str, Any]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows)
        except StopIteration as exc:
            raise ValueError("Файл пуст: нет строки заголовков") from exc

        headers = [as_text(h) for h in header_row]
        index = {name: i for i, name in enumerate(headers) if name}
        missing = [name for name in REQUIRED_COLUMNS if name not in index]
        if missing:
            raise ValueError("Нет обязательных колонок: " + ", ".join(missing))

        def cell(row: tuple[Any, ...], name: str) -> Any:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return None
            return row[pos]

        totals = {
            "rows": 0,
            "segments": 0,
            "cost": Decimal("0"),
            "zero_cost_rows": 0,
            "missing_cost_rows": 0,
            "delivered": 0,
            "delivery_failed": 0,
            "send_failed": 0,
        }
        send_status: Counter[str] = Counter()
        delivery_status: Counter[str] = Counter()
        channel_status: Counter[str] = Counter()
        packages: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "rows": 0,
                "segments": 0,
                "cost": Decimal("0"),
                "zero_cost_rows": 0,
                "delivered": 0,
                "delivery_failed": 0,
            }
        )
        operators: Counter[str] = Counter()
        error_reasons: Counter[str] = Counter()
        ids: dict[str, IdState] = {}
        dates: list[datetime] = []
        unparsed_dates = 0
        empty_package_rows = 0
        empty_price_rows = 0

        for row in rows:
            if row is None or all(v is None or as_text(v) == "" for v in row):
                continue

            totals["rows"] += 1
            message_id = as_text(cell(row, "ID сообщения")) or "(пусто)"
            package = as_text(cell(row, "Тип пакета"))
            price = as_decimal(cell(row, "Цена за один сегмент"))
            cost_value = as_decimal(cell(row, "Стоимость"))
            cost = cost_value if cost_value is not None else Decimal("0")
            segments = as_int(cell(row, "Количество сегментов в sms"))
            send = as_text(cell(row, "Статус отправки")) or "(пусто)"
            delivery = as_text(cell(row, "Статус доставки СМС или ММС")) or "(пусто)"
            operator = as_text(cell(row, "Оператор получателя")) or "(пусто)"
            channel = as_text(cell(row, "Канал")) or "(пусто)"
            sent_at = as_datetime(cell(row, "Дата попытки отправки"))
            sent_at_text = as_text(cell(row, "Дата попытки отправки"))

            totals["segments"] += segments
            totals["cost"] += cost
            if cost_value is None:
                totals["missing_cost_rows"] += 1
            elif cost == 0:
                totals["zero_cost_rows"] += 1
            if delivery == "Успешная доставка":
                totals["delivered"] += 1
            elif delivery == "Ошибка доставки":
                totals["delivery_failed"] += 1
            if send == "Ошибка отправки":
                totals["send_failed"] += 1

            send_status[send] += 1
            delivery_status[delivery] += 1
            channel_status[channel] += 1
            operators[operator] += 1

            pkg_stats = packages[package or "(пусто)"]
            pkg_stats["rows"] += 1
            pkg_stats["segments"] += segments
            pkg_stats["cost"] += cost
            if cost_value is not None and cost == 0:
                pkg_stats["zero_cost_rows"] += 1
            if delivery == "Успешная доставка":
                pkg_stats["delivered"] += 1
            elif delivery == "Ошибка доставки":
                pkg_stats["delivery_failed"] += 1

            if not package:
                empty_package_rows += 1
            if price is None:
                empty_price_rows += 1
            if not package or price is None:
                reason = (
                    as_text(cell(row, "Причина неотправки sms"))
                    or as_text(cell(row, "Причина недоставки sms"))
                    or "пустой пакет/цена"
                )
                error_reasons[reason] += 1

            if sent_at is not None:
                dates.append(sent_at)
            elif sent_at_text:
                unparsed_dates += 1

            state = ids.get(message_id)
            if state is None:
                state = IdState()
                ids[message_id] = state
            state.rows += 1
            state.cost += cost
            state.segments = max(state.segments, segments)
            state.classes.add(message_class(package))
            state.delivered = state.delivered or delivery == "Успешная доставка"
            state.failed = state.failed or delivery == "Ошибка доставки"
            if state.first_cost is None:
                state.first_cost = cost
            elif cost != state.first_cost:
                state.different_cost = True
            meta = metadata_hash(
                as_text(cell(row, "Текст сообщения")),
                as_text(cell(row, "Номер получателя")),
                sent_at_text,
                segments,
            )
            if state.first_meta is None:
                state.first_meta = meta
            elif meta != state.first_meta:
                state.metadata_conflict = True

        unique = {
            "messages": len(ids),
            "segments": sum(s.segments for s in ids.values()),
            "cost": sum((s.cost for s in ids.values()), Decimal("0")),
            "zero_cost": sum(1 for s in ids.values() if s.cost == 0),
            "delivered": sum(1 for s in ids.values() if s.delivered),
            "delivery_failed": sum(1 for s in ids.values() if s.failed),
        }

        unique_classes: dict[str, dict[str, Any]] = {
            "templated": {"messages": 0, "segments": 0, "cost": Decimal("0")},
            "ordinary": {"messages": 0, "segments": 0, "cost": Decimal("0")},
            "error": {"messages": 0, "segments": 0, "cost": Decimal("0")},
        }
        mixed_class_ids = 0
        for state in ids.values():
            classes = state.classes
            if "templated" in classes:
                cls = "templated"
                if "ordinary" in classes:
                    mixed_class_ids += 1
            elif "ordinary" in classes:
                cls = "ordinary"
            else:
                cls = "error"
            bucket = unique_classes[cls]
            bucket["messages"] += 1
            bucket["segments"] += state.segments
            bucket["cost"] += state.cost

        duplicate_ids = [s for s in ids.values() if s.rows > 1]
        duplicates = {
            "ids_with_multiple_rows": len(duplicate_ids),
            "extra_rows": sum(s.rows - 1 for s in duplicate_ids),
            "ids_with_different_cost": sum(1 for s in duplicate_ids if s.different_cost),
            "ids_with_metadata_conflict": sum(1 for s in duplicate_ids if s.metadata_conflict),
            "mixed_class_ids": mixed_class_ids,
        }

        period: dict[str, Any] = {"from": None, "to": None, "days": 0}
        if dates:
            first, last = min(dates), max(dates)
            period = {
                "from": first.isoformat(),
                "to": last.isoformat(),
                "days": (last.date() - first.date()).days + 1,
            }

        warnings: list[str] = []
        if period["days"] and period["days"] < 28:
            warnings.append(
                f"Период выглядит неполным: {period['days']} дн. "
                "Не сравнивайте абсолютные суммы с полным месяцем без нормализации."
            )
        if totals["rows"] and duplicates["extra_rows"] / totals["rows"] > 0.01:
            warnings.append(
                "Много дубликатов ID: "
                f"{duplicates['extra_rows']} дополнительных строк "
                f"({duplicates['extra_rows'] / totals['rows']:.1%}). "
                "Это биллинговые компоненты; суммируйте стоимость и считайте сообщение один раз."
            )
        if empty_package_rows or empty_price_rows:
            warnings.append(
                f"Строки с пустым пакетом/ценой: пакет={empty_package_rows}, цена={empty_price_rows}. "
                "Исключены из экономики, но сохранены в отчёте."
            )
        if unparsed_dates:
            warnings.append(f"Не удалось разобрать даты в {unparsed_dates} строках.")
        unknown_operators = [op for op in operators if op == "(пусто)"]
        if unknown_operators:
            warnings.append("Есть строки с пустым оператором получателя.")
        if totals["missing_cost_rows"]:
            warnings.append(f"Строки без стоимости: {totals['missing_cost_rows']}.")

        def cost_per_segment(cost: Decimal, segments: int) -> str:
            if not segments:
                return "0.0000"
            return rate(cost / segments)

        return {
            "file": str(path),
            "sheet": ws.title,
            "period": period,
            "rows": totals["rows"],
            "totals": {
                **{k: v for k, v in totals.items() if k != "cost"},
                "cost": money(totals["cost"]),
                "effective_cost_per_segment": cost_per_segment(totals["cost"], totals["segments"]),
            },
            "unique": {
                **{k: v for k, v in unique.items() if k != "cost"},
                "cost": money(unique["cost"]),
                "effective_cost_per_segment": cost_per_segment(unique["cost"], unique["segments"]),
            },
            "messages": {
                cls: {
                    "messages": bucket["messages"],
                    "segments": bucket["segments"],
                    "cost": money(bucket["cost"]),
                }
                for cls, bucket in unique_classes.items()
            },
            "packages": {
                name: {
                    **{k: v for k, v in stats.items() if k != "cost"},
                    "cost": money(stats["cost"]),
                }
                for name, stats in sorted(packages.items(), key=lambda item: -item[1]["rows"])
            },
            "operators": dict(operators.most_common()),
            "status": {
                "send": dict(send_status),
                "delivery": dict(delivery_status),
                "channel": dict(channel_status),
            },
            "duplicates": duplicates,
            "errors": {
                "empty_package_rows": empty_package_rows,
                "empty_price_rows": empty_price_rows,
                "reasons": dict(error_reasons.most_common(10)),
            },
            "warnings": warnings,
        }
    finally:
        wb.close()


def print_human(data: dict[str, Any]) -> None:
    def table(mapping: dict[str, Any], limit: int | None = None) -> None:
        items = list(mapping.items())
        if limit is not None:
            items = items[:limit]
        width = max((len(str(k)) for k, _ in items), default=0)
        for key, value in items:
            print(f"  {str(key).ljust(width)}  {value}")
        if limit is not None and len(mapping) > limit:
            print(f"  ... ещё {len(mapping) - limit}")

    period = data["period"]
    print(f"Файл: {data['file']}")
    print(f"Лист: {data['sheet']}")
    print(f"Период: {period['from']} .. {period['to']} ({period['days']} дн.)")
    print(f"Строк: {data['rows']}")
    print()
    print("Итоги по строкам:")
    table(data["totals"])
    print()
    print("Итоги по уникальным сообщениям:")
    table(data["unique"])
    print()
    print("Классы сообщений:")
    for name, bucket in data["messages"].items():
        print(
            f"  {name:10} сообщений={bucket['messages']:>7} "
            f"сегментов={bucket['segments']:>7} стоимость={bucket['cost']:>14}"
        )
    print()
    print("Пакеты:")
    for name, bucket in data["packages"].items():
        print(
            f"  {name!r:60} строк={bucket['rows']:>7} сегментов={bucket['segments']:>7} "
            f"стоимость={bucket['cost']:>14} нулевых={bucket['zero_cost_rows']:>7}"
        )
    print()
    print("Дубликаты:")
    table(data["duplicates"])
    print()
    print("Ошибки:")
    table({k: v for k, v in data["errors"].items() if k != "reasons"})
    if data["errors"]["reasons"]:
        print("  Причины:")
        table(data["errors"]["reasons"], limit=8)
    print()
    print("Статусы:")
    for group, values in data["status"].items():
        print(f"  {group}:")
        table(values)
    print()
    if data["warnings"]:
        print("Предупреждения:")
        for warning in data["warnings"]:
            print(f"  - {warning}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Профилирование статистики МТС-Маркетолога")
    parser.add_argument("path", type=Path, help="Путь к .xlsx")
    parser.add_argument("--json", action="store_true", help="Вывести только JSON")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"Файл не найден: {args.path}", file=sys.stderr)
        return 2
    if args.path.suffix.lower() != ".xlsx":
        print("Ожидается файл .xlsx", file=sys.stderr)
        return 2

    try:
        data = profile(args.path)
    except Exception as exc:  # noqa: BLE001 - CLI должен показать причину
        print(f"Ошибка профилирования: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_human(data)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
