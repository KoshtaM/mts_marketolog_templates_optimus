"""Дрейф текста шаблона: сообщения изменились и образовали кандидата.

Сервис отвечает на вопрос «шаблон перестал подпадать, потому что текст
сообщений немного изменился?». Сравнение детерминированное и работает на
уровне токенов: литералы сравниваются точно после общей политики нормализации,
переменные `%w`/`%d` сводятся к базовому виду. Fuzzy-сравнений и ML нет.

Дрейф фиксируется, когда одновременно выполняются условия:

- зарегистрированный шаблон активен;
- за период под него не подпало ни одно сообщение;
- есть кандидат от того же отправителя;
- тексты шаблона и кандидата совпадают в большей части токенов.

Результат — подсказка человеку: шаблон мог устареть, а его сообщения
естественным образом собрались в кандидата. Автоматических решений сервис
не принимает.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from mts_templates.domain.analytics.activity import TemplateMetrics
from mts_templates.domain.analytics.analysis import CandidateGroup
from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    normalize,
    sender_key,
)
from mts_templates.domain.entities import SmsTemplate

# Тексты считаются близкими, если общая часть токенов даёт не меньше 60 %
# их суммарного числа. Порог намеренно мягкий: дрейф — подсказка, а не
# автоматическое решение.
MIN_SIMILARITY = Decimal("0.6")
# Два общих токена — минимум, чтобы «Код %d» и «Пароль %d» не считались
# дрейфом друг друга.
MIN_COMMON_TOKENS = 2

_VARIABLE = re.compile(r"%(?P<kind>[wd])(?:\+|\{\d+,\d+\})?")
_SIMILARITY_QUANT = Decimal("0.0001")


class DriftFragmentKind(StrEnum):
    """Роль фрагмента в сравнении текстов."""

    EQUAL = "equal"
    REMOVED = "removed"
    ADDED = "added"


@dataclass(frozen=True, slots=True)
class DriftFragment:
    """Фрагмент текста: общий, удалённый из шаблона или добавленный в кандидате."""

    kind: DriftFragmentKind
    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("Текст фрагмента дрейфа не может быть пустым")


@dataclass(frozen=True, slots=True)
class TemplateDrift:
    """Расхождение текста шаблона и кандидата, собранного из его сообщений.

    `template_fragments` — текст шаблона по частям (общие и удалённые),
    `candidate_fragments` — текст кандидата (общие и добавленные). По ним UI
    показывает, где именно изменился текст.
    """

    template_id: str
    candidate_id: str
    candidate_text: str
    similarity: Decimal
    template_fragments: tuple[DriftFragment, ...]
    candidate_fragments: tuple[DriftFragment, ...]
    removed: tuple[str, ...]
    added: tuple[str, ...]
    changed_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        if not self.template_id or not self.candidate_id:
            raise ValueError("Дрейф должен ссылаться на шаблон и кандидата")
        if not self.candidate_text.strip():
            raise ValueError("Текст кандидата дрейфа не может быть пустым")
        if not Decimal("0") <= self.similarity <= Decimal("1"):
            raise ValueError("similarity дрейфа должен быть в диапазоне 0..1")
        if self.changed_tokens < 1:
            raise ValueError("Дрейф должен содержать хотя бы одно изменение")
        if self.total_tokens < self.changed_tokens:
            raise ValueError("Число изменённых токенов больше общего числа")
        if not self.template_fragments or not self.candidate_fragments:
            raise ValueError("Дрейф должен содержать фрагменты обоих текстов")


@dataclass(frozen=True, slots=True)
class _Token:
    """Токен текста: литерал или переменная; `surface` — исходное написание."""

    kind: str
    value: str
    surface: str

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.value


def detect_template_drifts(
    metrics: Sequence[TemplateMetrics],
    candidates: Sequence[CandidateGroup],
    templates: Sequence[SmsTemplate],
    *,
    policy: NormalizationPolicy = DEFAULT_NORMALIZATION,
    sender_case_sensitive: bool = False,
    min_similarity: Decimal = MIN_SIMILARITY,
) -> tuple[TemplateDrift, ...]:
    """Найти шаблоны, чьи сообщения изменились и собрались в кандидата.

    Каждый шаблон и каждый кандидат участвуют не более чем в одном дрейфе:
    выбирается пара с наибольшей похожестью, затем с большим объёмом сообщений.
    """
    if not candidates:
        return ()

    by_id = {template.template_id: template for template in templates}
    candidate_tokens = {
        candidate.candidate_id: _tokenize(candidate.template_text, policy)
        for candidate in candidates
    }
    ranked: list[tuple[Decimal, int, str, str, TemplateDrift]] = []

    for item in metrics:
        if item.matched_messages != 0:
            continue
        template = by_id.get(item.template_id)
        if template is None or not template.active:
            continue
        template_tokens = _tokenize(template.text, policy)
        if not template_tokens:
            continue
        for candidate in candidates:
            if not _sender_matches(
                template.sender,
                candidate.senders,
                sender_case_sensitive=sender_case_sensitive,
            ):
                continue
            drift = _compare(
                template.template_id,
                candidate,
                template_tokens,
                candidate_tokens[candidate.candidate_id],
                min_similarity=min_similarity,
            )
            if drift is None:
                continue
            ranked.append(
                (
                    drift.similarity,
                    candidate.messages,
                    template.template_id,
                    candidate.candidate_id,
                    drift,
                )
            )

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2], row[3]))
    used_templates: set[str] = set()
    used_candidates: set[str] = set()
    drifts: list[TemplateDrift] = []
    for _similarity, _messages, template_id, candidate_id, drift in ranked:
        if template_id in used_templates or candidate_id in used_candidates:
            continue
        used_templates.add(template_id)
        used_candidates.add(candidate_id)
        drifts.append(drift)

    drifts.sort(key=lambda drift: drift.template_id)
    return tuple(drifts)


def _sender_matches(
    template_sender: str,
    candidate_senders: Sequence[str],
    *,
    sender_case_sensitive: bool,
) -> bool:
    """Отправитель кандидата совпадает с отправителем шаблона.

    Пустой отправитель шаблона — универсальный: подходит любой кандидат,
    но текст всё равно должен совпасть в большей части токенов.
    """
    keys = {
        sender_key(sender, case_sensitive=sender_case_sensitive)
        for sender in candidate_senders
        if sender.strip()
    }
    if not keys:
        return False
    if not template_sender.strip():
        return True
    return sender_key(template_sender, case_sensitive=sender_case_sensitive) in keys


def _compare(
    template_id: str,
    candidate: CandidateGroup,
    template_tokens: tuple[_Token, ...],
    candidate_tokens: tuple[_Token, ...],
    *,
    min_similarity: Decimal,
) -> TemplateDrift | None:
    """Сравнить два текста и вернуть дрейф, если они достаточно близки."""
    if not candidate_tokens:
        return None
    operations = _diff(template_tokens, candidate_tokens)
    common = sum(1 for kind, _left, _right in operations if kind is DriftFragmentKind.EQUAL)
    if common < MIN_COMMON_TOKENS:
        return None
    if common == len(template_tokens) == len(candidate_tokens):
        return None

    similarity = (
        Decimal(common * 2) / Decimal(len(template_tokens) + len(candidate_tokens))
    ).quantize(_SIMILARITY_QUANT)
    if similarity < min_similarity:
        return None

    removed = tuple(
        left.surface
        for kind, left, _right in operations
        if kind is DriftFragmentKind.REMOVED and left
    )
    added = tuple(
        right.surface
        for kind, _left, right in operations
        if kind is DriftFragmentKind.ADDED and right
    )
    return TemplateDrift(
        template_id=template_id,
        candidate_id=candidate.candidate_id,
        candidate_text=candidate.template_text,
        similarity=similarity,
        template_fragments=_fragments(operations, template_side=True),
        candidate_fragments=_fragments(operations, template_side=False),
        removed=removed,
        added=added,
        changed_tokens=len(removed) + len(added),
        total_tokens=max(len(template_tokens), len(candidate_tokens)),
    )


def _diff(
    left: tuple[_Token, ...],
    right: tuple[_Token, ...],
) -> list[tuple[DriftFragmentKind, _Token | None, _Token | None]]:
    """Выровнять токены по LCS и вернуть операции сравнения.

    При равном выборе предпочтение отдаётся удалению: тогда замена слова
    показывается как «было — стало», а не как случайная перестановка.
    """
    rows, columns = len(left), len(right)
    lengths = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows - 1, -1, -1):
        for column in range(columns - 1, -1, -1):
            if left[row].key == right[column].key:
                lengths[row][column] = lengths[row + 1][column + 1] + 1
            else:
                lengths[row][column] = max(lengths[row + 1][column], lengths[row][column + 1])

    operations: list[tuple[DriftFragmentKind, _Token | None, _Token | None]] = []
    row = column = 0
    while row < rows and column < columns:
        if left[row].key == right[column].key:
            operations.append((DriftFragmentKind.EQUAL, left[row], right[column]))
            row += 1
            column += 1
        elif lengths[row + 1][column] >= lengths[row][column + 1]:
            operations.append((DriftFragmentKind.REMOVED, left[row], None))
            row += 1
        else:
            operations.append((DriftFragmentKind.ADDED, None, right[column]))
            column += 1
    while row < rows:
        operations.append((DriftFragmentKind.REMOVED, left[row], None))
        row += 1
    while column < columns:
        operations.append((DriftFragmentKind.ADDED, None, right[column]))
        column += 1
    return operations


def _fragments(
    operations: Sequence[tuple[DriftFragmentKind, _Token | None, _Token | None]],
    *,
    template_side: bool,
) -> tuple[DriftFragment, ...]:
    """Склеить соседние операции в читаемые фрагменты одной стороны."""
    fragments: list[DriftFragment] = []
    for kind, left, right in operations:
        side_token = left if template_side else right
        if side_token is None or kind is _other_side(template_side):
            continue
        if fragments and fragments[-1].kind is kind:
            previous = fragments[-1]
            fragments[-1] = DriftFragment(kind=kind, text=f"{previous.text} {side_token.surface}")
        else:
            fragments.append(DriftFragment(kind=kind, text=side_token.surface))
    return tuple(fragments)


def _other_side(template_side: bool) -> DriftFragmentKind:
    """Операция, которая не относится к стороне: добавление — не в шаблоне и наоборот."""
    return DriftFragmentKind.ADDED if template_side else DriftFragmentKind.REMOVED


def _tokenize(text: str, policy: NormalizationPolicy) -> tuple[_Token, ...]:
    """Разбить текст шаблона на токены, сохранив исходное написание.

    Переменные `%w{1,n}` и `%d+` сводятся к базовому виду `w`/`d`: диапазон
    не влияет на то, изменился ли постоянный текст сообщения.
    """
    tokens: list[_Token] = []
    for word in text.split():
        position = 0
        for match in _VARIABLE.finditer(word):
            _append_literals(tokens, word[position : match.start()], policy)
            kind = str(match.group("kind"))
            tokens.append(_Token(kind=kind, value=kind, surface=match.group(0)))
            position = match.end()
        _append_literals(tokens, word[position:], policy)
    return tuple(tokens)


def _append_literals(tokens: list[_Token], raw: str, policy: NormalizationPolicy) -> None:
    normalized = normalize(raw, policy)
    if not normalized:
        return
    parts = normalized.split()
    if len(parts) == 1:
        tokens.append(_Token(kind="literal", value=parts[0], surface=raw.strip()))
        return
    for part in parts:
        tokens.append(_Token(kind="literal", value=part, surface=part))
