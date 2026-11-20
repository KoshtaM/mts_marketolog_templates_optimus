"""Нормализация текста: единая политика для матчинга и поиска кандидатов.

Политика по умолчанию: NFKC, нижний регистр, удаление пунктуации, схлопывание
пробелов. Свёртка `ё → е` и омоглифов по умолчанию выключена: это решение
принимает пользователь настройкой, а не алгоритм.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PUNCTUATION_KEEP = "keep"
PUNCTUATION_DELETE = "delete"
PUNCTUATION_SPACE = "space"
PUNCTUATION_POLICIES = (PUNCTUATION_KEEP, PUNCTUATION_DELETE, PUNCTUATION_SPACE)

_WHITESPACE = re.compile(r"\s+")
_INVISIBLE = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060]")
_PUNCTUATION = re.compile(r"[^\w\s]")

_QUOTES = str.maketrans(
    {
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
        "\xa0": " ",
    }
)

_HOMOGLYPHS = str.maketrans(
    {
        "a": "а",
        "c": "с",
        "e": "е",
        "h": "н",
        "k": "к",
        "m": "м",
        "o": "о",
        "p": "р",
        "t": "т",
        "x": "х",
        "y": "у",
        "b": "в",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizationPolicy:
    """Как приводить текст к сравнимому виду."""

    punctuation: str = PUNCTUATION_DELETE
    fold_yo: bool = False
    fold_homoglyphs: bool = False
    lowercase: bool = True

    def __post_init__(self) -> None:
        if self.punctuation not in PUNCTUATION_POLICIES:
            raise ValueError(f"Неизвестная политика пунктуации: {self.punctuation!r}")


DEFAULT_NORMALIZATION = NormalizationPolicy()
TEXT_NORMALIZATION = NormalizationPolicy(punctuation=PUNCTUATION_KEEP)


def normalize(text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION) -> str:
    """Привести текст к сравнимому виду по политике."""
    cleaned = _prepare(text, policy)
    if policy.punctuation == PUNCTUATION_SPACE:
        cleaned = _PUNCTUATION.sub(" ", cleaned)
    elif policy.punctuation == PUNCTUATION_DELETE:
        cleaned = _PUNCTUATION.sub("", cleaned)
    return _WHITESPACE.sub(" ", cleaned).strip()


def normalize_with_offsets(
    text: str, policy: NormalizationPolicy = DEFAULT_NORMALIZATION
) -> tuple[str, tuple[int, ...]]:
    """Нормализовать текст и вернуть индексы исходных символов.

    `offsets[i]` — позиция в исходной строке, из которой получен `result[i]`.
    Пробелы после схлопывания сохраняют индекс первого пробела серии.
    """
    pieces: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for index, char in enumerate(text):
        expanded = _prepare(char, policy)
        if not expanded:
            continue
        for piece in expanded:
            if piece.isspace():
                pending_space = bool(pieces)
                continue
            if pending_space:
                pieces.append(" ")
                offsets.append(index)
                pending_space = False
            for normalized_char in _apply_punctuation(piece, policy):
                if normalized_char.isspace():
                    pending_space = bool(pieces)
                    continue
                pieces.append(normalized_char)
                offsets.append(index)
    return "".join(pieces), tuple(offsets)


def normalize_text(text: str) -> str:
    """Нижний регистр, единые кавычки и тире, схлопнутые пробелы; пунктуация сохраняется."""
    return normalize(text, TEXT_NORMALIZATION)


def mask_phone(phone: str) -> str:
    """Маскировать номер для логов и UI: 79*****1234."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        return "***"
    return f"{digits[:2]}*****{digits[-4:]}"


def sender_key(sender: str, *, case_sensitive: bool = False) -> str:
    """Ключ сравнения имени отправителя.

    По умолчанию регистр не важен; шаблон с пустым отправителем — универсальный.
    """
    cleaned = sender.strip()
    return cleaned if case_sensitive else cleaned.casefold()


def _prepare(text: str, policy: NormalizationPolicy) -> str:
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = _INVISIBLE.sub("", cleaned).translate(_QUOTES)
    if policy.lowercase:
        cleaned = cleaned.casefold()
    if policy.fold_yo:
        cleaned = cleaned.replace("ё", "е")
    if policy.fold_homoglyphs:
        cleaned = cleaned.translate(_HOMOGLYPHS)
    return cleaned


def _apply_punctuation(text: str, policy: NormalizationPolicy) -> str:
    if policy.punctuation == PUNCTUATION_SPACE:
        return _PUNCTUATION.sub(" ", text)
    if policy.punctuation == PUNCTUATION_DELETE:
        return _PUNCTUATION.sub("", text)
    return text
