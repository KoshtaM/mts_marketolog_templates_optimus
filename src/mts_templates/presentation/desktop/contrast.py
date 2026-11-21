"""Контраст цветов по WCAG 2.1: выбор читаемого текста поверх фона.

Модуль не импортирует Qt: только разбор `#rrggbb` и формула относительной
яркости. Используется подсветкой строк таблиц и тестами доступности тем.
"""

from __future__ import annotations

LIGHT_TEXT = "#111111"
DARK_TEXT = "#f7f7f4"
MIN_CONTRAST = 4.5


def _parse(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) != 6:
        raise ValueError(f"Ожидался цвет #rrggbb, получено: {color!r}")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red, green, blue


def _linear(channel: int) -> float:
    srgb = channel / 255
    if srgb <= 0.04045:
        return srgb / 12.92
    return float(((srgb + 0.055) / 1.055) ** 2.4)


def relative_luminance(color: str) -> float:
    """Относительная яркость цвета по WCAG 2.1."""
    red, green, blue = _parse(color)
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(first: str, second: str) -> float:
    """Коэффициент контраста двух цветов: от 1 до 21."""
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_color(background: str) -> str:
    """Тёмный или светлый текст, дающий больший контраст с фоном."""
    if contrast_ratio(LIGHT_TEXT, background) >= contrast_ratio(DARK_TEXT, background):
        return LIGHT_TEXT
    return DARK_TEXT
