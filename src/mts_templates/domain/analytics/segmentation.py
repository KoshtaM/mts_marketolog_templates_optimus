"""Сегментация SMS: 1 сегмент до 70 символов, далее по 67."""

from __future__ import annotations

SINGLE_SEGMENT_LIMIT = 70
MULTI_SEGMENT_LIMIT = 67


def count_segments(text: str) -> int:
    """Количество SMS-сегментов по длине текста.

    Пустой текст — 0 сегментов: это либо ошибка отправки, либо отсутствие данных.
    """
    length = len(text)
    if length == 0:
        return 0
    if length <= SINGLE_SEGMENT_LIMIT:
        return 1
    rest = length - SINGLE_SEGMENT_LIMIT
    return 1 + -(-rest // MULTI_SEGMENT_LIMIT)
