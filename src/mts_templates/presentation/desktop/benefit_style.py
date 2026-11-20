"""Цвета уровней выгоды шаблона.

Пять зелёных градаций по порогам из настроек и один слабо-красный уровень для
убытка: убыток не может быть больше стоимости шаблона, поэтому градации ему не
нужны. Модуль не зависит от Qt: возвращает имена цветов, виджет создаёт `QColor`.
"""

from __future__ import annotations

from mts_templates.application.settings import BenefitThresholds
from mts_templates.domain.value_objects import Money

LOSS_COLOR = "#f8d7d4"
LEVEL_COLORS = (
    "#d9eedb",
    "#c8e6c9",
    "#a5d6a7",
    "#81c784",
    "#4caf50",
)
OPERATOR_LISTED_COLOR = "#c8e6c9"


def benefit_level(net_benefit: Money, thresholds: BenefitThresholds) -> int:
    """Уровень выгоды: `-1` — убыток, `0` — без цвета, `1..5` — зелёные градации."""
    if net_benefit.amount < 0:
        return -1
    level = 0
    for index, threshold in enumerate(thresholds.levels, start=1):
        if net_benefit.amount >= threshold.amount:
            level = index
    return level


def benefit_color(net_benefit: Money, thresholds: BenefitThresholds) -> str | None:
    """Имя цвета фона строки или None, если выгода нулевая."""
    level = benefit_level(net_benefit, thresholds)
    if level < 0:
        return LOSS_COLOR
    if level == 0:
        return None
    return LEVEL_COLORS[level - 1]
