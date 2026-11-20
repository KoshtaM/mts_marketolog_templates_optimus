"""Тесты каталога тем оформления (без Qt)."""

from __future__ import annotations

from mts_templates.application.settings import THEME_IDS, THEME_SYSTEM
from mts_templates.presentation.desktop.theme_catalog import (
    SYSTEM_THEME,
    THEMES,
    theme_by_id,
)


def test_seven_design_themes_are_defined() -> None:
    assert len(THEMES) == 7
    assert len({theme.id for theme in THEMES}) == 7
    assert all(theme.name.strip() for theme in THEMES)


def test_catalog_covers_all_persisted_ids() -> None:
    catalog_ids = {theme.id for theme in THEMES} | {SYSTEM_THEME.id}
    assert catalog_ids == set(THEME_IDS)


def test_unknown_theme_falls_back_to_system() -> None:
    assert theme_by_id("does-not-exist") is SYSTEM_THEME
    assert theme_by_id(THEME_SYSTEM) is SYSTEM_THEME


def test_system_theme_has_no_stylesheet() -> None:
    assert SYSTEM_THEME.stylesheet == ""


def test_each_design_theme_has_stylesheet_with_its_tokens() -> None:
    for theme in THEMES:
        stylesheet = theme.stylesheet
        assert stylesheet
        assert theme.palette.window in stylesheet
        assert theme.palette.text in stylesheet
        assert theme.palette.accent in stylesheet


def test_neo_brutalism_uses_hard_borders_and_no_rounding() -> None:
    theme = theme_by_id("neo_brutalism")

    assert theme.radius == 0
    assert theme.border_width >= 3
    assert theme.hard_shadow is True
    assert "border-right-width" in theme.stylesheet


def test_dark_themes_have_light_text() -> None:
    for theme_id in ("cassette_futurism", "dark_art_deco"):
        theme = theme_by_id(theme_id)
        assert theme.palette.text != theme.palette.window
        assert theme.palette.window.startswith("#")
