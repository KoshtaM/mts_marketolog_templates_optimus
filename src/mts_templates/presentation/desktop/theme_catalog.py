"""Каталог тем оформления: палитры и генерация QSS.

Модуль не импортирует Qt: это чистые данные и строки стилей. Применение темы к
`QApplication` и виджеты живут в `theme.py` и `widgets/theme_card.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from mts_templates.application.settings import (
    THEME_BIOPHILIC_GLASSHOUSE,
    THEME_CASSETTE_FUTURISM,
    THEME_DARK_ART_DECO,
    THEME_ETHEREAL_MESH,
    THEME_IDS,
    THEME_LOFI_COZY,
    THEME_NEO_BRUTALISM,
    THEME_SWISS_MINIMALISM,
    THEME_SYSTEM,
)


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Цветовые токены темы: фон, поверхности, текст, акцент и семантика."""

    window: str
    surface: str
    surface_alt: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    border: str
    header: str
    header_text: str
    selection: str
    selection_text: str
    positive: str
    negative: str
    accent_secondary: str


@dataclass(frozen=True, slots=True)
class Theme:
    """Тема оформления: палитра, шрифт, радиусы и флаг жёстких теней."""

    id: str
    name: str
    description: str
    palette: ThemePalette
    font_family: str = "Segoe UI"
    font_size: int = 10
    radius: int = 8
    border_width: int = 1
    hard_shadow: bool = False
    bold_text: bool = False

    @property
    def is_system(self) -> bool:
        """Системная тема оставляет оформление Qt по умолчанию."""
        return self.id == THEME_SYSTEM

    @property
    def stylesheet(self) -> str:
        """QSS для `QApplication`; для системной темы — пустая строка."""
        if self.is_system:
            return ""
        return _build_stylesheet(self)


SYSTEM_THEME = Theme(
    id=THEME_SYSTEM,
    name="Системная",
    description="Оформление Qt по умолчанию: светлый нейтральный интерфейс.",
    palette=ThemePalette(
        window="#f4f6fa",
        surface="#ffffff",
        surface_alt="#eef2f7",
        text="#1f2a37",
        text_muted="#667085",
        accent="#1f6feb",
        accent_hover="#1a5fd0",
        accent_text="#ffffff",
        border="#d7dee8",
        header="#dce9f8",
        header_text="#475467",
        selection="#dbeafe",
        selection_text="#1f2a37",
        positive="#1b7f3a",
        negative="#b42318",
        accent_secondary="#8b1a3a",
    ),
    font_family="Segoe UI",
    font_size=10,
    radius=8,
    border_width=1,
)


THEMES: tuple[Theme, ...] = (
    Theme(
        id=THEME_NEO_BRUTALISM,
        name="Необрутализм",
        description="Толстые чёрные рамки, резкие тени, бумага, горчица и коралл.",
        palette=ThemePalette(
            window="#f2e8cf",
            surface="#fff8e7",
            surface_alt="#f5e6c8",
            text="#111111",
            text_muted="#4a4a4a",
            accent="#e0b400",
            accent_hover="#c9a100",
            accent_text="#111111",
            border="#111111",
            header="#ff6b5b",
            header_text="#111111",
            selection="#ffe08a",
            selection_text="#111111",
            positive="#2f7d32",
            negative="#c0392b",
            accent_secondary="#ff6b5b",
        ),
        font_family="Verdana",
        font_size=10,
        radius=0,
        border_width=3,
        hard_shadow=True,
        bold_text=True,
    ),
    Theme(
        id=THEME_BIOPHILIC_GLASSHOUSE,
        name="Биофильный дизайн",
        description="Матовое стекло, шалфейная зелень, дерево и тени от листьев.",
        palette=ThemePalette(
            window="#e6efe4",
            surface="#f7faf5",
            surface_alt="#dbe8d8",
            text="#2c3a2e",
            text_muted="#5f7161",
            accent="#4f7a5a",
            accent_hover="#3f6649",
            accent_text="#ffffff",
            border="#b9cdb6",
            header="#cfe0cb",
            header_text="#2c3a2e",
            selection="#d7e8d4",
            selection_text="#2c3a2e",
            positive="#3f7a4a",
            negative="#a8452f",
            accent_secondary="#8a6f4e",
        ),
        font_family="Segoe UI",
        font_size=10,
        radius=14,
        border_width=1,
    ),
    Theme(
        id=THEME_CASSETTE_FUTURISM,
        name="Кассетный футуризм",
        description="Ретро-фантастика 80-х, янтарное свечение, CRT-зелёный, металл.",
        palette=ThemePalette(
            window="#14120e",
            surface="#1e1a14",
            surface_alt="#262019",
            text="#f2c46b",
            text_muted="#9a8a6a",
            accent="#ffb000",
            accent_hover="#ffc733",
            accent_text="#14120e",
            border="#4a3d28",
            header="#2a241b",
            header_text="#ffcf6b",
            selection="#3a2f1f",
            selection_text="#f2c46b",
            positive="#7dff9b",
            negative="#ff6b5b",
            accent_secondary="#58ff9d",
        ),
        font_family="Consolas",
        font_size=10,
        radius=4,
        border_width=1,
    ),
    Theme(
        id=THEME_SWISS_MINIMALISM,
        name="Швейцарский минимализм",
        description="Строгая сетка, много воздуха, сдержанный красный акцент.",
        palette=ThemePalette(
            window="#f5f5f3",
            surface="#ffffff",
            surface_alt="#ececea",
            text="#111111",
            text_muted="#6b6b68",
            accent="#d92d20",
            accent_hover="#b42318",
            accent_text="#ffffff",
            border="#d9d9d5",
            header="#e8e8e4",
            header_text="#111111",
            selection="#f3d9d6",
            selection_text="#111111",
            positive="#1f7a3a",
            negative="#b42318",
            accent_secondary="#111111",
        ),
        font_family="Segoe UI",
        font_size=10,
        radius=2,
        border_width=1,
    ),
    Theme(
        id=THEME_DARK_ART_DECO,
        name="Тёмный ар-деко",
        description="Обсидиан и изумруд, тонкие золотые линии, серифный шрифт.",
        palette=ThemePalette(
            window="#0b0f0d",
            surface="#121916",
            surface_alt="#0f1512",
            text="#f0e6cf",
            text_muted="#a89b7c",
            accent="#c9a227",
            accent_hover="#e0b83a",
            accent_text="#0b0f0d",
            border="#2a3a31",
            header="#0f3d2e",
            header_text="#e8d9a8",
            selection="#1c3a2c",
            selection_text="#f0e6cf",
            positive="#4fbf87",
            negative="#d9534f",
            accent_secondary="#1f6f4f",
        ),
        font_family="Georgia",
        font_size=10,
        radius=3,
        border_width=1,
    ),
    Theme(
        id=THEME_ETHEREAL_MESH,
        name="Эфирный градиент",
        description="Размытые цветные сферы, полупрозрачное стекло, мягкое свечение.",
        palette=ThemePalette(
            window="#eef0ff",
            surface="#f7f8ff",
            surface_alt="#e6e9fb",
            text="#2b2d4a",
            text_muted="#6f7396",
            accent="#7c6cf0",
            accent_hover="#6a58e8",
            accent_text="#ffffff",
            border="#d5d9f2",
            header="#e2e5fb",
            header_text="#4a4d75",
            selection="#e4e0ff",
            selection_text="#2b2d4a",
            positive="#3f9e7a",
            negative="#d05a7a",
            accent_secondary="#ff8fc7",
        ),
        font_family="Segoe UI",
        font_size=10,
        radius=16,
        border_width=1,
    ),
    Theme(
        id=THEME_LOFI_COZY,
        name="Лоу-фай уют",
        description="Тёплый бежевый и кофейный, мягкий свет лампы, матовая фактура.",
        palette=ThemePalette(
            window="#efe3cf",
            surface="#f7eddc",
            surface_alt="#e7d7bf",
            text="#3f3024",
            text_muted="#7a6653",
            accent="#b07d4f",
            accent_hover="#96663c",
            accent_text="#fff8ee",
            border="#d3bfa4",
            header="#e3cfb2",
            header_text="#4a3728",
            selection="#ead7bd",
            selection_text="#3f3024",
            positive="#5b7a4a",
            negative="#a8563f",
            accent_secondary="#6b4f3a",
        ),
        font_family="Segoe UI",
        font_size=10,
        radius=12,
        border_width=1,
    ),
)

_THEMES_BY_ID = {theme.id: theme for theme in (SYSTEM_THEME, *THEMES)}

# Каталог обязан покрывать все идентификаторы, которые сохраняются в настройках.
if set(_THEMES_BY_ID) != set(THEME_IDS):
    raise RuntimeError("Каталог тем не совпадает со списком THEME_IDS")


def theme_by_id(theme_id: str) -> Theme:
    """Тема по идентификатору; неизвестный идентификатор — системная тема."""
    return _THEMES_BY_ID.get(theme_id, SYSTEM_THEME)


def _build_stylesheet(theme: Theme) -> str:
    p = theme.palette
    r = theme.radius
    bw = theme.border_width
    weight = "font-weight: 700;" if theme.bold_text else ""
    shadow_rules = ""
    if theme.hard_shadow:
        shadow_rules = f"""
QPushButton {{
    border-right-width: {bw + 2}px;
    border-bottom-width: {bw + 2}px;
}}
QPushButton:pressed {{
    border-right-width: {bw}px;
    border-bottom-width: {bw}px;
    padding-left: 9px;
    padding-top: 7px;
}}
"""
    return f"""
QWidget {{
    background-color: {p.window};
    color: {p.text};
    font-family: "{theme.font_family}";
    font-size: {theme.font_size}pt;
    {weight}
}}
QMainWindow, QDialog {{
    background-color: {p.window};
}}
QTabWidget::pane {{
    border: {bw}px solid {p.border};
    background-color: {p.surface};
}}
QTabBar::tab {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    border: {bw}px solid {p.border};
    border-bottom: none;
    border-top-left-radius: {r}px;
    border-top-right-radius: {r}px;
    padding: 7px 16px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {p.surface};
    color: {p.text};
}}
QTabBar::tab:hover {{
    color: {p.accent};
}}
QGroupBox {{
    background-color: {p.surface};
    border: {bw}px solid {p.border};
    border-radius: {r}px;
    margin-top: 12px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {p.text};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    border-radius: {r}px;
    padding: 4px 8px;
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {p.accent};
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
}}
QPushButton {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    border-radius: {r}px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    border-color: {p.accent};
    color: {p.accent};
}}
QPushButton:pressed {{
    background-color: {p.surface_alt};
}}
QPushButton#primaryButton {{
    background-color: {p.accent};
    color: {p.accent_text};
    border: none;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {p.accent_hover};
    color: {p.accent_text};
}}
QCheckBox {{
    color: {p.text};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: {bw}px solid {p.border};
    border-radius: {max(2, r // 3)}px;
    background-color: {p.surface};
}}
QCheckBox::indicator:checked {{
    background-color: {p.accent};
    border-color: {p.accent};
}}
QTableWidget, QTableView {{
    background-color: {p.surface};
    alternate-background-color: {p.surface_alt};
    color: {p.text};
    gridline-color: {p.border};
    border: {bw}px solid {p.border};
    selection-background-color: {p.selection};
    selection-color: {p.selection_text};
}}
QHeaderView::section {{
    background-color: {p.header};
    color: {p.header_text};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    padding: 6px;
    font-weight: 600;
}}
QListWidget, QListView {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    border-radius: {r}px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
}}
QListWidget::item:selected {{
    background-color: {p.accent};
    color: {p.accent_text};
}}
QListWidget::item:hover {{
    background-color: {p.surface_alt};
}}
QScrollArea {{
    background-color: {p.window};
    border: none;
}}
QStatusBar {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    border-top: 1px solid {p.border};
}}
QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    padding: 4px 6px;
}}
QProgressBar {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: {r}px;
    text-align: center;
    color: {p.text};
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: {r}px;
}}
QMenu {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
}}
QMenu::item:selected {{
    background-color: {p.accent};
    color: {p.accent_text};
}}
QScrollBar:vertical {{
    background: {p.surface_alt};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border};
    min-height: 28px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.accent};
}}
QScrollBar:horizontal {{
    background: {p.surface_alt};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p.border};
    min-width: 28px;
    border-radius: 6px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
{shadow_rules}
"""
