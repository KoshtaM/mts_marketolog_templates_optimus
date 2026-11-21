"""Цвета уровней выгоды шаблона.

Пять градаций «зелёного» по порогам из настроек и один слабо-красный уровень для
убытка: убыток не может быть больше стоимости шаблона, поэтому градации ему не
нужны. Фоны выводятся из палитры темы: на светлой поверхности получаются
пастельные заливки, на тёмной — глубокие оттенки, поэтому текст остаётся
читаемым в любой теме. Модуль не зависит от Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from mts_templates.application.settings import BenefitThresholds
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.contrast import (
    MIN_CONTRAST,
    contrast_ratio,
    readable_text_color,
    relative_luminance,
)

LIGHT_LEVEL_INTENSITY = (0.16, 0.28, 0.40, 0.52, 0.64)
DARK_LEVEL_INTENSITY = (0.10, 0.18, 0.26, 0.34, 0.42)
LIGHT_LOSS_INTENSITY = 0.20
DARK_LOSS_INTENSITY = 0.14
LIGHT_LISTED_INTENSITY = 0.28
DARK_LISTED_INTENSITY = 0.16
DARK_SURFACE_LUMINANCE = 0.35


@dataclass(frozen=True, slots=True)
class RowPalette:
    """Фоны подсветки строк, выведенные из палитры активной темы."""

    level_colors: tuple[str, ...]
    loss_color: str
    listed_color: str

    @property
    def all_colors(self) -> tuple[str, ...]:
        """Все цвета подсветки — для проверки контраста в тестах."""
        return (*self.level_colors, self.loss_color, self.listed_color)


def _mix(foreground: str, background: str, ratio: float) -> str:
    """Смешать цвета в пропорции `ratio` (0 — фон, 1 — передний цвет)."""
    first = _parse(foreground)
    second = _parse(background)
    channels = (round(first[index] * ratio + second[index] * (1 - ratio)) for index in range(3))
    return "#" + "".join(f"{value:02x}" for value in channels)


def _parse(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


@lru_cache(maxsize=64)
def row_palette(surface: str, positive: str, negative: str) -> RowPalette:
    """Фоны подсветки строк для поверхности темы."""
    dark = relative_luminance(surface) < DARK_SURFACE_LUMINANCE
    levels = DARK_LEVEL_INTENSITY if dark else LIGHT_LEVEL_INTENSITY
    loss = DARK_LOSS_INTENSITY if dark else LIGHT_LOSS_INTENSITY
    listed = DARK_LISTED_INTENSITY if dark else LIGHT_LISTED_INTENSITY
    return RowPalette(
        level_colors=tuple(_mix(positive, surface, value) for value in levels),
        loss_color=_mix(negative, surface, loss),
        listed_color=_mix(positive, surface, listed),
    )


def benefit_level(net_benefit: Money, thresholds: BenefitThresholds) -> int:
    """Уровень выгоды: `-1` — убыток, `0` — без цвета, `1..5` — градации."""
    if net_benefit.amount < 0:
        return -1
    level = 0
    for index, threshold in enumerate(thresholds.levels, start=1):
        if net_benefit.amount >= threshold.amount:
            level = index
    return level


def benefit_color(
    net_benefit: Money,
    thresholds: BenefitThresholds,
    palette: RowPalette,
) -> str | None:
    """Имя цвета фона строки или None, если выгода нулевая."""
    level = benefit_level(net_benefit, thresholds)
    if level < 0:
        return palette.loss_color
    if level == 0:
        return None
    return palette.level_colors[level - 1]


def semantic_text(foreground: str, background: str) -> str:
    """Семантический цвет текста, читаемый на фоне темы."""
    if contrast_ratio(foreground, background) >= MIN_CONTRAST:
        return foreground
    return readable_text_color(background)
