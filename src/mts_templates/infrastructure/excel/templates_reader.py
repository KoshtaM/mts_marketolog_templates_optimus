"""Чтение Excel-файла с зарегистрированными шаблонами.

Формат выгрузки МТС-Маркетолога: `ID шаблона`, `Текст шаблона`,
`Текст (пример) шаблона`, `Имя отправителя`, `Статус`, `Операторы`. Колонки
сопоставляются по заголовкам либо пользователем в диалоге.

Один шаблон может быть зарегистрирован на нескольких операторов двумя
способами: одной записью со списком операторов в ячейке или несколькими
записями с разными `ID шаблона`. Записи с посимвольно одинаковым текстом
(регистр, пунктуация и пробелы значимы) и отправителем — один шаблон: операторы
объединяются, плата за шаблон взимается один раз. Правила составления шаблонов
проверяются здесь: строка, которая им не соответствует, не импортируется, а в
предупреждении указывается её номер.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook

from mts_templates.application.dto import (
    TemplateColumnMapping,
    TemplateFilePreview,
    TemplateReadResult,
)
from mts_templates.domain.analytics.template_syntax import (
    TemplatePattern,
    compile_pattern,
    normalize_for_matching,
    parse_operators,
)
from mts_templates.domain.entities import DEFAULT_TEMPLATE_FEE, SmsTemplate
from mts_templates.domain.errors import TemplateAnalysisError, TemplateSyntaxError
from mts_templates.domain.value_objects import Money, Operator
from mts_templates.infrastructure.excel.statistics_reader import normalize_header

TEXT_ALIASES = ("текст шаблона", "шаблон", "текст", "text", "сообщение", "sms")
ID_ALIASES = ("id шаблона", "id", "ид", "код", "идентификатор")
NAME_ALIASES = ("название", "name", "имя шаблона", "наименование")
SENDER_ALIASES = ("имя отправителя", "отправитель", "sender")
ACTIVE_ALIASES = ("статус", "активен", "active", "состояние")
FEE_ALIASES = ("стоимость", "цена", "fee", "абонентская плата")
OPERATORS_ALIASES = ("операторы", "оператор")
EXAMPLE_ALIASES = ("текст (пример) шаблона", "пример")
TRAFFIC_ALIASES = ("тип трафика", "трафик")

INACTIVE_MARKERS = frozenset(
    {
        "неактивен",
        "не активен",
        "отключен",
        "отключён",
        "выключен",
        "не подключен",
        "не подключён",
        "приостановлен",
        "деактивирован",
        "удален",
        "удалён",
        "заблокирован",
        "отклонен",
        "отклонён",
        "архив",
    }
)
TRUE_MARKERS = frozenset(
    {"1", "true", "да", "yes", "y", "активен", "активный", "подключен", "подключён"}
)
FALSE_MARKERS = frozenset({"0", "false", "нет", "no", "n"})
FIRST_DATA_ROW = 2
MIN_SUBSTRING_ALIAS_LENGTH = 4
MAX_WARNINGS = 30


class ExcelTemplateReader:
    """Адаптер списка шаблонов: Excel → `SmsTemplate` с проверкой правил МТС."""

    def preview(self, path: Path, limit: int = 10) -> TemplateFilePreview:
        columns, rows = self._load(path, limit)
        return TemplateFilePreview(
            path=path,
            columns=columns,
            sample_rows=rows,
            suggested=detect_mapping(columns),
        )

    def read(
        self,
        path: Path,
        mapping: TemplateColumnMapping | None = None,
    ) -> TemplateReadResult:
        columns, rows = self._load(path, limit=None)
        resolved = mapping or detect_mapping(columns)
        if resolved is None:
            raise TemplateAnalysisError(
                "Не удалось определить колонку с текстом шаблона. Укажите сопоставление колонок."
            )
        if resolved.text not in columns:
            raise TemplateAnalysisError(f"В файле нет колонки {resolved.text!r}")
        return _build_result(rows, resolved)

    def _load(
        self, path: Path, limit: int | None
    ) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
        if not path.is_file():
            raise TemplateAnalysisError(f"Файл не найден: {path}")

        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:  # openpyxl поднимает разные типы
            raise TemplateAnalysisError(f"Не удалось прочитать Excel: {exc}") from exc

        try:
            sheet = workbook.active
            header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if header_row is None:
                raise TemplateAnalysisError("Файл пуст: нет строки заголовков")
            headers = [
                normalize_header(str(value)) if value is not None else "" for value in header_row
            ]
            columns = tuple(header for header in headers if header)
            if not columns:
                raise TemplateAnalysisError("Не удалось прочитать заголовки файла")

            rows: list[dict[str, str]] = []
            for values in sheet.iter_rows(min_row=FIRST_DATA_ROW, values_only=True):
                if values is None or all(value is None for value in values):
                    continue
                row: dict[str, str] = {}
                for index, value in enumerate(values):
                    if index >= len(headers) or not headers[index]:
                        continue
                    row[headers[index]] = "" if value is None else str(value).strip()
                rows.append(row)
                if limit is not None and len(rows) >= limit:
                    break
        finally:
            workbook.close()

        if not rows:
            raise TemplateAnalysisError("В файле нет строк с шаблонами")
        return columns, tuple(rows)


def detect_mapping(columns: Iterable[str]) -> TemplateColumnMapping | None:
    """Подобрать колонки по заголовкам; None, если текстовой колонки нет."""
    available = list(columns)
    text = _match(available, TEXT_ALIASES)
    if text is None:
        return None
    return TemplateColumnMapping(
        text=text,
        template_id=_match(available, ID_ALIASES),
        name=_match(available, NAME_ALIASES),
        sender=_match(available, SENDER_ALIASES),
        active=_match(available, ACTIVE_ALIASES),
        monthly_fee=_match(available, FEE_ALIASES),
        operators=_match(available, OPERATORS_ALIASES),
        example=_match(available, EXAMPLE_ALIASES),
        traffic_type=_match(available, TRAFFIC_ALIASES),
    )


def _build_result(
    rows: Iterable[dict[str, str]],
    mapping: TemplateColumnMapping,
) -> TemplateReadResult:
    warnings = _Warnings()
    groups: dict[tuple[str, str], _TemplateGroup] = {}
    order: list[tuple[str, str]] = []
    imported_rows = 0
    without_operators = 0

    for number, row in enumerate(rows, start=FIRST_DATA_ROW):
        text = _value(row, mapping.text)
        if not text:
            continue
        try:
            pattern = compile_pattern(text)
        except TemplateSyntaxError as exc:
            warnings.add(f"Строка {number} не импортирована: {exc}.")
            continue

        imported_rows += 1
        sender = _value(row, mapping.sender)
        key = (sender, pattern.identity)
        group = groups.get(key)
        if group is None:
            group = _TemplateGroup(
                text=text,
                sender=sender,
                pattern=pattern,
                name=_value(row, mapping.name),
                traffic_type=_value(row, mapping.traffic_type),
                monthly_fee=_parse_fee(_value(row, mapping.monthly_fee)),
            )
            groups[key] = group
            order.append(key)

        group.rows.append(number)
        row_id = _value(row, mapping.template_id)
        if row_id:
            if row_id in group.ids:
                warnings.add(f"Строка {number}: ID {row_id} уже встречался в файле.")
            else:
                group.ids.append(row_id)

        example = _value(row, mapping.example)
        if example:
            if not pattern.fullmatch(normalize_for_matching(example)):
                warnings.add(f"Строка {number}: пример не соответствует шаблону.")
            elif not group.example:
                group.example = example

        operators, unknown = parse_operators(_value(row, mapping.operators))
        if unknown:
            warnings.add(f"Строка {number}: неизвестные операторы: {', '.join(unknown)}.")
        if not operators:
            without_operators += 1

        active, known = _parse_active(_value(row, mapping.active))
        if not known:
            warnings.add(
                f"Строка {number}: неизвестный статус "
                f"{_value(row, mapping.active)!r} — шаблон считается отключённым."
            )
        group.add_registration(operators, active=active)

    templates: list[SmsTemplate] = []
    merged = 0
    for key in order:
        group = groups[key]
        if len(group.rows) > 1:
            merged += 1
        template_id = _canonical_id(group.ids) or _make_id(group.sender, group.text)
        if group.active and group.disabled_operators:
            warnings.add(
                f"Шаблон «{_shorten(group.text, 40)}» (ID {', '.join(group.ids)}) "
                f"отключён у операторов: {_operator_names(group.disabled_operators)}; "
                "в расчёт берутся только подключённые."
            )
        templates.append(
            SmsTemplate(
                template_id=template_id,
                name=group.name or _shorten(group.text),
                text=group.text,
                sender=group.sender,
                active=group.active,
                monthly_fee=group.monthly_fee,
                operators=group.resolved_operators,
                traffic_type=group.traffic_type,
                example=group.example,
            )
        )

    if merged:
        warnings.add(
            f"Объединены записи с одинаковым текстом: записей в файле — {imported_rows}, "
            f"шаблонов — {len(templates)}. Одинаковый текст у разных операторов — один "
            "шаблон, плата за него взимается один раз."
        )
    if without_operators:
        warnings.add(
            f"Записей без операторов: {without_operators} — такие шаблоны применяются ко всем."
        )
    return TemplateReadResult(templates=tuple(templates), warnings=warnings.finish())


@dataclass(slots=True)
class _TemplateGroup:
    """Записи файла, описывающие один шаблон у разных операторов."""

    text: str
    sender: str
    pattern: TemplatePattern
    name: str
    traffic_type: str
    monthly_fee: Money
    example: str = ""
    active: bool = False
    applies_to_all: bool = False
    operators: set[Operator] = field(default_factory=set)
    connected_operators: set[Operator] = field(default_factory=set)
    disabled_operators: set[Operator] = field(default_factory=set)
    ids: list[str] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)

    def add_registration(self, operators: frozenset[Operator], *, active: bool) -> None:
        self.operators.update(operators)
        if not active:
            self.disabled_operators.update(operators)
            return
        self.active = True
        if not operators:
            self.applies_to_all = True
        self.connected_operators.update(operators)

    @property
    def resolved_operators(self) -> frozenset[Operator]:
        """Операторы шаблона: подключённые для активного, все указанные для отключённого."""
        if not self.active:
            return frozenset(self.operators)
        return frozenset() if self.applies_to_all else frozenset(self.connected_operators)


class _Warnings:
    """Предупреждения импорта с ограничением объёма."""

    def __init__(self, limit: int = MAX_WARNINGS) -> None:
        self._items: list[str] = []
        self._limit = limit
        self._suppressed = 0

    def add(self, message: str) -> None:
        if len(self._items) < self._limit:
            self._items.append(message)
        else:
            self._suppressed += 1

    def finish(self) -> tuple[str, ...]:
        if self._suppressed:
            return (*self._items, f"…и ещё {self._suppressed} предупреждений.")
        return tuple(self._items)


def _match(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    """Колонка по заголовку: точное совпадение важнее частичного, длинный синоним важнее короткого."""
    best: tuple[int, int, int, str] | None = None
    for index, column in enumerate(columns):
        folded = column.casefold()
        for alias in aliases:
            if folded == alias:
                score = (2, len(alias), -index, column)
            elif len(alias) >= MIN_SUBSTRING_ALIAS_LENGTH and alias in folded:
                score = (1, len(alias), -index, column)
            else:
                continue
            if best is None or score > best:
                best = score
    return None if best is None else best[3]


def _value(row: dict[str, str], column: str | None) -> str:
    if not column:
        return ""
    return row.get(column, "").strip()


def _parse_active(raw: str) -> tuple[bool, bool]:
    """Вернуть `(активен, статус распознан)`; пустой статус — шаблон подключён."""
    value = raw.strip().casefold()
    if not value:
        return True, True
    if value in FALSE_MARKERS or value in INACTIVE_MARKERS:
        return False, True
    if value in TRUE_MARKERS:
        return True, True
    return False, False


def _parse_fee(raw: str) -> Money:
    if not raw:
        return DEFAULT_TEMPLATE_FEE
    cleaned = (
        raw.replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        return Money(Decimal(cleaned))
    except InvalidOperation as exc:
        raise TemplateAnalysisError(f"Некорректная стоимость шаблона: {raw!r}") from exc


def _shorten(text: str, limit: int = 60) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= limit else single_line[: limit - 1] + "…"


def _make_id(sender: str, text: str) -> str:
    digest = hashlib.sha256(f"{sender}\x1f{text}".encode()).hexdigest()
    return f"tpl-{digest[:12]}"


def _canonical_id(ids: list[str]) -> str:
    """ID шаблона из выгрузки: минимальный числовой, иначе первый непустой."""
    if not ids:
        return ""
    return min(ids, key=_id_sort_key)


def _id_sort_key(value: str) -> tuple[int, int, str]:
    return (0, int(value), value) if value.isdigit() else (1, 0, value)


def _operator_names(operators: Iterable[Operator]) -> str:
    return ", ".join(sorted(operator.value for operator in operators))
