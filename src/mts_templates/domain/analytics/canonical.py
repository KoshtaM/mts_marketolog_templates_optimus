"""Канонические токены и сигнатуры текста для детерминированной группировки.

Сигнатура не зависит от значений переменных: числа сворачиваются в числовые
серии (`NUM_RUN`) с отдельно сохранёнными длинами, смешанные токены и
сущности (ссылки, e-mail, телефоны) становятся одним словом-переменной.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    normalize,
    normalize_with_offsets,
)

_ENTITY = re.compile(
    r"(?P<url>(?:https?://|www\.)\S+)"
    r"|(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<phone>(?:\+7|\b8|\b7)[\d()\-]{8,14}\d)",
    re.IGNORECASE,
)
_NON_SPACE = re.compile(r"\S+")


class TokenKind(StrEnum):
    """Тип токена после нормализации."""

    LITERAL = "lit"
    NUMBER = "num"
    MIXED = "mixed"
    ENTITY = "entity"


class ElementKind(StrEnum):
    """Тип элемента сигнатуры."""

    LITERAL = "lit"
    NUMBER_RUN = "num_run"
    WORD_VARIABLE = "word_var"


@dataclass(frozen=True, slots=True)
class Token:
    """Токен нормализованного текста.

    `value` — нормализованная форма для сравнения, `surface` — исходная форма
    с регистром, пунктуацией и тире. Группировка и матчинг используют `value`,
    в текст шаблона-кандидата попадает `surface`.
    """

    kind: TokenKind
    value: str
    raw: str = ""
    surface: str = ""


@dataclass(frozen=True, slots=True)
class SignatureElement:
    """Элемент сигнатуры: литерал, числовая серия или слово-переменная.

    `limit` задаёт максимальное число слов для `%w{1,n}`; для литералов и чисел
    не используется. `surface` — исходная форма литерала для текста шаблона;
    в ключ тождества сигнатуры не входит.
    """

    kind: ElementKind
    value: str = ""
    limit: int = 1
    surface: str = ""


@dataclass(frozen=True, slots=True)
class CanonicalSignature:
    """Сигнатура сообщения: ключ группировки и длины числовых серий."""

    elements: tuple[SignatureElement, ...]
    run_lengths: tuple[int, ...] = ()

    @property
    def key(self) -> tuple[tuple[str, str], ...]:
        """Ключ тождества: значения переменных и длины серий не входят."""
        return tuple(
            (element.kind.value, element.value if element.kind is ElementKind.LITERAL else "")
            for element in self.elements
        )

    @property
    def literal_length(self) -> int:
        return sum(
            len(element.value) for element in self.elements if element.kind is ElementKind.LITERAL
        )

    @property
    def numeric_slots(self) -> int:
        return sum(1 for element in self.elements if element.kind is ElementKind.NUMBER_RUN)

    @property
    def variable_count(self) -> int:
        return sum(1 for element in self.elements if element.kind is not ElementKind.LITERAL)

    def text(self) -> str:
        """Человекочитаемое представление сигнатуры для диагностики."""
        parts: list[str] = []
        for element in self.elements:
            if element.kind is ElementKind.LITERAL:
                parts.append(element.value)
            elif element.kind is ElementKind.NUMBER_RUN:
                parts.append("<NUM>")
            else:
                parts.append("<W>")
        return " ".join(parts)


def tokenize(text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION) -> tuple[Token, ...]:
    """Разбить текст на токены, сохранив исходную форму слов.

    Нормализованное значение используется для сравнения, `surface` — для текста
    шаблона-кандидата: регистр, пунктуация и тире берутся из исходного текста.
    """
    tokens: list[Token] = []
    position = 0
    for match in _ENTITY.finditer(text):
        tokens.extend(_plain_tokens(text[position : match.start()], policy))
        raw = match.group(0)
        tokens.append(
            Token(
                kind=TokenKind.ENTITY,
                value=normalize(raw, policy),
                raw=raw,
                surface=raw,
            )
        )
        position = match.end()
    tokens.extend(_plain_tokens(text[position:], policy))
    return tuple(tokens)


def signature_of(
    text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION
) -> CanonicalSignature:
    """Построить каноническую сигнатуру текста."""
    tokens = tokenize(text, policy)
    elements: list[SignatureElement] = []
    run_lengths: list[int] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind is TokenKind.NUMBER:
            length = 0
            while index < len(tokens) and tokens[index].kind is TokenKind.NUMBER:
                length += 1
                index += 1
            elements.append(SignatureElement(kind=ElementKind.NUMBER_RUN))
            run_lengths.append(length)
            continue
        if token.kind is TokenKind.LITERAL:
            elements.append(
                SignatureElement(
                    kind=ElementKind.LITERAL,
                    value=token.value,
                    surface=token.surface,
                )
            )
        else:
            elements.append(SignatureElement(kind=ElementKind.WORD_VARIABLE))
        index += 1
    return CanonicalSignature(elements=tuple(elements), run_lengths=tuple(run_lengths))


def is_literal_only(elements: tuple[SignatureElement, ...]) -> bool:
    return all(element.kind is ElementKind.LITERAL for element in elements)


def _plain_tokens(text: str, policy: NormalizationPolicy) -> list[Token]:
    normalized, offsets = normalize_with_offsets(text, policy)
    spans = [match.span() for match in _NON_SPACE.finditer(normalized)]
    if not spans:
        return []
    cores = [(offsets[start], offsets[end - 1] + 1) for start, end in spans]
    surfaces = _surfaces(text, cores)
    return [
        Token(
            kind=_classify(normalized[start:end]),
            value=normalized[start:end],
            raw=normalized[start:end],
            surface=surface,
        )
        for (start, end), surface in zip(spans, surfaces, strict=True)
    ]


def _surfaces(text: str, cores: list[tuple[int, int]]) -> tuple[str, ...]:
    """Восстановить исходную форму токенов: регистр и пунктуация вокруг ядра.

    Ядро токена — непрерывный участок исходного текста, из которого получено
    нормализованное значение. Соседние знаки препинания приклеиваются к токену:
    `готов,` и `заберите!` сохраняют запятую и восклицательный знак, а тире
    между словами (`— готов`) переходит к правому токену.
    """
    prefixes = [""] * len(cores)
    suffixes = [""] * len(cores)
    for index in range(len(cores) + 1):
        left_end = cores[index - 1][1] if index > 0 else 0
        right_start = cores[index][0] if index < len(cores) else len(text)
        head, middle, tail = _split_gap(text[left_end:right_start])
        has_left = index > 0
        has_right = index < len(cores)
        if head:
            if has_left:
                suffixes[index - 1] += head
            elif has_right:
                prefixes[index] += head
        if tail:
            if has_right:
                prefixes[index] += tail
            elif has_left:
                suffixes[index - 1] += tail
        if middle:
            if has_right:
                prefixes[index] = f"{middle} {prefixes[index]}"
            elif has_left:
                suffixes[index - 1] = f"{suffixes[index - 1]} {middle}"
    return tuple(
        " ".join(f"{prefix}{text[start:end]}{suffix}".split())
        for prefix, (start, end), suffix in zip(prefixes, cores, suffixes, strict=True)
    )


def _split_gap(gap: str) -> tuple[str, str, str]:
    """Разделить промежуток между токенами на голову, середину и хвост.

    Голова примыкает к левому токену, хвост — к правому, середина — знаки
    препинания между пробелами (тире в `слово — слово`).
    """
    if not gap:
        return "", "", ""
    first_space = next((index for index, char in enumerate(gap) if char.isspace()), None)
    if first_space is None:
        return "", "", gap
    last_space = (
        len(gap) - 1 - next(index for index, char in enumerate(reversed(gap)) if char.isspace())
    )
    return gap[:first_space], gap[first_space : last_space + 1].strip(), gap[last_space + 1 :]


def _classify(token: str) -> TokenKind:
    if token.isdigit():
        return TokenKind.NUMBER
    if token.isalpha():
        return TokenKind.LITERAL
    return TokenKind.MIXED
