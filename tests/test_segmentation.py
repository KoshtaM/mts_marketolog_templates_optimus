"""Тесты сегментации SMS."""

from __future__ import annotations

import pytest

from mts_templates.domain.analytics.segmentation import count_segments


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (0, 0),
        (1, 1),
        (70, 1),
        (71, 2),
        (137, 2),
        (138, 3),
        (204, 3),
        (205, 4),
    ],
)
def test_segment_boundaries(length: int, expected: int) -> None:
    assert count_segments("a" * length) == expected
