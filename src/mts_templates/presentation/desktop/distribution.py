"""Группировка распределения по числу SMS-сегментов для гистограммы. Без Qt."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mts_templates.application.dto import SegmentCountBucket

EXACT_SEGMENT_LIMIT = 9
TAIL_RANGES: tuple[tuple[int, int | None], ...] = (
    (10, 19),
    (20, 49),
    (50, 99),
    (100, None),
)


@dataclass(frozen=True, slots=True)
class DistributionBar:
    """Столбец гистограммы: подпись диапазона, количество и доля."""

    label: str
    count: int
    share: float
    grouped: bool = False


def group_buckets(
    buckets: Sequence[SegmentCountBucket],
    *,
    exact_limit: int = EXACT_SEGMENT_LIMIT,
    tail_ranges: Sequence[tuple[int, int | None]] = TAIL_RANGES,
) -> tuple[DistributionBar, ...]:
    """Точные столбцы для 1..exact_limit и укрупнённые диапазоны для хвоста.

    Значения без записей внутри «точной» части показываются нулями, чтобы
    форма распределения не искажалась пропусками. Пустые диапазоны хвоста
    не выводятся.
    """
    present = {bucket.segments: bucket for bucket in buckets if bucket.count > 0}
    largest = max(present, default=0)
    bars = [
        _exact_bar(segments, present.get(segments))
        for segments in range(1, min(exact_limit, largest) + 1)
    ]
    for low, high in tail_ranges:
        members = [
            bucket
            for segments, bucket in present.items()
            if segments >= low and (high is None or segments <= high)
        ]
        if not members:
            continue
        bars.append(
            DistributionBar(
                label=_range_label(low, high),
                count=sum(bucket.count for bucket in members),
                share=sum(bucket.share for bucket in members),
                grouped=True,
            )
        )
    return tuple(bars)


def _exact_bar(segments: int, bucket: SegmentCountBucket | None) -> DistributionBar:
    if bucket is None:
        return DistributionBar(label=str(segments), count=0, share=0.0)
    return DistributionBar(label=str(segments), count=bucket.count, share=bucket.share)


def _range_label(low: int, high: int | None) -> str:
    if high is None:
        return f"{low}+"
    return f"{low}–{high}"
