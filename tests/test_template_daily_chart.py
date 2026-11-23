"""Дневной график выбранного шаблона на вкладке «Шаблоны»."""

from __future__ import annotations

from datetime import date

from mts_templates.domain.analytics.activity import DaySegments
from mts_templates.presentation.desktop.daily_chart import (
    TEMPLATE_MATCHED_COLOR,
    TEMPLATE_MATCHED_LABEL,
    TEMPLATE_OTHER_COLOR,
    TEMPLATE_OTHER_LABEL,
    TEMPLATE_OTHER_TEMPLATED_LABEL,
    build_template_daily_chart,
)


def _day(day: int, segments: int) -> DaySegments:
    return DaySegments(day=date(2026, 11, day), segments=segments)


def test_bars_cover_every_day_of_the_period() -> None:
    data = build_template_daily_chart(
        (_day(2, 9), _day(3, 4)),
        (_day(2, 5),),
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 4),
    )

    assert [bar.label for bar in data.bars] == ["01.11", "02.11", "03.11", "04.11"]
    assert [bar.total for bar in data.bars] == [0.0, 9.0, 4.0, 0.0]


def test_matched_part_is_overlay_inside_the_base_bar() -> None:
    data = build_template_daily_chart(
        (_day(2, 9),),
        (_day(2, 5),),
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 2),
    )

    bar = data.bars[0]
    assert [(part.label, part.value, part.color) for part in bar.segments] == [
        (TEMPLATE_OTHER_LABEL, 9.0, TEMPLATE_OTHER_COLOR),
    ]
    assert [(overlay.label, overlay.value, overlay.color) for overlay in bar.overlays] == [
        (TEMPLATE_MATCHED_LABEL, 5.0, TEMPLATE_MATCHED_COLOR)
    ]
    assert bar.total == 9.0


def test_day_without_matches_has_only_other_traffic() -> None:
    data = build_template_daily_chart(
        (_day(3, 4),),
        (),
        period_start=date(2026, 11, 3),
        period_end=date(2026, 11, 3),
    )

    assert [(part.label, part.value) for part in data.bars[0].segments] == [
        (TEMPLATE_OTHER_LABEL, 4.0)
    ]
    assert data.bars[0].overlays == ()


def test_matched_beyond_total_is_clamped_not_negative() -> None:
    data = build_template_daily_chart(
        (_day(2, 3),),
        (_day(2, 5),),
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 2),
    )

    bar = data.bars[0]
    assert [(part.label, part.value) for part in bar.segments] == [(TEMPLATE_OTHER_LABEL, 3.0)]
    assert [(overlay.label, overlay.value) for overlay in bar.overlays] == [
        (TEMPLATE_MATCHED_LABEL, 3.0)
    ]


def test_templated_only_uses_templated_traffic_as_base() -> None:
    data = build_template_daily_chart(
        (_day(2, 7),),
        (_day(2, 9),),
        period_start=date(2026, 11, 2),
        period_end=date(2026, 11, 2),
        templated_only=True,
    )

    bar = data.bars[0]
    assert [(part.label, part.value) for part in bar.segments] == [
        (TEMPLATE_OTHER_TEMPLATED_LABEL, 7.0)
    ]
    assert [(overlay.label, overlay.value) for overlay in bar.overlays] == [
        (TEMPLATE_MATCHED_LABEL, 7.0)
    ]
    assert data.caption == "шаблон: 7 из 7 шаблонированных сегментов"
    assert data.legend == (
        (TEMPLATE_MATCHED_LABEL, TEMPLATE_MATCHED_COLOR),
        (TEMPLATE_OTHER_TEMPLATED_LABEL, TEMPLATE_OTHER_COLOR),
    )


def test_caption_and_legend_describe_both_parts() -> None:
    data = build_template_daily_chart(
        (_day(2, 9), _day(3, 4)),
        (_day(2, 5),),
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 4),
    )

    assert data.caption == "шаблон: 5 из 13 сегментов"
    assert data.legend == (
        (TEMPLATE_MATCHED_LABEL, TEMPLATE_MATCHED_COLOR),
        (TEMPLATE_OTHER_LABEL, TEMPLATE_OTHER_COLOR),
    )


def test_empty_period_has_no_caption() -> None:
    data = build_template_daily_chart(
        (),
        (),
        period_start=date(2026, 11, 1),
        period_end=date(2026, 11, 4),
    )

    assert data.caption == ""
    assert all(bar.segments == () for bar in data.bars)
    assert all(bar.overlays == () for bar in data.bars)


def test_invalid_period_falls_back_to_days_with_data() -> None:
    data = build_template_daily_chart(
        (_day(3, 4),),
        (_day(1, 2),),
        period_start=date(2026, 11, 5),
        period_end=date(2026, 11, 1),
    )

    assert [bar.label for bar in data.bars] == ["01.11", "03.11"]
