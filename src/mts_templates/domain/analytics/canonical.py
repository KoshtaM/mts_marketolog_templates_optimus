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
)

_ENTITY = re.compile(
    r"(?P<url>(?:https?://|www\.)\S+)"
    r"|(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
    r"|(?P<phone>(?:\+7|\b8|\b7)[\d()\-]{8,14}\d)",
    re.IGNORECASE,
)


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
    """Токен нормализованного текста."""

    kind: TokenKind
    value: str
    raw: str = ""


@dataclass(frozen=True, slots=True)
class SignatureElement:
    """Элемент сигнатуры: литерал, числовая серия или слово-переменная.

    `limit` задаёт максимальное число слов для `%w{1,n}`; для литералов и чисел
    не используется.
    """

    kind: ElementKind
    value: str = ""
    limit: int = 1


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
    """Разбить текст на токены, выделив сущности на исходной строке."""
    tokens: list[Token] = []
    position = 0
    for match in _ENTITY.finditer(text):
        tokens.extend(_plain_tokens(normalize(text[position : match.start()], policy)))
        raw = match.group(0)
        tokens.append(Token(kind=TokenKind.ENTITY, value=normalize(raw, policy), raw=raw))
        position = match.end()
    tokens.extend(_plain_tokens(normalize(text[position:], policy)))
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
            elements.append(SignatureElement(kind=ElementKind.LITERAL, value=token.value))
        else:
            elements.append(SignatureElement(kind=ElementKind.WORD_VARIABLE))
        index += 1
    return CanonicalSignature(elements=tuple(elements), run_lengths=tuple(run_lengths))


def is_literal_only(elements: tuple[SignatureElement, ...]) -> bool:
    return all(element.kind is ElementKind.LITERAL for element in elements)


def _plain_tokens(normalized: str) -> list[Token]:
    return [
        Token(kind=_classify(token), value=token, raw=token)
        for token in normalized.split()
        if token
    ]


def _classify(token: str) -> TokenKind:
    if token.isdigit():
        return TokenKind.NUMBER
    if token.isalpha():
        return TokenKind.LITERAL
    return TokenKind.MIXED
