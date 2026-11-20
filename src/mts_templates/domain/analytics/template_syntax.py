"""Синтаксис шаблонов МТС-Маркетолог: разбор, проверка и сопоставление текста.

Правила — раздел 9.1 AGENTS.md и «Порядок согласования шаблонов МТС».
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    normalize,
)
from mts_templates.domain.errors import TemplateSyntaxError
from mts_templates.domain.value_objects import Operator

MAX_GROUP_WORDS = 20

_OPERATOR_SEPARATOR = re.compile(r"[/,;]")
_VARIABLE = re.compile(
    r"%(?:(?P<kind>[wd])(?P<quantifier>\+|\{(?P<min>\d+),(?P<max>\d+)\})?|(?P<unknown>[^\W\d_]))"
)


@dataclass(frozen=True, slots=True)
class _Variable:
    """Переменная часть: `kind` — `w` (слово) или `d` (число); `limit` — число групп.

    `limit=1` — одиночная переменная, `limit=None` — `%d+` без ограничения.
    """

    kind: str
    limit: int | None

    @property
    def is_group(self) -> bool:
        return self.limit is None or self.limit > 1


@dataclass(frozen=True, slots=True)
class TemplatePattern:
    """Скомпилированный шаблон: регулярное выражение по нормализованному тексту."""

    regex: re.Pattern[str]
    literal_length: int
    variable_count: int
    source: str

    @property
    def identity(self) -> str:
        """Тождество шаблона — исходный текст как есть.

        Регистр, пунктуация и пробелы значимы: две записи выгрузки — один шаблон,
        только если текст совпадает посимвольно (после обрезки краёв). Иначе это
        разные шаблоны, даже если сообщения под них подпадают одинаково.
        """
        return self.source

    def fullmatch(self, normalized_text: str) -> bool:
        return self.regex.fullmatch(normalized_text) is not None


def normalize_for_matching(text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION) -> str:
    """Текст для сравнения с шаблоном: без пунктуации, нижний регистр, один пробел."""
    return normalize(text, policy)


def compile_pattern(
    text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION
) -> TemplatePattern:
    """Разобрать текст шаблона и собрать регулярное выражение; при нарушении правил — ошибка."""
    sequence: list[str | _Variable] = []
    word_patterns: list[str] = []

    for raw_word in text.split():
        pieces = _split_word(raw_word, policy)
        if not pieces:
            continue
        sequence.extend(pieces)
        word_patterns.append("".join(_piece_regex(piece) for piece in pieces))

    if not word_patterns:
        raise TemplateSyntaxError("Текст шаблона пуст")
    _check_adjacent_groups(sequence)

    literals = [piece for piece in sequence if isinstance(piece, str)]
    literal_length = sum(len(piece) for piece in literals)
    if not any(char.isalnum() for piece in literals for char in piece):
        raise TemplateSyntaxError("Шаблон должен содержать постоянный текст")

    variable_count = len(sequence) - len(literals)
    regex = re.compile(r"\s+".join(word_patterns))
    return TemplatePattern(
        regex=regex,
        literal_length=literal_length,
        variable_count=variable_count,
        source=text,
    )


def parse_operators(raw: str) -> tuple[frozenset[Operator], tuple[str, ...]]:
    """Операторы из колонки шаблона (`МТС/Мегафон/t2`) и неизвестные названия."""
    operators: set[Operator] = set()
    unknown: list[str] = []
    for name in _OPERATOR_SEPARATOR.split(raw):
        cleaned = name.strip()
        if not cleaned:
            continue
        operator = Operator.from_raw(cleaned)
        if operator is Operator.UNKNOWN:
            unknown.append(cleaned)
        else:
            operators.add(operator)
    return frozenset(operators), tuple(unknown)


def _split_word(raw_word: str, policy: NormalizationPolicy) -> list[str | _Variable]:
    pieces: list[str | _Variable] = []
    position = 0
    for match in _VARIABLE.finditer(raw_word):
        _append_literal(pieces, raw_word[position : match.start()], policy)
        pieces.append(_variable_from_match(match))
        position = match.end()
    _append_literal(pieces, raw_word[position:], policy)
    return pieces


def _append_literal(pieces: list[str | _Variable], raw: str, policy: NormalizationPolicy) -> None:
    literal = normalize(raw, policy)
    if literal:
        pieces.append(literal)


def _variable_from_match(match: re.Match[str]) -> _Variable:
    if match.group("unknown") is not None:
        raise TemplateSyntaxError(f"Неизвестная переменная %{match.group('unknown')}")
    kind = match.group("kind")
    quantifier = match.group("quantifier")
    if quantifier is None:
        return _Variable(kind=kind, limit=1)
    if quantifier == "+":
        if kind == "w":
            raise TemplateSyntaxError("Запрещено %w+: используйте %w{1,n}")
        return _Variable(kind=kind, limit=None)
    minimum, maximum = int(match.group("min")), int(match.group("max"))
    if minimum != 1 or maximum < 1:
        raise TemplateSyntaxError(f"Диапазон переменной %{kind}{quantifier} должен начинаться с 1")
    if maximum == 1:
        raise TemplateSyntaxError(f"Используйте %{kind} вместо %{kind}{{1,1}}")
    if maximum > MAX_GROUP_WORDS:
        raise TemplateSyntaxError(f"Число групп в %{kind}{{1,{maximum}}} больше {MAX_GROUP_WORDS}")
    return _Variable(kind=kind, limit=maximum)


def _check_adjacent_groups(sequence: list[str | _Variable]) -> None:
    for left, right in itertools.pairwise(sequence):
        if (
            isinstance(left, _Variable)
            and isinstance(right, _Variable)
            and left.is_group
            and right.is_group
        ):
            raise TemplateSyntaxError(
                "Запрещено объединять подряд групповые переменные: добавьте постоянный текст"
            )


def _piece_regex(piece: str | _Variable) -> str:
    if isinstance(piece, str):
        return re.escape(piece)
    token = r"\S+" if piece.kind == "w" else r"\d+"
    if piece.limit == 1:
        return token
    if piece.limit is None:
        return rf"{token}(?:\s+{token})*"
    return rf"{token}(?:\s+{token}){{0,{piece.limit - 1}}}"
