"""Применение темы к `QApplication` и доступ к активной палитре."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from mts_templates.presentation.desktop.theme_catalog import (
    SYSTEM_THEME,
    Theme,
    ThemePalette,
    theme_by_id,
)

_active_theme: Theme = SYSTEM_THEME


def active_theme() -> Theme:
    """Тема, применённая сейчас."""
    return _active_theme


def active_palette() -> ThemePalette:
    """Палитра активной темы для кастомной отрисовки."""
    return _active_theme.palette


def apply_theme(app: QApplication, theme_id: str) -> Theme:
    """Применить тему ко всему приложению и вернуть её."""
    global _active_theme
    theme = theme_by_id(theme_id)
    _active_theme = theme
    app.setStyleSheet(theme.stylesheet)
    for widget in app.allWidgets():
        widget.update()
    return theme
