"""Детерминированный поиск шаблонов-кандидатов (MTS-CSG).

Пайплайн: нормализация → токенизация → каноническая сигнатура → точная
группировка по `(отправитель, сигнатура)` → эмиссия `%d`/`%d{1,n}`/`%d+`/`%w`
→ слияние одного литерального участка в `%w{1,n}` (только с подтверждением)
→ линтер → проверка полным совпадением → защита от чужих совпадений.

Нормализация нужна только для сравнения. В текст шаблона литералы попадают в
исходной форме (`SignatureElement.surface`): регистр, пунктуация и тире
сохраняются, поэтому кандидат не превращается в нижний регистр.

Никакой нечёткой близости: группы строятся только по точному тождеству
сигнатуры. Слияние литералов — единственное обобщение, и оно всегда требует
ручного подтверждения.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from mts_templates.domain.analytics.canonical import (
    CanonicalSignature,
    ElementKind,
    SignatureElement,
    signature_of,
)
from mts_templates.domain.analytics.normalization import (
    DEFAULT_NORMALIZATION,
    NormalizationPolicy,
    sender_key,
)
from mts_templates.domain.analytics.template_syntax import (
    MAX_GROUP_WORDS,
    TemplatePattern,
    compile_pattern,
    normalize_for_matching,
)
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.errors import TemplateSyntaxError
from mts_templates.domain.value_objects import Money, Operator

_VARIABLE = re.compile(
    r"%(?:(?P<kind>[wd])(?P<quantifier>\+|\{(?P<min>\d+),(?P<max>\d+)\})?|(?P<unknown>[^\W\d_]))"
)
_LETTER = re.compile(r"[A-Za-zА-Яа-яЁё]")


class CandidateStatus(StrEnum):
    """Статус кандидата после проверки."""

    AUTO_VALIDATED = "auto_validated"
    NEEDS_HUMAN_APPROVAL = "needs_human_approval"
    WARNING_SAVED = "warning_saved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CsgConfig:
    """Параметры поиска кандидатов."""

    normalization: NormalizationPolicy = DEFAULT_NORMALIZATION
    sender_case_sensitive: bool = False
    min_support: int = 5
    min_segments: int = 5
    min_literal_length: int = 8
    max_w_words: int = MAX_GROUP_WORDS
    max_d_words: int = MAX_GROUP_WORDS
    max_foreign_matches: int = 0
    merge_literal_slots: bool = True
    max_word_slots_per_merge: int = MAX_GROUP_WORDS
    max_literal_cardinality: int = 3
    max_tail_depth: int = 4

    def __post_init__(self) -> None:
        if self.min_support < 1:
            raise ValueError("min_support должен быть не меньше 1")
        if self.min_segments < 1:
            raise ValueError("min_segments должен быть не меньше 1")
        if self.max_w_words < 1 or self.max_d_words < 1:
            raise ValueError("Лимиты групповых переменных должны быть положительными")
        if self.max_word_slots_per_merge < 1:
            raise ValueError("max_word_slots_per_merge должен быть положительным")
        if self.max_literal_cardinality < 1:
            raise ValueError("max_literal_cardinality должен быть положительным")
        if self.max_tail_depth < 0:
            raise ValueError("max_tail_depth не может быть отрицательным")


@dataclass(frozen=True, slots=True)
class Issue:
    """Нарушение правил шаблона МТС."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SignatureGroup:
    """Сообщения одного отправителя с одинаковой канонической сигнатурой."""

    sender: str
    sender_key: str
    signature: CanonicalSignature
    messages: tuple[SmsMessage, ...]
    run_lengths: tuple[tuple[int, ...], ...] = ()
    _message_ids: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_message_ids", frozenset(message.message_id for message in self.messages)
        )

    @property
    def key(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return self.sender_key, self.signature.key

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def segments(self) -> int:
        return sum(message.segments for message in self.messages)

    @property
    def cost(self) -> Money:
        return sum((message.cost for message in self.messages), Money.zero())

    @property
    def operators(self) -> tuple[Operator, ...]:
        return tuple(
            sorted({message.operator for message in self.messages}, key=lambda op: op.value)
        )

    @property
    def raw_senders(self) -> tuple[str, ...]:
        return tuple(sorted({message.sender for message in self.messages}))

    @property
    def message_ids(self) -> frozenset[str]:
        return self._message_ids

    @property
    def literal_key(self) -> tuple[str, ...]:
        return tuple(
            element.value
            for element in self.signature.elements
            if element.kind is ElementKind.LITERAL
        )

    @property
    def variable_skeleton(self) -> tuple[str, ...]:
        return tuple(
            element.kind.value
            for element in self.signature.elements
            if element.kind is not ElementKind.LITERAL
        )


@dataclass(frozen=True, slots=True)
class MergedSignature:
    """Обобщённая группа: литеральные участки заменены на `%w`/`%w{1,n}`."""

    sender: str
    sender_key: str
    template_text: str
    elements: tuple[SignatureElement, ...]
    groups: tuple[SignatureGroup, ...]
    word_min: int
    word_max: int

    @property
    def messages(self) -> tuple[SmsMessage, ...]:
        return tuple(
            sorted(
                (message for group in self.groups for message in group.messages),
                key=lambda message: message.message_id,
            )
        )

    @property
    def message_count(self) -> int:
        return sum(group.message_count for group in self.groups)

    @property
    def segments(self) -> int:
        return sum(group.segments for group in self.groups)

    @property
    def cost(self) -> Money:
        return sum((group.cost for group in self.groups), Money.zero())

    @property
    def operators(self) -> tuple[Operator, ...]:
        return tuple(
            sorted({op for group in self.groups for op in group.operators}, key=lambda op: op.value)
        )

    @property
    def raw_senders(self) -> tuple[str, ...]:
        return tuple(sorted({sender for group in self.groups for sender in group.raw_senders}))


@dataclass(frozen=True, slots=True)
class CsgCandidate:
    """Проверенный кандидат или отклонённая группа."""

    template_text: str
    sender: str
    sender_key: str
    messages: tuple[SmsMessage, ...]
    status: CandidateStatus
    warnings: tuple[str, ...]
    foreign_matches: int
    confidence: Decimal
    coverage: Decimal
    groups: tuple[SignatureGroup, ...] = ()

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def segments(self) -> int:
        return sum(message.segments for message in self.messages)

    @property
    def cost(self) -> Money:
        return sum((message.cost for message in self.messages), Money.zero())

    @property
    def operators(self) -> tuple[Operator, ...]:
        return tuple(
            sorted({message.operator for message in self.messages}, key=lambda op: op.value)
        )

    @property
    def raw_senders(self) -> tuple[str, ...]:
        return tuple(sorted({message.sender for message in self.messages}))


@dataclass(frozen=True, slots=True)
class CsgExtraction:
    """Результат детерминированного поиска."""

    candidates: tuple[CsgCandidate, ...]
    rejected: tuple[CsgCandidate, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def merged_candidates(self) -> int:
        return sum(
            1
            for candidate in self.candidates
            if candidate.status is CandidateStatus.NEEDS_HUMAN_APPROVAL
        )


@dataclass(slots=True)
class _Accumulator:
    sender: str
    sender_key: str
    elements: tuple[SignatureElement, ...]
    messages: list[SmsMessage] = field(default_factory=list)
    run_lengths: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    surfaces: dict[int, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))


def build_signature_groups(
    messages: Iterable[SmsMessage], config: CsgConfig
) -> tuple[SignatureGroup, ...]:
    """Сгруппировать сообщения по отправителю и канонической сигнатуре."""
    accumulators: dict[tuple[str, tuple[tuple[str, str], ...]], _Accumulator] = {}
    for message in messages:
        if message.segments <= 0 or not message.text.strip():
            continue
        signature = signature_of(message.text, config.normalization)
        if not signature.elements:
            continue
        key = (
            sender_key(message.sender, case_sensitive=config.sender_case_sensitive),
            signature.key,
        )
        accumulator = accumulators.get(key)
        if accumulator is None:
            accumulator = _Accumulator(
                sender=message.sender,
                sender_key=key[0],
                elements=signature.elements,
            )
            accumulators[key] = accumulator
        accumulator.messages.append(message)
        for index, element in enumerate(signature.elements):
            if element.surface:
                accumulator.surfaces[index][element.surface] += 1
        for slot, length in enumerate(signature.run_lengths):
            accumulator.run_lengths[slot].add(length)

    groups: list[SignatureGroup] = []
    for accumulator in accumulators.values():
        signature = CanonicalSignature(elements=_surface_elements(accumulator))
        slots = signature.numeric_slots
        run_lengths = tuple(
            tuple(sorted(accumulator.run_lengths.get(index, {1}))) for index in range(slots)
        )
        groups.append(
            SignatureGroup(
                sender=accumulator.sender,
                sender_key=accumulator.sender_key,
                signature=signature,
                messages=tuple(accumulator.messages),
                run_lengths=run_lengths,
            )
        )
    groups.sort(key=lambda group: (-group.message_count, group.sender_key, group.signature.key))
    return tuple(groups)


def _surface_elements(accumulator: _Accumulator) -> tuple[SignatureElement, ...]:
    """Элементы группы с исходной формой литералов, выбранной по большинству."""
    return tuple(
        SignatureElement(
            kind=element.kind,
            value=element.value,
            limit=element.limit,
            surface=(
                _voted_surface(accumulator.surfaces.get(index, Counter()).items())
                if element.kind is ElementKind.LITERAL
                else ""
            ),
        )
        for index, element in enumerate(accumulator.elements)
    )


def _voted_surface(votes: Iterable[tuple[str, int]]) -> str:
    """Выбрать исходную форму литерала: чаще всего, при равенстве — первая по алфавиту.

    Знаки `%` и `|` из поверхности исключаются: в тексте шаблона они начинают
    переменную и запрещены правилами МТС.
    """
    counts: Counter[str] = Counter()
    for surface, weight in votes:
        if surface and "%" not in surface and "|" not in surface:
            counts[surface] += weight
    if not counts:
        return ""
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def emit_template(group: SignatureGroup, config: CsgConfig) -> tuple[str, tuple[Issue, ...]]:
    """Собрать текст шаблона из сигнатуры и наблюдаемых длин числовых серий."""
    return _emit_elements(group.signature.elements, group.run_lengths, config)


def lint_template(text: str, config: CsgConfig) -> tuple[Issue, ...]:
    """Проверить шаблон по правилам МТС; вернуть список нарушений."""
    issues: list[Issue] = []
    if not text.strip():
        return (Issue("empty", "Текст шаблона пуст"),)
    if "|" in text:
        issues.append(Issue("pipe", "Символ `|` в шаблоне запрещён"))
    if "%" in _VARIABLE.sub("", text):
        issues.append(Issue("unknown_variable", "Неизвестная переменная в шаблоне"))

    sequence: list[str | tuple[str, bool]] = []
    literals: list[str] = []
    for raw_word in text.split():
        pieces, word_issues = _split_template_word(raw_word, config)
        issues.extend(word_issues)
        for piece in pieces:
            sequence.append(piece)
            if isinstance(piece, str):
                literals.append(piece)
    issues.extend(_adjacent_group_issues(sequence))

    literal_text = "".join(literals)
    if not any(char.isalnum() for char in literal_text):
        issues.append(Issue("no_literal", "Шаблон должен содержать постоянный текст"))
    elif not _LETTER.search(literal_text):
        issues.append(
            Issue("non_letter_literal", "Постоянный текст должен содержать кириллицу или латиницу")
        )
    if len(literal_text) < config.min_literal_length:
        issues.append(
            Issue(
                "short_literal",
                f"Постоянный текст короче {config.min_literal_length} символов",
            )
        )
    return tuple(issues)


class _Normalizer:
    """Кэш нормализованных текстов: одна нормализация на уникальный текст."""

    __slots__ = ("_cache", "_policy")

    def __init__(self, policy: NormalizationPolicy) -> None:
        self._policy = policy
        self._cache: dict[str, str] = {}

    def __call__(self, text: str) -> str:
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        normalized = normalize_for_matching(text, self._policy)
        self._cache[text] = normalized
        return normalized


def count_foreign_matches(
    template_text: str,
    own_message_ids: frozenset[str],
    candidates: Iterable[SignatureGroup],
    config: CsgConfig,
    *,
    limit: int | None = None,
    normalizer: _Normalizer | None = None,
) -> int:
    """Сколько сообщений вне группы подпадает под шаблон.

    `candidates` — только те группы, которые могут совпасть по литералам;
    проверка останавливается, как только превышен `limit`. Группы, которые
    шаблон покрывает целиком, чужими не считаются: это тот же шаблон.
    """
    try:
        pattern = compile_pattern(template_text, config.normalization)
    except TemplateSyntaxError:
        return 0
    matches, _ = _scan_foreign(
        pattern,
        own_message_ids,
        candidates,
        config,
        limit,
        normalizer or _Normalizer(config.normalization),
    )
    return matches


def _scan_foreign(
    pattern: TemplatePattern,
    own_message_ids: frozenset[str],
    candidates: Iterable[SignatureGroup],
    config: CsgConfig,
    limit: int | None,
    normalizer: _Normalizer,
) -> tuple[int, tuple[SignatureGroup, ...]]:
    matches = 0
    absorbed: list[SignatureGroup] = []
    for group in candidates:
        if group.message_ids <= own_message_ids:
            continue
        # Внутри группы литералы одинаковы; различаются только длины числовых
        # серий. Если все серии однозначны, достаточно проверить одно сообщение.
        stable = all(len(lengths) <= 1 for lengths in group.run_lengths)
        first = group.messages[0]
        first_matches = pattern.fullmatch(normalizer(first.text))
        if not first_matches and stable:
            continue
        if stable:
            hits = [
                message for message in group.messages if message.message_id not in own_message_ids
            ]
        else:
            hits = [
                message
                for message in group.messages
                if message.message_id not in own_message_ids
                and pattern.fullmatch(normalizer(message.text))
            ]
        if not hits:
            continue
        if len(hits) == group.message_count:
            absorbed.append(group)
            continue
        matches += len(hits)
        if limit is not None and matches > limit:
            return matches, tuple(absorbed)
    return matches, tuple(absorbed)


def _merge_messages(
    own: Sequence[SmsMessage], absorbed: Sequence[SignatureGroup]
) -> tuple[SmsMessage, ...]:
    """Сообщения кандидата вместе с группами, которые шаблон покрывает целиком."""
    messages = list(own)
    seen = {message.message_id for message in own}
    for group in absorbed:
        for message in group.messages:
            if message.message_id in seen:
                continue
            seen.add(message.message_id)
            messages.append(message)
    return tuple(messages)


def merge_signature_groups(
    groups: Sequence[SignatureGroup], config: CsgConfig
) -> tuple[MergedSignature, ...]:
    """Обобщить литеральные участки сигнатур в `%w`/`%w{1,n}`.

    Группы объединяются по «скелету» сигнатуры: одинаковая последовательность
    участков (литералы, числовые серии, слова-переменные) у одного отправителя.
    Варьирующиеся литеральные участки заменяются переменной, если внутри участка
    остаётся неизменный префикс или суффикс: `г пермь пермская` и
    `г киров гостиный` дают `г %w{1,3}`, а `возьмите паспорт` и
    `возьмите паспорт DOCTORLIGHT` не обобщаются — у варианта пустая середина.

    Одиночный варьирующийся участок обобщается только при числе вариантов больше
    `max_literal_cardinality`: пары вроде «пополнение»/«списание» остаются
    разными шаблонами. Результат всегда требует подтверждения человеком.
    """
    if not config.merge_literal_slots:
        return ()

    clusters: dict[tuple[str, tuple[str, ...]], list[_Unit]] = defaultdict(list)
    for group in groups:
        unit = _unit_of(group)
        clusters[(group.sender_key, _skeleton(unit.elements))].append(unit)

    merged: dict[str, MergedSignature] = {}
    for (sender_key_value, _), cluster in clusters.items():
        if len(cluster) < 2:
            continue
        pending: list[tuple[Sequence[_Unit], int]] = [(cluster, 0)]
        while pending:
            units, depth = pending.pop()
            for bucket, bucket_depth in _generalized_buckets(units, config, min_depth=depth):
                item = _merged_signature(bucket, sender_key_value, config)
                if item is None:
                    if bucket_depth < config.max_tail_depth:
                        pending.append((bucket, bucket_depth + 1))
                    continue
                # Одинаковый текст может выйти из разных скелетов: оставляем
                # самое крупное объединение — оно покрывает больше сообщений.
                existing = merged.get(item.template_text)
                if existing is None or item.message_count > existing.message_count:
                    merged[item.template_text] = item
    return tuple(
        sorted(merged.values(), key=lambda item: (-item.message_count, item.template_text))
    )


_LITERAL_SLOT = "literal"
_NUMBER_SLOT = "number"
_WORD_SLOT = "word"


@dataclass(frozen=True, slots=True)
class _Slot:
    """Участок сигнатуры: подряд идущие элементы одного вида."""

    kind: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _SlotPattern:
    """Обобщение литерального участка.

    Участок превращается в `префикс %w якорь %w суффикс`: общий префикс,
    общий суффикс и общий внутренний токен («якорь», например `специалист`)
    остаются литералами, между ними — переменные.
    """

    prefix: tuple[str, ...]
    suffix: tuple[str, ...]
    middles: frozenset[tuple[str, ...]]
    anchor: str | None = None
    left_limit: int = 0
    right_limit: int = 0

    @property
    def limits(self) -> tuple[int, ...]:
        return tuple(value for value in (self.left_limit, self.right_limit) if value > 0)

    @property
    def word_limit(self) -> int:
        return max(self.limits, default=1)


@dataclass(frozen=True, slots=True)
class _Unit:
    """Сигнатура с сообщениями: исходная группа или уже обобщённый кандидат."""

    sender: str
    sender_key: str
    elements: tuple[SignatureElement, ...]
    run_lengths: tuple[tuple[int, ...], ...]
    groups: tuple[SignatureGroup, ...]

    @property
    def message_count(self) -> int:
        return sum(group.message_count for group in self.groups)

    @property
    def segments(self) -> int:
        return sum(group.segments for group in self.groups)


class _ForeignIndex:
    """Индекс групп для быстрой проверки чужих совпадений.

    Полное совпадение привязано к началу текста: если шаблон начинается с
    литерала, подойти может только группа с тем же первым литералом.
    """

    def __init__(self, groups: Iterable[SignatureGroup]) -> None:
        self._by_sender: dict[str, list[SignatureGroup]] = defaultdict(list)
        self._by_first_literal: dict[tuple[str, str], list[SignatureGroup]] = defaultdict(list)
        for group in groups:
            self._by_sender[group.sender_key].append(group)
            first = group.signature.elements[0]
            if first.kind is ElementKind.LITERAL:
                self._by_first_literal[(group.sender_key, first.value)].append(group)

    def pool(
        self, sender_key_value: str, elements: Sequence[SignatureElement]
    ) -> Sequence[SignatureGroup]:
        first = elements[0] if elements else None
        if first is not None and first.kind is ElementKind.LITERAL:
            return self._by_first_literal.get((sender_key_value, first.value), ())
        return self._by_sender.get(sender_key_value, ())


def _unit_of(group: SignatureGroup) -> _Unit:
    return _Unit(
        sender=group.sender,
        sender_key=group.sender_key,
        elements=group.signature.elements,
        run_lengths=group.run_lengths,
        groups=(group,),
    )


def _slot_kind(kind: ElementKind) -> str:
    if kind is ElementKind.LITERAL:
        return _LITERAL_SLOT
    if kind is ElementKind.NUMBER_RUN:
        return _NUMBER_SLOT
    return _WORD_SLOT


def _slots(elements: Sequence[SignatureElement]) -> tuple[_Slot, ...]:
    slots: list[_Slot] = []
    index = 0
    while index < len(elements):
        kind = _slot_kind(elements[index].kind)
        end = index + 1
        if kind is not _NUMBER_SLOT:
            while end < len(elements) and _slot_kind(elements[end].kind) == kind:
                end += 1
        slots.append(_Slot(kind=kind, start=index, end=end))
        index = end
    return tuple(slots)


def _skeleton(elements: Sequence[SignatureElement]) -> tuple[str, ...]:
    return tuple(slot.kind for slot in _slots(elements))


def _generalized_buckets(
    units: Sequence[_Unit], config: CsgConfig, *, min_depth: int = 0
) -> list[tuple[list[_Unit], int]]:
    """Разбить кластер на группы, которые можно обобщить одинаково.

    Кластер делится по последним словам, когда сигнатура заканчивается
    литералом: `… ваши результаты готовы` и `… ваши результаты готовы
    DOCTORLIGHT` — разные шаблоны, а не одна переменная. Если участок не
    обобщается из-за смеси семейств, хвостовой якорь углубляется.
    """
    slots = _skeleton(units[0].elements)
    literal_slots = [index for index, kind in enumerate(slots) if kind is _LITERAL_SLOT]
    if not literal_slots:
        return []
    tail_allowed = slots[-1] is _LITERAL_SLOT

    pending: list[tuple[list[_Unit], int]] = [(list(units), min_depth)]
    result: list[tuple[list[_Unit], int]] = []
    while pending:
        bucket, depth = pending.pop()
        if len(bucket) < 2:
            continue
        if tail_allowed and depth == 0:
            # Мало вариантов последнего слова — это разные семейства
            # (`… паспорт` и `… паспорт DOCTORLIGHT`), а не одна переменная.
            tokens = {unit.elements[-1].value for unit in bucket}
            if 2 <= len(tokens) <= config.max_literal_cardinality:
                parts = _partition(bucket, (), tail=1)
                if len(parts) > 1:
                    pending.extend((part, 1) for part in parts)
                    continue
        patterns = {
            index: pattern
            for index in literal_slots
            if (pattern := _slot_pattern(_slot_values(bucket, index), config)) is not None
        }
        qualifying = _qualifying_slots(patterns, config)
        if not qualifying:
            if tail_allowed and depth < config.max_tail_depth:
                parts = _partition(bucket, (), tail=depth + 1)
                if len(parts) > 1:
                    pending.extend((part, depth + 1) for part in parts)
            continue
        fixed = [index for index in literal_slots if index not in qualifying]
        parts = _partition(bucket, fixed, tail=depth)
        if len(parts) > 1:
            pending.extend((part, depth) for part in parts)
            continue
        result.append((bucket, depth))
    return result


def _qualifying_slots(
    patterns: dict[int, _SlotPattern], config: CsgConfig
) -> dict[int, _SlotPattern]:
    """Участки, которые действительно обобщаются.

    Одиночный участок с малым числом вариантов оставляем литералом: это разные
    шаблоны, а не переменная.
    """
    if len(patterns) == 1:
        (pattern,) = patterns.values()
        if len(pattern.middles) <= config.max_literal_cardinality:
            return {}
    return dict(patterns)


def _slot_values(units: Sequence[_Unit], index: int) -> tuple[tuple[str, ...], ...]:
    """Значения литерального участка по всем единицам; границы — у каждой свои."""
    return tuple(_slot_value(unit, index) for unit in units)


def _slot_value(unit: _Unit, index: int) -> tuple[str, ...]:
    slot = _slots(unit.elements)[index]
    return tuple(element.value for element in unit.elements[slot.start : slot.end])


def _slot_pattern(values: Sequence[tuple[str, ...]], config: CsgConfig) -> _SlotPattern | None:
    """Обобщение участка с сохранением общих частей.

    Переменными становятся только середины между общим префиксом, общим
    суффиксом и общим внутренним токеном: `г пермь пермская специалист` и
    `г киров специалист` дают `г %w специалист`.
    """
    if len(set(values)) < 2:
        return None
    shortest = min(len(value) for value in values)
    prefix_length = 0
    while prefix_length < shortest and len({value[prefix_length] for value in values}) == 1:
        prefix_length += 1
    suffix_length = 0
    while (
        suffix_length < shortest - prefix_length
        and len({value[len(value) - 1 - suffix_length] for value in values}) == 1
    ):
        suffix_length += 1
    middles = frozenset(
        tuple(value[prefix_length : len(value) - suffix_length if suffix_length else len(value)])
        for value in values
    )
    if len(middles) < 2 or any(not middle for middle in middles):
        return None
    if max(len(middle) for middle in middles) > config.max_word_slots_per_merge:
        return None
    anchor, left_limit, right_limit = _anchor_of(middles)
    prefix = values[0][:prefix_length]
    suffix = values[0][len(values[0]) - suffix_length :] if suffix_length else ()
    return _SlotPattern(
        prefix=prefix,
        suffix=suffix,
        middles=middles,
        anchor=anchor,
        left_limit=left_limit,
        right_limit=right_limit,
    )


def _anchor_of(middles: frozenset[tuple[str, ...]]) -> tuple[str | None, int, int]:
    """Общий токен середины: самый устойчивый по позиции; вернёт (якорь, слева, справа).

    Якорь годится, только если в каждой середине перед ним и после него есть
    хотя бы одно слово: переменные `%w` не могут быть пустыми.
    """
    common: set[str] = set.intersection(*(set(middle) for middle in middles))
    best: tuple[tuple[int, str], str, int, int] | None = None
    for token in common:
        positions = [middle.index(token) for middle in middles]
        if min(positions) < 1 or any(
            position > len(middle) - 2 for middle, position in zip(middles, positions, strict=True)
        ):
            continue
        key = (max(positions) - min(positions), token)
        if best is None or key < best[0]:
            best = (key, token, min(positions), max(positions))
    if best is None:
        return None, 0, max(len(middle) for middle in middles)
    left = max(middle.index(best[1]) for middle in middles)
    right = max(len(middle) - 1 - middle.index(best[1]) for middle in middles)
    return best[1], left, right


def _partition(
    units: Sequence[_Unit], indexes: Sequence[int], *, tail: int = 0
) -> list[list[_Unit]]:
    """Разделить единицы по значениям литеральных участков.

    `tail` добавляет к ключу последние слова текста: хвостовые варианты вроде
    `… готовы` и `… готовы DOCTORLIGHT` остаются разными шаблонами.
    """
    buckets: dict[tuple[Any, ...], list[_Unit]] = defaultdict(list)
    for unit in units:
        slots = _slots(unit.elements)
        key: tuple[Any, ...] = tuple(
            tuple(element.value for element in unit.elements[slots[index].start : slots[index].end])
            for index in indexes
        )
        if tail:
            key = (*key, *(element.value for element in unit.elements[-tail:]))
        buckets[key].append(unit)
    return list(buckets.values())


def _merged_signature(
    bucket: Sequence[_Unit], sender_key_value: str, config: CsgConfig
) -> MergedSignature | None:
    patterns: dict[int, _SlotPattern] = {}
    skeleton = _skeleton(bucket[0].elements)
    for index, kind in enumerate(skeleton):
        if kind is not _LITERAL_SLOT:
            continue
        pattern = _slot_pattern(_slot_values(bucket, index), config)
        if pattern is not None:
            patterns[index] = pattern
    qualifying = _qualifying_slots(patterns, config)
    if not qualifying:
        return None
    if sum(unit.message_count for unit in bucket) < config.min_support:
        return None
    if sum(unit.segments for unit in bucket) < config.min_segments:
        return None

    elements, run_lengths = _merged_elements(bucket, qualifying)
    template_text, issues = _emit_elements(elements, run_lengths, config)
    if issues or "%w" not in template_text:
        return None
    groups = tuple(group for unit in bucket for group in unit.groups)
    limits = [limit for pattern in qualifying.values() for limit in pattern.limits]
    return MergedSignature(
        sender=bucket[0].sender,
        sender_key=sender_key_value,
        template_text=template_text,
        elements=elements,
        groups=groups,
        word_min=min(limits, default=1),
        word_max=max(limits, default=1),
    )


def _merged_elements(
    bucket: Sequence[_Unit],
    qualifying: dict[int, _SlotPattern],
) -> tuple[tuple[SignatureElement, ...], tuple[tuple[int, ...], ...]]:
    sample = bucket[0].elements
    elements: list[SignatureElement] = []
    run_lengths: list[tuple[int, ...]] = []
    numeric_index = 0
    for index, slot in enumerate(_slots(sample)):
        if slot.kind is _LITERAL_SLOT:
            pattern = qualifying.get(index)
            if pattern is None:
                elements.extend(_kept_slot_elements(bucket, index))
                continue
            elements.extend(_pattern_elements(bucket, index, pattern))
            continue
        if slot.kind is _NUMBER_SLOT:
            collected: set[int] = set()
            for unit in bucket:
                collected.update(unit.run_lengths[numeric_index])
            run_lengths.append(tuple(sorted(collected)))
            numeric_index += 1
            elements.extend(sample[slot.start : slot.end])
            continue
        elements.extend(sample[slot.start : slot.end])
    return tuple(elements), tuple(run_lengths)


def _slot_of(unit: _Unit, index: int) -> _Slot:
    return _slots(unit.elements)[index]


def _literal(value: str, votes: Iterable[tuple[str, int]]) -> SignatureElement:
    return SignatureElement(
        kind=ElementKind.LITERAL,
        value=value,
        surface=_voted_surface(votes) or value,
    )


def _kept_slot_elements(units: Sequence[_Unit], index: int) -> tuple[SignatureElement, ...]:
    """Литеральный участок, который остаётся неизменным: значения и форма из групп."""
    slots = [_slot_of(unit, index) for unit in units]
    sample = units[0].elements
    slot = slots[0]
    return tuple(
        _literal(
            sample[slot.start + offset].value,
            (
                (unit.elements[slots[position].start + offset].surface, unit.message_count)
                for position, unit in enumerate(units)
            ),
        )
        for offset in range(slot.end - slot.start)
    )


def _pattern_elements(
    units: Sequence[_Unit], index: int, pattern: _SlotPattern
) -> tuple[SignatureElement, ...]:
    elements: list[SignatureElement] = []
    elements.extend(_aligned_slot_elements(units, index, pattern.prefix, from_end=False))
    if pattern.left_limit > 0:
        elements.append(SignatureElement(kind=ElementKind.WORD_VARIABLE, limit=pattern.left_limit))
    if pattern.anchor is not None:
        elements.append(_literal(pattern.anchor, _anchor_votes(units, index, pattern.anchor)))
    if pattern.right_limit > 0:
        elements.append(SignatureElement(kind=ElementKind.WORD_VARIABLE, limit=pattern.right_limit))
    elements.extend(_aligned_slot_elements(units, index, pattern.suffix, from_end=True))
    return tuple(elements)


def _aligned_slot_elements(
    units: Sequence[_Unit],
    index: int,
    values: Sequence[str],
    *,
    from_end: bool,
) -> tuple[SignatureElement, ...]:
    result: list[SignatureElement] = []
    for offset, value in enumerate(values):
        votes: list[tuple[str, int]] = []
        for unit in units:
            slot = _slot_of(unit, index)
            position = slot.end - len(values) + offset if from_end else slot.start + offset
            if 0 <= position < len(unit.elements) and unit.elements[position].value == value:
                votes.append((unit.elements[position].surface, unit.message_count))
        result.append(_literal(value, votes))
    return tuple(result)


def _anchor_votes(units: Sequence[_Unit], index: int, anchor: str) -> list[tuple[str, int]]:
    votes: list[tuple[str, int]] = []
    for unit in units:
        slot = _slot_of(unit, index)
        for element in unit.elements[slot.start : slot.end]:
            if element.value == anchor:
                votes.append((element.surface, unit.message_count))
                break
    return votes


def extract_candidates(groups: Sequence[SignatureGroup], config: CsgConfig) -> CsgExtraction:
    """Построить, проверить и отсортировать кандидатов."""
    merged = merge_signature_groups(groups, config)
    index = _ForeignIndex(groups)
    normalizer = _Normalizer(config.normalization)

    accepted: list[CsgCandidate] = []
    rejected: list[CsgCandidate] = []
    warnings: list[str] = []
    covered: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

    for item in merged:
        candidate = _validate_merged(item, index, config, normalizer)
        if candidate.status is CandidateStatus.REJECTED:
            rejected.append(candidate)
            continue
        accepted.append(candidate)
        covered.update(group.key for group in candidate.groups)

    for group in groups:
        if group.key in covered:
            continue
        if group.message_count < config.min_support:
            continue
        if group.segments < config.min_segments:
            continue
        candidate = _validate_exact(group, index, config, normalizer)
        if candidate.status is CandidateStatus.REJECTED:
            rejected.append(candidate)
        else:
            accepted.append(candidate)
            covered.update(item.key for item in candidate.groups)

    accepted.sort(key=lambda candidate: (-candidate.message_count, candidate.template_text))
    if rejected:
        warnings.append(
            f"{len(rejected)} групп отклонены проверкой: шаблон не покрывает сообщения "
            "или подпадает под чужие сообщения."
        )
    if any(candidate.status is CandidateStatus.NEEDS_HUMAN_APPROVAL for candidate in accepted):
        warnings.append(
            "Часть кандидатов содержит предложенную переменную %w{1,n}: "
            "перед регистрацией подтвердите её человеком."
        )
    return CsgExtraction(
        candidates=tuple(accepted),
        rejected=tuple(rejected),
        warnings=tuple(warnings),
    )


def _validate_exact(
    group: SignatureGroup,
    index: _ForeignIndex,
    config: CsgConfig,
    normalizer: _Normalizer,
) -> CsgCandidate:
    template_text, issues = emit_template(group, config)
    if issues:
        return _rejected(group, template_text, issues, 0)
    pattern = _compile(template_text, config)
    if pattern is None:
        return _rejected(
            group,
            template_text,
            (Issue("syntax", "Шаблон не компилируется"),),
            0,
        )
    matched = sum(1 for message in group.messages if pattern.fullmatch(normalizer(message.text)))
    if matched != group.message_count:
        return _rejected(
            group,
            template_text,
            (Issue("not_fullmatch", "Шаблон покрывает не все сообщения группы"),),
            0,
        )
    foreign, absorbed = _scan_foreign(
        pattern,
        group.message_ids,
        index.pool(group.sender_key, group.signature.elements),
        config,
        config.max_foreign_matches,
        normalizer,
    )
    if foreign > config.max_foreign_matches:
        return _rejected(
            group,
            template_text,
            (
                Issue(
                    "foreign_matches",
                    f"Шаблон подпадает под {foreign} чужих сообщений",
                ),
            ),
            foreign,
        )
    candidate_warnings: tuple[str, ...] = ()
    status = CandidateStatus.AUTO_VALIDATED
    if len(group.raw_senders) > 1:
        status = CandidateStatus.WARNING_SAVED
        candidate_warnings = ("Отправители объединены без учёта регистра: проверьте имя.",)
    return CsgCandidate(
        template_text=template_text,
        sender=group.sender,
        sender_key=group.sender_key,
        messages=_merge_messages(group.messages, absorbed),
        status=status,
        warnings=candidate_warnings,
        foreign_matches=foreign,
        confidence=Decimal("1"),
        coverage=Decimal("1"),
        groups=(group, *absorbed),
    )


def _validate_merged(
    item: MergedSignature,
    index: _ForeignIndex,
    config: CsgConfig,
    normalizer: _Normalizer,
) -> CsgCandidate:
    issues = lint_template(item.template_text, config)
    if issues:
        return _rejected_merged(item, issues, 0)
    pattern = _compile(item.template_text, config)
    if pattern is None:
        return _rejected_merged(item, (Issue("syntax", "Шаблон не компилируется"),), 0)
    messages = item.messages
    matched = sum(1 for message in messages if pattern.fullmatch(normalizer(message.text)))
    if matched != len(messages):
        return _rejected_merged(
            item,
            (Issue("not_fullmatch", "Обобщённый шаблон покрывает не все сообщения"),),
            0,
        )
    own_ids = frozenset(message.message_id for message in messages)
    foreign, absorbed = _scan_foreign(
        pattern,
        own_ids,
        index.pool(item.sender_key, item.elements),
        config,
        config.max_foreign_matches,
        normalizer,
    )
    if foreign > config.max_foreign_matches:
        return _rejected_merged(
            item,
            (
                Issue(
                    "foreign_matches",
                    f"Обобщённый шаблон подпадает под {foreign} чужих сообщений",
                ),
            ),
            foreign,
        )
    variable = f"%w{{1,{item.word_max}}}" if item.word_max > 1 else "%w"
    return CsgCandidate(
        template_text=item.template_text,
        sender=item.sender,
        sender_key=item.sender_key,
        messages=_merge_messages(messages, absorbed),
        status=CandidateStatus.NEEDS_HUMAN_APPROVAL,
        warnings=(
            f"Литеральный участок обобщён до {variable}: подтвердите переменную "
            "перед регистрацией шаблона.",
        ),
        foreign_matches=foreign,
        confidence=Decimal("0.9"),
        coverage=Decimal("1"),
        groups=(*item.groups, *absorbed),
    )


def _rejected(
    group: SignatureGroup,
    template_text: str,
    issues: Iterable[Issue],
    foreign: int,
) -> CsgCandidate:
    return CsgCandidate(
        template_text=template_text,
        sender=group.sender,
        sender_key=group.sender_key,
        messages=group.messages,
        status=CandidateStatus.REJECTED,
        warnings=tuple(issue.message for issue in issues),
        foreign_matches=foreign,
        confidence=Decimal("0"),
        coverage=Decimal("0"),
        groups=(group,),
    )


def _rejected_merged(item: MergedSignature, issues: Iterable[Issue], foreign: int) -> CsgCandidate:
    return CsgCandidate(
        template_text=item.template_text,
        sender=item.sender,
        sender_key=item.sender_key,
        messages=item.messages,
        status=CandidateStatus.REJECTED,
        warnings=tuple(issue.message for issue in issues),
        foreign_matches=foreign,
        confidence=Decimal("0"),
        coverage=Decimal("0"),
        groups=item.groups,
    )


def _emit_elements(
    elements: Sequence[SignatureElement],
    run_lengths: Sequence[Sequence[int]],
    config: CsgConfig,
) -> tuple[str, tuple[Issue, ...]]:
    parts: list[str] = []
    slot = 0
    for element in elements:
        if element.kind is ElementKind.LITERAL:
            parts.append(element.surface or element.value)
            continue
        if element.kind is ElementKind.NUMBER_RUN:
            lengths = tuple(run_lengths[slot]) if slot < len(run_lengths) else (1,)
            slot += 1
            parts.append(_numeric_variable(lengths, config))
            continue
        parts.append("%w" if element.limit <= 1 else f"%w{{1,{element.limit}}}")
    text = " ".join(part for part in parts if part)
    return text, lint_template(text, config)


def _numeric_variable(lengths: Sequence[int], config: CsgConfig) -> str:
    effective = tuple(length for length in lengths if length > 0) or (1,)
    low, high = min(effective), max(effective)
    if low == high:
        return " ".join(["%d"] * low)
    if high <= config.max_d_words:
        return f"%d{{1,{high}}}"
    return "%d+"


def _compile(template_text: str, config: CsgConfig) -> TemplatePattern | None:
    try:
        return compile_pattern(template_text, config.normalization)
    except TemplateSyntaxError:
        return None


def _split_template_word(
    raw_word: str, config: CsgConfig
) -> tuple[list[str | tuple[str, bool]], list[Issue]]:
    """Разобрать слово шаблона на литералы и переменные с признаком группы."""
    pieces: list[str | tuple[str, bool]] = []
    issues: list[Issue] = []
    position = 0
    for match in _VARIABLE.finditer(raw_word):
        literal = raw_word[position : match.start()]
        if literal:
            pieces.append(normalize_for_matching(literal, config.normalization))
        issue = _variable_issue(match, config)
        if issue is not None:
            issues.append(issue)
        pieces.append((str(match.group("kind")), _is_group_variable(match)))
        position = match.end()
    literal = raw_word[position:]
    if literal:
        pieces.append(normalize_for_matching(literal, config.normalization))
    return pieces, issues


def _variable_issue(match: re.Match[str], config: CsgConfig) -> Issue | None:
    if match.group("unknown") is not None:
        return Issue("unknown_variable", f"Неизвестная переменная %{match.group('unknown')}")
    kind = str(match.group("kind"))
    quantifier = match.group("quantifier")
    if quantifier == "+":
        if kind == "w":
            return Issue("w_plus", "Запрещено %w+: используйте %w или %w{1,n}")
        return None
    if quantifier is None:
        return None
    minimum = int(match.group("min"))
    maximum = int(match.group("max"))
    if minimum != 1:
        return Issue("bad_range", f"Диапазон %{kind}{quantifier} должен начинаться с 1")
    if maximum == 1:
        return Issue("redundant_range", f"Используйте %{kind} вместо %{kind}{{1,1}}")
    limit = config.max_w_words if kind == "w" else config.max_d_words
    if maximum > limit or maximum > MAX_GROUP_WORDS:
        return Issue(
            "too_many_groups",
            f"Число групп в %{kind}{{{1},{maximum}}} больше {min(limit, MAX_GROUP_WORDS)}",
        )
    return None


def _is_group_variable(match: re.Match[str]) -> bool:
    quantifier = match.group("quantifier")
    if quantifier == "+":
        return True
    if quantifier is None:
        return False
    return int(match.group("max")) > 1


def _adjacent_group_issues(sequence: Sequence[str | tuple[str, bool]]) -> list[Issue]:
    """Подряд идущие переменные запрещены: границу между ними определить нельзя.

    Исключение — `%d %d` (дата и время): МТС допускает две числовые переменные
    подряд. Две словесные переменные запрещены всегда, групповые — по правилам.
    """
    issues: list[Issue] = []
    for left, right in itertools.pairwise(sequence):
        if not (isinstance(left, tuple) and isinstance(right, tuple)):
            continue
        words = left[0] == "w" and right[0] == "w"
        if (left[1] and right[1]) or words:
            issues.append(
                Issue(
                    "adjacent_groups",
                    "Запрещено ставить переменные %w подряд: добавьте постоянный текст",
                )
            )
    return issues
