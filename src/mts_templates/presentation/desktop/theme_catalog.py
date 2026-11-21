"""Каталог тем оформления: палитры и генерация QSS.

Модуль не импортирует Qt: это чистые данные и строки стилей. Применение темы к
`QApplication` и виджеты живут в `theme.py` и `widgets/theme_card.py`.

Контракт темы — `ThemePalette` (цветовые токены) и поля `Theme` (шрифты, радиусы,
масштаб отступов). Новые темы добавляются сюда: идентификатор объявляется в
`application/settings.py`, палитра — в `THEMES`, превью — в `widgets/theme_card.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from mts_templates.application.settings import (
    THEME_BIOPHILIC_GLASSHOUSE,
    THEME_CASSETTE_FUTURISM,
    THEME_DARK_ART_DECO,
    THEME_EDITORIAL_MODERN,
    THEME_ETHEREAL_MESH,
    THEME_IDS,
    THEME_LOFI_COZY,
    THEME_MEMPHIS_POSTMODERN,
    THEME_NEO_BRUTALISM,
    THEME_RISOGRAPH_PUNK,
    THEME_SOVIET_SPACE,
    THEME_SWISS_MINIMALISM,
    THEME_SYSTEM,
    THEME_WABI_SABI,
    THEME_Y2K_CHROME,
)


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Цветовые токены темы.

    Соответствие контракту: `window` — фон, `surface` — поверхность,
    `surface_alt` — приподнятая поверхность, `text` — основной текст,
    `text_muted` — вторичный текст, `accent`/`accent_hover`/`accent_pressed` —
    акцент и его состояния, `focus_ring` — обводка фокуса, `negative` —
    опасность/убыток, `positive` — успех/прибыль, `warning` — предупреждение,
    `shadow` — цвет тени.
    """

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
    accent_pressed: str
    focus_ring: str
    warning: str
    shadow: str


@dataclass(frozen=True, slots=True)
class Theme:
    """Тема оформления: палитра, шрифты, радиусы и масштаб отступов."""

    id: str
    name: str
    description: str
    palette: ThemePalette
    font_family: str = "Segoe UI"
    font_heading: str = ""
    font_mono: str = ""
    font_size: int = 10
    radius: int = 8
    border_width: int = 1
    spacing_scale: float = 1.0
    hard_shadow: bool = False
    bold_text: bool = False

    @property
    def is_system(self) -> bool:
        """Системная тема оставляет оформление Qt по умолчанию."""
        return self.id == THEME_SYSTEM

    @property
    def heading_font(self) -> str:
        """Шрифт заголовков; по умолчанию совпадает с основным."""
        return self.font_heading or self.font_family

    @property
    def mono_font(self) -> str:
        """Моноширинный шрифт для технических подписей."""
        return self.font_mono or self.font_family

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
        accent_pressed="#1650b0",
        focus_ring="#1f6feb",
        warning="#b54708",
        shadow="#98a2b3",
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
            accent_pressed="#b08e00",
            focus_ring="#1d3a8a",
            warning="#9a5b00",
            shadow="#111111",
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
            text_muted="#556753",
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
            accent_pressed="#35573e",
            focus_ring="#4f7a5a",
            warning="#8a5a00",
            shadow="#8a9a86",
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
            accent_pressed="#d99400",
            focus_ring="#58ff9d",
            warning="#ffb000",
            shadow="#000000",
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
            accent_pressed="#8f1d18",
            focus_ring="#d92d20",
            warning="#8a5a00",
            shadow="#b9b9b4",
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
            accent_pressed="#a8851b",
            focus_ring="#c9a227",
            warning="#d9a441",
            shadow="#000000",
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
            text_muted="#5d6184",
            accent="#6a58e8",
            accent_hover="#5a48d8",
            accent_text="#ffffff",
            border="#d5d9f2",
            header="#e2e5fb",
            header_text="#4a4d75",
            selection="#e4e0ff",
            selection_text="#2b2d4a",
            positive="#3f9e7a",
            negative="#d05a7a",
            accent_secondary="#ff8fc7",
            accent_pressed="#4a38c4",
            focus_ring="#6a58e8",
            warning="#a15c00",
            shadow="#9aa0c4",
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
            text_muted="#6b5947",
            accent="#96663c",
            accent_hover="#845733",
            accent_text="#fff8ee",
            border="#d3bfa4",
            header="#e3cfb2",
            header_text="#4a3728",
            selection="#ead7bd",
            selection_text="#3f3024",
            positive="#5b7a4a",
            negative="#a8563f",
            accent_secondary="#6b4f3a",
            accent_pressed="#71482a",
            focus_ring="#845733",
            warning="#8a5a00",
            shadow="#b39d80",
        ),
        font_family="Segoe UI",
        font_size=10,
        radius=12,
        border_width=1,
    ),
    Theme(
        id=THEME_RISOGRAPH_PUNK,
        name="Ризограф-панк",
        description="Двухцветная ризопечать, зерно бумаги, смещённые слои краски.",
        palette=ThemePalette(
            window="#f4efe6",
            surface="#fbf7ef",
            surface_alt="#ece4d6",
            text="#111111",
            text_muted="#4a4a4a",
            accent="#ff4fa3",
            accent_hover="#f0348f",
            accent_text="#111111",
            border="#c7bba9",
            header="#1d3a8a",
            header_text="#f4efe6",
            selection="#ffd9ea",
            selection_text="#111111",
            positive="#1f7a4a",
            negative="#b3261e",
            accent_secondary="#1d3a8a",
            accent_pressed="#d92479",
            focus_ring="#1d3a8a",
            warning="#9a5b00",
            shadow="#1d3a8a",
        ),
        font_family="Segoe UI",
        font_heading="Verdana",
        font_mono="Consolas",
        font_size=10,
        radius=6,
        border_width=1,
    ),
    Theme(
        id=THEME_WABI_SABI,
        name="Ваби-саби",
        description="Японская сдержанность, керамика, рисовая бумага, асимметрия.",
        palette=ThemePalette(
            window="#e8dfd2",
            surface="#f0e9de",
            surface_alt="#d6cec2",
            text="#2f3b4c",
            text_muted="#625d55",
            accent="#5f6d5a",
            accent_hover="#52604d",
            accent_text="#f7f3ec",
            border="#c2b8a9",
            header="#d6cec2",
            header_text="#2f3b4c",
            selection="#cfd6c9",
            selection_text="#2f3b4c",
            positive="#46603f",
            negative="#8f3b2e",
            accent_secondary="#8a6f4e",
            accent_pressed="#465242",
            focus_ring="#4f5c4a",
            warning="#8a5a00",
            shadow="#8a7a66",
        ),
        font_family="Segoe UI",
        font_heading="Georgia",
        font_mono="Consolas",
        font_size=10,
        radius=3,
        border_width=1,
        spacing_scale=1.15,
    ),
    Theme(
        id=THEME_Y2K_CHROME,
        name="Y2K-хром",
        description="Жидкий металл, иридесценция, стеклянные пузыри, пилюли.",
        palette=ThemePalette(
            window="#e6e9ef",
            surface="#f4f6fa",
            surface_alt="#d7dce6",
            text="#1a1d24",
            text_muted="#4b5261",
            accent="#6fd3ff",
            accent_hover="#4cc3f7",
            accent_text="#1a1d24",
            border="#aeb6c4",
            header="#cfd6e2",
            header_text="#1a1d24",
            selection="#d6f0ff",
            selection_text="#1a1d24",
            positive="#177a4f",
            negative="#b42318",
            accent_secondary="#b79cff",
            accent_pressed="#2fb0ea",
            focus_ring="#2f6fed",
            warning="#a15c00",
            shadow="#8a93a3",
        ),
        font_family="Segoe UI",
        font_heading="Trebuchet MS",
        font_mono="Consolas",
        font_size=10,
        radius=16,
        border_width=1,
    ),
    Theme(
        id=THEME_EDITORIAL_MODERN,
        name="Редакционный модерн",
        description="Газетная вёрстка, крупные серифы, колонки, алый акцент.",
        palette=ThemePalette(
            window="#f3efe6",
            surface="#fbf8f1",
            surface_alt="#e9e3d7",
            text="#141414",
            text_muted="#5f5b54",
            accent="#c8322b",
            accent_hover="#ad2721",
            accent_text="#ffffff",
            border="#bdb6aa",
            header="#e5dfd3",
            header_text="#141414",
            selection="#f0d9d6",
            selection_text="#141414",
            positive="#1d6b3a",
            negative="#a8241d",
            accent_secondary="#141414",
            accent_pressed="#911d18",
            focus_ring="#c8322b",
            warning="#8a5a00",
            shadow="#6e6a63",
        ),
        font_family="Georgia",
        font_heading="Georgia",
        font_mono="Consolas",
        font_size=10,
        radius=2,
        border_width=1,
    ),
    Theme(
        id=THEME_SOVIET_SPACE,
        name="Советский космос",
        description="Космическая гонка 60-х, приборные панели, схемы, трафареты.",
        palette=ThemePalette(
            window="#13213d",
            surface="#1c2c4a",
            surface_alt="#24365a",
            text="#ede3c8",
            text_muted="#a9b7cc",
            accent="#e0782f",
            accent_hover="#f08a3f",
            accent_text="#13213d",
            border="#3a4c6e",
            header="#24365a",
            header_text="#ede3c8",
            selection="#2c4470",
            selection_text="#ede3c8",
            positive="#7fd6a1",
            negative="#ff8f7a",
            accent_secondary="#8c949e",
            accent_pressed="#c9661f",
            focus_ring="#ffb066",
            warning="#f0b429",
            shadow="#0a1224",
        ),
        font_family="Segoe UI",
        font_heading="Bahnschrift",
        font_mono="Consolas",
        font_size=10,
        radius=4,
        border_width=1,
    ),
    Theme(
        id=THEME_MEMPHIS_POSTMODERN,
        name="Мемфис-постмодерн",
        description="Игровая геометрия, зигзаги, пастель, чёрные контуры.",
        palette=ThemePalette(
            window="#fbf7f0",
            surface="#ffffff",
            surface_alt="#f2ebdd",
            text="#111111",
            text_muted="#5c5c5c",
            accent="#ff7f6e",
            accent_hover="#ff6450",
            accent_text="#111111",
            border="#111111",
            header="#9fe3d0",
            header_text="#111111",
            selection="#f7e45b",
            selection_text="#111111",
            positive="#1f7a3a",
            negative="#b42318",
            accent_secondary="#c9b6f2",
            accent_pressed="#e94f3c",
            focus_ring="#1d3a8a",
            warning="#a86400",
            shadow="#111111",
        ),
        font_family="Segoe UI",
        font_heading="Verdana",
        font_mono="Consolas",
        font_size=10,
        radius=14,
        border_width=2,
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
    focus_bw = max(2, bw)
    heading = theme.heading_font
    mono = theme.mono_font
    weight = "font-weight: 700;" if theme.bold_text else ""

    def px(value: float) -> int:
        return max(1, round(value * theme.spacing_scale))

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
    padding-left: {px(9)}px;
    padding-top: {px(7)}px;
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
    padding: {px(7)}px {px(16)}px;
    margin-right: 2px;
    font-family: "{heading}";
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
    padding-top: {px(8)}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {p.text};
    font-family: "{heading}";
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    border-radius: {r}px;
    padding: {px(4)}px {px(8)}px;
    selection-background-color: {p.accent};
    selection-color: {p.accent_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border: {focus_bw}px solid {p.focus_ring};
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
    padding: {px(6)}px {px(14)}px;
}}
QPushButton:hover {{
    border-color: {p.accent};
    color: {p.accent};
}}
QPushButton:pressed {{
    background-color: {p.surface_alt};
}}
QPushButton:focus {{
    border: {focus_bw}px solid {p.focus_ring};
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
QPushButton#primaryButton:pressed {{
    background-color: {p.accent_pressed};
    color: {p.accent_text};
}}
QCheckBox {{
    color: {p.text};
    spacing: 6px;
}}
QCheckBox:focus {{
    color: {p.focus_ring};
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
QTableWidget:focus, QTableView:focus {{
    border: {focus_bw}px solid {p.focus_ring};
}}
QHeaderView::section {{
    background-color: {p.header};
    color: {p.header_text};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border};
    padding: {px(6)}px;
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
    padding: {px(8)}px {px(12)}px;
}}
QListWidget::item:selected {{
    background-color: {p.accent};
    color: {p.accent_text};
}}
QListWidget::item:hover {{
    background-color: {p.surface_alt};
}}
QListWidget:focus, QListView:focus {{
    border: {focus_bw}px solid {p.focus_ring};
}}
QScrollArea {{
    background-color: {p.window};
    border: none;
}}
QStatusBar {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    border-top: 1px solid {p.border};
    font-family: "{mono}";
}}
QToolTip {{
    background-color: {p.surface};
    color: {p.text};
    border: {bw}px solid {p.border};
    padding: {px(4)}px {px(6)}px;
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
QPlainTextEdit#warningsView {{
    border: none;
    border-left: 3px solid {p.warning};
    padding-left: 8px;
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
