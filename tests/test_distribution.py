"""Группировка распределения по числу SMS-сегментов для гистограммы."""

from __future__ import annotations

import pytest

from mts_templates.application.dto import SegmentCountBucket
from mts_templates.presentation.desktop.distribution import DistributionBar, group_buckets


def make_buckets(counts: dict[int, int]) -> tuple[SegmentCountBucket, ...]:
    total = sum(counts.values())
    return tuple(
        SegmentCountBucket(segments=segments, count=count, share=count / total)
        for segments, count in sorted(counts.items())
    )


def test_exact_segments_keep_gaps_as_zero_bars() -> None:
    bars = group_buckets(make_buckets({1: 5, 2: 3, 4: 1}))

    assert [bar.label for bar in bars] == ["1", "2", "3", "4"]
    assert bars[2] == DistributionBar(label="3", count=0, share=0.0)
    assert all(not bar.grouped for bar in bars)


def test_tail_is_grouped_into_ranges() -> None:
    bars = group_buckets(make_buckets({1: 4, 12: 2, 15: 1, 60: 3, 130: 1}))

    labels = [bar.label for bar in bars]
    assert labels == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10–19", "50–99", "100+"]
    by_label = {bar.label: bar for bar in bars}
    assert by_label["10–19"] == DistributionBar(
        label="10–19", count=3, share=pytest.approx(3 / 11), grouped=True
    )
    assert by_label["50–99"].count == 3
    assert by_label["100+"].count == 1
    assert by_label["100+"].grouped is True


def test_counts_and_shares_are_preserved() -> None:
    buckets = make_buckets({1: 7, 2: 4, 9: 2, 25: 5, 80: 2})

    bars = group_buckets(buckets)

    assert sum(bar.count for bar in bars) == sum(bucket.count for bucket in buckets)
    assert sum(bar.share for bar in bars) == pytest.approx(1.0)


def test_empty_distribution_gives_no_bars() -> None:
    assert group_buckets(()) == ()


def test_only_empty_buckets_give_no_bars() -> None:
    buckets = (SegmentCountBucket(segments=1, count=0, share=0.0),)

    assert group_buckets(buckets) == ()


def test_custom_limits_are_respected() -> None:
    bars = group_buckets(
        make_buckets({1: 1, 2: 1, 3: 1, 4: 1}),
        exact_limit=2,
        tail_ranges=((3, None),),
    )

    assert [bar.label for bar in bars] == ["1", "2", "3+"]
    assert bars[-1].count == 2
