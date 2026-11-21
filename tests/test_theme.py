"""Тесты каталога тем оформления и контраста палитр (без Qt)."""

from __future__ import annotations

from mts_templates.application.settings import THEME_IDS, THEME_SYSTEM
from mts_templates.presentation.desktop.benefit_style import row_palette
from mts_templates.presentation.desktop.contrast import (
    MIN_CONTRAST,
    contrast_ratio,
    readable_text_color,
)
from mts_templates.presentation.desktop.theme_catalog import (
    SYSTEM_THEME,
    THEMES,
    theme_by_id,
)

ALL_THEMES = (SYSTEM_THEME, *THEMES)
FOCUS_MIN_CONTRAST = 3.0


def test_thirteen_design_themes_are_defined() -> None:
    assert len(THEMES) == 13
    assert len({theme.id for theme in THEMES}) == 13
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
    for theme_id in ("cassette_futurism", "dark_art_deco", "soviet_space"):
        theme = theme_by_id(theme_id)
        assert theme.palette.text != theme.palette.window
        assert theme.palette.window.startswith("#")


def test_text_and_surface_contrast_meets_wcag_aa() -> None:
    for theme in ALL_THEMES:
        palette = theme.palette
        pairs = (
            (palette.text, palette.window),
            (palette.text, palette.surface),
            (palette.text_muted, palette.window),
            (palette.text_muted, palette.surface),
            (palette.header_text, palette.header),
            (palette.accent_text, palette.accent),
            (palette.selection_text, palette.selection),
        )
        for foreground, background in pairs:
            assert contrast_ratio(foreground, background) >= MIN_CONTRAST, (
                f"{theme.id}: {foreground} на {background}"
            )


def test_focus_ring_is_visible_on_every_theme() -> None:
    for theme in ALL_THEMES:
        palette = theme.palette
        assert contrast_ratio(palette.focus_ring, palette.window) >= FOCUS_MIN_CONTRAST, theme.id
        assert contrast_ratio(palette.focus_ring, palette.surface) >= FOCUS_MIN_CONTRAST, theme.id
        assert "focus" in theme.stylesheet or theme.is_system


def test_row_highlights_are_readable_in_every_theme() -> None:
    for theme in ALL_THEMES:
        palette = theme.palette
        rows = row_palette(palette.surface, palette.positive, palette.negative)
        for color in rows.all_colors:
            text = readable_text_color(color)
            assert contrast_ratio(text, color) >= MIN_CONTRAST, f"{theme.id}: {color}"
