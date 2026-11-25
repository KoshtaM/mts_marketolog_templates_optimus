"""Экран дашборда: сводка по выбранной загрузке.

Композиция следует иерархии внимания: сверху — ключевые показатели и потенциал
роста, ниже — динамика, структура и точные значения в компактных таблицах.
Дополнительные разрезы (абоненты) вынесены в переключатель видов, чтобы обзор
помещался на одном экране без прокрутки.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from string import Template

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    BatchStatistics,
    DailySegments,
    DashboardSummary,
    ImportBatch,
    OperatorStatistics,
    SegmentationStatistics,
    SubscriberOperatorShare,
)
from mts_templates.application.use_cases.dashboard import GetDashboardSummary, ListBatches
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.daily_chart import build_daily_chart
from mts_templates.presentation.desktop.distribution import group_buckets
from mts_templates.presentation.desktop.formatting import (
    format_average,
    format_int,
    format_money,
    format_operators,
    format_percent,
    format_period,
)
from mts_templates.presentation.desktop.operator_colors import (
    OTHER_COLOR,
    operator_color,
)
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.theme_catalog import Theme, ThemePalette
from mts_templates.presentation.desktop.widgets.distribution_chart import (
    DARK_MUSTARD_GRADIENT,
    DistributionChart,
)
from mts_templates.presentation.desktop.widgets.pie_chart import PieChart, PieSlice
from mts_templates.presentation.desktop.widgets.share_bar import (
    ShareBarChart,
    ShareMeter,
    SharePart,
    ShareRow,
)
from mts_templates.presentation.desktop.widgets.stacked_bar_chart import StackedBarChart
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

CHART_OPERATOR_LIMIT = 5
DAILY_CHART_MIN_HEIGHT = 230
OPERATOR_TOP = 6
# Базовая минимальная высота круговой диаграммы абонентов: поднимается до
# высоты соседних гистограмм, чтобы подблоки ряда были одной высоты.
AUDIENCE_PIE_MIN_HEIGHT = 200
# Минимальная высота ряда круговых диаграмм в «Структуре». Если правой колонке
# не хватает места на этот ряд, «Структура» остаётся компактной с полосами.
STRUCTURE_PIE_MIN_HEIGHT = 200

# Шаблонированные SMS в диаграммах долей — «морская волна»: чистый зелёный
# зарезервирован за корпоративным цветом МегаФона в диаграммах операторов.
TEMPLATED_CHART_COLOR = "#0d9488"

# Карточка выгоды — главный показатель, стоимость чуть шире остальных.
CARD_STRETCH = (130, 115, 100, 100, 100, 100)
BENEFIT_BASE_HINT = "в месяц, после вычета стоимости шаблонов"
BENEFIT_SAVING_FONT_SIZE = 15

MAIN_COLUMNS = (
    "Класс",
    "Сообщений",
    "Сегментов",
    "Счёт",
    "Средняя стоимость сегмента",
    "Доля",
)
MAIN_ROWS = (
    ("total", "Всего", "tableRowLabelTotal"),
    ("ordinary", "Обычные", "tableRowLabel"),
    ("templated", "Шаблонированные", "tableRowLabel"),
)
OPERATOR_COLUMNS = ("Оператор", "Сообщений", "Сегментов", "Счёт", "Доля")

_DASHBOARD_STYLE = Template("""
#dashboardPage {
    background: $window;
}
#dashboardContent {
    background: $window;
}
#dashboardViewport {
    background: $window;
}
#metricCard, #sectionCard {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
}
#metricCard[tone="positive"] {
    border-left: 3px solid $positive;
}
#metricCard[tone="negative"] {
    border-left: 3px solid $negative;
}
#metricTitle {
    color: $text_muted;
    font-size: 11px;
}
#metricValue {
    color: $text;
    font-size: 22px;
    font-weight: 600;
}
QLabel#metricValue[tone="positive"] {
    color: $positive;
}
QLabel#metricValue[tone="negative"] {
    color: $negative;
}
#metricHint {
    color: $text_muted;
    font-size: 11px;
}
#sectionTitle {
    color: $text;
    font-size: 14px;
    font-weight: 600;
}
#sectionHint {
    color: $text_muted;
    font-size: 11px;
}
#tableHeader {
    color: $text_muted;
    font-size: 11px;
    font-weight: 600;
    border-bottom: 1px solid $border;
    padding: 0 0 5px 0;
}
#tableCell {
    color: $text;
    font-size: 13px;
    padding: 4px 0;
}
#tableCellMuted {
    color: $text_muted;
    font-size: 13px;
    padding: 4px 0;
}
#tableRowLabel {
    color: $text;
    font-size: 13px;
    padding: 4px 0;
}
#tableRowLabelTotal {
    color: $text;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 0;
}
#tableEmpty {
    color: $text_muted;
    font-size: 12px;
    padding: 8px 0;
}
#potentialLine {
    color: $text_muted;
    font-size: 12px;
}
#insightLine {
    color: $text_muted;
    font-size: 11px;
}
#viewSwitch {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 9px;
}
#viewSwitchButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 14px;
    color: $text_muted;
    font-weight: 600;
}
#viewSwitchButton:hover {
    color: $text;
}
#viewSwitchButton:checked {
    background: $surface;
    border: 1px solid $border;
    color: $text;
}
#subBlock {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 10px;
}
#warningsCard {
    background: $surface;
    border: 1px solid $border;
    border-left: 3px solid $warning;
    border-radius: 12px;
}
#warningsToggle {
    background: transparent;
    border: none;
    color: $text;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 2px;
    text-align: left;
}
#warningsToggle:hover {
    color: $accent;
}
#warningsView {
    background: transparent;
    border: none;
    color: $text_muted;
    font-size: 11px;
}
#toolbarLabel {
    color: $text_muted;
}
#subtitle {
    color: $text_muted;
    font-size: 12px;
}
QComboBox {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 5px 10px;
}
QComboBox:hover {
    border-color: $accent;
}
#primaryButton {
    background: $accent;
    color: $accent_text;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-weight: 600;
}
#primaryButton:hover {
    background: $accent_hover;
}
#primaryButton:pressed {
    background: $accent_pressed;
}
""")


def dashboard_style(palette: ThemePalette) -> str:
    """Собрать QSS дашборда из палитры активной темы."""
    return _DASHBOARD_STYLE.substitute(
        window=palette.window,
        surface=palette.surface,
        surface_alt=palette.surface_alt,
        border=palette.border,
        text=palette.text,
        text_muted=palette.text_muted,
        accent=palette.accent,
        accent_hover=palette.accent_hover,
        accent_pressed=palette.accent_pressed,
        accent_text=palette.accent_text,
        positive=palette.positive,
        negative=palette.negative,
        warning=palette.warning,
    )


class _MetricCard(QFrame):
    """Карточка показателя: заголовок, значение и короткое пояснение."""

    def __init__(self, title: str, hint: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setProperty("tone", "neutral")
        self._default_hint = hint

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(1)

        self._title = QLabel(title, self)
        self._title.setObjectName("metricTitle")
        self._value = QLabel("—", self)
        self._value.setObjectName("metricValue")
        self._value.setProperty("tone", "neutral")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._hint = QLabel(hint, self)
        self._hint.setObjectName("metricHint")
        self._hint.setWordWrap(True)

        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._hint)

    def set_value(self, text: str, *, tone: str = "neutral") -> None:
        self._value.setText(text)
        if self._value.property("tone") == tone and self.property("tone") == tone:
            return
        self._value.setProperty("tone", tone)
        self.setProperty("tone", tone)
        self._repolish()

    def set_hint(self, text: str, *, rich: bool = False) -> None:
        """Показать подпись. `rich=True` — текст с HTML-разметкой."""
        self._hint.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
        self._hint.setText(text)
        self._hint.setVisible(bool(text))

    def reset(self) -> None:
        self.set_value("—")
        self.set_hint(self._default_hint)
        self.setToolTip("")

    def _repolish(self) -> None:
        for widget in (self, self._value):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)


class DashboardPage(QWidget):
    """Показывает объёмы, стоимость и результат последнего анализа."""

    def __init__(
        self,
        *,
        dashboard: GetDashboardSummary,
        list_batches: ListBatches,
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(dashboard_style(active_palette()))

        self._dashboard = dashboard
        self._list_batches = list_batches
        self._runner = runner
        self._cards: dict[str, _MetricCard] = {}
        self._cells: dict[str, QLabel] = {}
        self._class_shares: dict[str, ShareMeter] = {}
        self._last_summary: DashboardSummary | None = None
        self._structure_pies_visible = False

        self._batch_combo = QComboBox(self)
        self._batch_combo.setMinimumContentsLength(20)
        self._batch_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._refresh_button = QPushButton("Обновить", self)
        self._refresh_button.setObjectName("primaryButton")
        self._batch_label = QLabel("—", self)
        self._batch_label.setObjectName("subtitle")
        self._batch_label.setWordWrap(True)

        self._build()
        self.reload()

    def apply_theme(self, theme: Theme) -> None:
        """Пересобрать локальные стили дашборда под выбранную тему."""
        self.setStyleSheet(dashboard_style(theme.palette))
        if self._last_summary is not None:
            self._show(self._last_summary)
        self.update()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Переключить «Структуру» между полосами и диаграммами по высоте колонки."""
        if watched is self._right_column and event.type() == QEvent.Type.Resize:
            self._update_structure_mode()
        return super().eventFilter(watched, event)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget(self)
        content.setObjectName("dashboardContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        self._views = QStackedWidget(content)
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._batch_label)

        self._overview = self._build_overview(content)
        self._audience = self._build_audience(content)
        self._views.addWidget(self._overview)
        self._views.addWidget(self._audience)
        layout.addWidget(self._views, stretch=1)
        layout.addWidget(self._build_warnings_section(content))

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.viewport().setObjectName("dashboardViewport")
        outer.addWidget(scroll)

        self._batch_combo.currentIndexChanged.connect(self._batch_changed)
        self._refresh_button.clicked.connect(self.refresh)

    def _build_toolbar(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)
        caption = QLabel("Загрузка", self)
        caption.setObjectName("toolbarLabel")
        header.addWidget(caption)
        header.addWidget(self._batch_combo, stretch=1)
        header.addWidget(self._build_view_switch())
        header.addWidget(self._refresh_button)
        return header

    def _build_view_switch(self) -> QFrame:
        """Переключатель видов «Обзор / Абоненты» в стиле сегментированного контроля."""
        frame = QFrame(self)
        frame.setObjectName("viewSwitch")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._view_group = QButtonGroup(frame)
        self._view_group.setExclusive(True)
        for index, label in enumerate(("Обзор", "Абоненты")):
            button = QPushButton(label, frame)
            button.setObjectName("viewSwitchButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._view_group.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        self._view_group.idClicked.connect(self._switch_view)
        return frame

    def _switch_view(self, index: int) -> None:
        self._views.setCurrentIndex(index)
        if index == 0:
            QTimer.singleShot(0, self._update_structure_mode)

    def _build_overview(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._build_cards(page))

        self._potential = QLabel(page)
        self._potential.setObjectName("potentialLine")
        self._potential.setTextFormat(Qt.TextFormat.RichText)
        self._potential.setWordWrap(True)
        self._potential.setVisible(False)
        layout.addWidget(self._potential)

        layout.addWidget(self._build_columns(page), stretch=1)
        return page

    def _build_cards(self, parent: QWidget) -> QWidget:
        """Шесть непересекающихся KPI: выгода, стоимость, объём и инвентарь."""
        container = QWidget(parent)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        definitions = (
            ("benefit", "Выгода шаблонов", BENEFIT_BASE_HINT),
            ("cost", "Стоимость, ₽", "средняя цена сегмента —"),
            ("messages", "Сообщений", "SMS-сегментов: —"),
            ("delivered_share", "Доставлено", "успешная доставка"),
            ("templates", "Шаблонов", "активных —"),
            ("candidates", "Кандидатов", "по последнему анализу"),
        )
        for column, (key, title, hint) in enumerate(definitions):
            card = _MetricCard(title, hint, container)
            grid.addWidget(card, 0, column)
            self._cards[key] = card
        for column, stretch in enumerate(CARD_STRETCH):
            grid.setColumnStretch(column, stretch)
        return container

    def _build_columns(self, parent: QWidget) -> QWidget:
        """Две колонки 3:2: динамика и классы слева, структура и операторы справа."""
        container = QWidget(parent)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        left = QWidget(container)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        daily = self._build_daily_section(left)
        main = self._build_main_section(left)
        left_layout.addWidget(daily, stretch=1)
        left_layout.addWidget(main)

        right = QWidget(container)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        structure = self._build_structure_section(right)
        operators = self._build_operator_section(right)
        right_layout.addWidget(structure)
        right_layout.addWidget(operators, stretch=1)
        right_layout.setStretch(0, 0)
        right_layout.setStretch(1, 1)
        self._right_column = right
        self._right_layout = right_layout
        right.installEventFilter(self)

        grid.addWidget(left, 0, 0)
        grid.addWidget(right, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setRowStretch(0, 1)
        return container

    def _update_structure_mode(self) -> None:
        """Показать в «Структуре» круговые диаграммы, если колонка позволяет.

        В компактном режиме «Структура» занимает высоту по содержимому, а
        свободное место забирает таблица операторов. В расширенном — таблица
        операторов фиксируется по содержимому, а «Структура» растягивается и
        показывает две круговые диаграммы.
        """
        if self._right_column.height() <= 0:
            return

        structure = self._structure_box
        pie_row = self._structure_pie_row
        pie_height = max(pie_row.sizeHint().height(), STRUCTURE_PIE_MIN_HEIGHT)
        share_height = self._share_chart.sizeHint().height()
        if self._structure_pies_visible:
            expanded = structure.sizeHint().height()
            compact = max(expanded - pie_height + share_height, 0)
        else:
            compact = structure.sizeHint().height()
            expanded = compact - share_height + pie_height

        show_pies = _structure_pies_fit(
            self._right_column.height(),
            expanded,
            self._operator_box.sizeHint().height(),
            self._right_layout.spacing(),
        )
        if show_pies == self._structure_pies_visible:
            return

        self._structure_pies_visible = show_pies
        self._share_chart.setVisible(not show_pies)
        pie_row.setVisible(show_pies)
        if show_pies:
            structure.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._operator_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._right_layout.setStretch(0, 1)
            self._right_layout.setStretch(1, 0)
        else:
            structure.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._operator_box.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
            )
            self._right_layout.setStretch(0, 0)
            self._right_layout.setStretch(1, 1)
        structure.updateGeometry()
        self._operator_box.updateGeometry()

    def _section(self, title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout, QLabel]:
        """Карточка раздела: заголовок, подпись справа и тело."""
        box = QFrame(self)
        box.setObjectName("sectionCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title_label = QLabel(title, box)
        title_label.setObjectName("sectionTitle")
        hint_label = QLabel(hint, box)
        hint_label.setObjectName("sectionHint")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hint_label.setVisible(bool(hint))
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(hint_label)
        layout.addLayout(header)
        return box, layout, hint_label

    def _build_daily_section(self, parent: QWidget) -> QWidget:
        """Динамика SMS-сегментов по дням и операторам."""
        box, body, self._daily_caption = self._section("Динамика по дням")
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._daily_chart = StackedBarChart("", box)
        self._daily_chart.setMinimumHeight(DAILY_CHART_MIN_HEIGHT)
        self._daily_chart.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self._daily_chart, stretch=1)
        return box

    def _build_main_section(self, parent: QWidget) -> QWidget:
        """Компактная таблица классов сообщений с мини-долями."""
        box, body, _hint = self._section("Классы сообщений", "доли — по SMS-сегментам")
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(0)
        for column, text in enumerate(MAIN_COLUMNS):
            label = QLabel(text, box)
            label.setObjectName("tableHeader")
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            label.setAlignment(_column_alignment(column))
            grid.addWidget(label, 0, column)

        accent = active_palette()
        for row, (prefix, text, style_name) in enumerate(MAIN_ROWS, start=1):
            name = QLabel(text, box)
            name.setObjectName(style_name)
            grid.addWidget(name, row, 0)
            for column, suffix in enumerate(("messages", "segments", "cost", "average"), start=1):
                cell = QLabel("—", box)
                cell.setObjectName("tableCell")
                cell.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(cell, row, column)
                self._cells[f"{prefix}_{suffix}"] = cell
            meter = ShareMeter(0.0, accent.text_muted, box)
            grid.addWidget(meter, row, len(MAIN_COLUMNS) - 1, Qt.AlignmentFlag.AlignRight)
            self._class_shares[prefix] = meter

        for column in range(len(MAIN_COLUMNS)):
            grid.setColumnStretch(column, 1 if column < len(MAIN_COLUMNS) - 1 else 0)
        body.addLayout(grid)
        return box

    def _build_structure_section(self, parent: QWidget) -> QWidget:
        """Доли SMS-сегментов и расходов по классам сообщений.

        Компактный режим — горизонтальные полосы. Если в правой колонке есть
        запас высоты, полосы заменяются двумя круговыми диаграммами: так
        освободившееся под таблицей операторов место используется, а не
        остаётся пустым.
        """
        box, body, _hint = self._section("Структура", "доли SMS-сегментов и расходов")
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._structure_box = box

        self._share_chart = ShareBarChart(box)
        self._share_chart.setMinimumHeight(96)
        body.addWidget(self._share_chart)

        self._structure_pie_row = QWidget(box)
        self._structure_pie_row.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._structure_pie_row.setMinimumHeight(STRUCTURE_PIE_MIN_HEIGHT)
        self._structure_pie_row.setVisible(False)
        pie_layout = QHBoxLayout(self._structure_pie_row)
        pie_layout.setContentsMargins(0, 0, 0, 0)
        pie_layout.setSpacing(12)
        self._segment_share_pie = PieChart("Доли SMS-сегментов", self._structure_pie_row)
        self._cost_share_pie = PieChart("Доли расходов", self._structure_pie_row)
        pie_layout.addWidget(
            self._sub_block(self._structure_pie_row, self._segment_share_pie, expanding=True),
            stretch=1,
        )
        pie_layout.addWidget(
            self._sub_block(self._structure_pie_row, self._cost_share_pie, expanding=True),
            stretch=1,
        )
        body.addWidget(self._structure_pie_row, stretch=1)

        self._structure_insight = QLabel("", box)
        self._structure_insight.setObjectName("insightLine")
        self._structure_insight.setTextFormat(Qt.TextFormat.RichText)
        self._structure_insight.setWordWrap(True)
        body.addWidget(self._structure_insight)
        return box

    def _build_operator_section(self, parent: QWidget) -> QWidget:
        """Операторы получателя: точные значения и мини-доля сообщений."""
        box, body, self._operator_hint = self._section(
            "Операторы получателя", "доля — от сообщений"
        )
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._operator_box = box

        self._operator_rows = QGridLayout()
        self._operator_rows.setContentsMargins(0, 0, 0, 0)
        self._operator_rows.setHorizontalSpacing(12)
        self._operator_rows.setVerticalSpacing(0)
        for column, text in enumerate(OPERATOR_COLUMNS):
            label = QLabel(text, box)
            label.setObjectName("tableHeader")
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            label.setAlignment(_column_alignment(column))
            self._operator_rows.addWidget(label, 0, column)
        for column in range(len(OPERATOR_COLUMNS)):
            self._operator_rows.setColumnStretch(
                column, 1 if column < len(OPERATOR_COLUMNS) - 1 else 0
            )
        body.addLayout(self._operator_rows)

        self._operator_insight = QLabel("", box)
        self._operator_insight.setObjectName("insightLine")
        self._operator_insight.setWordWrap(True)
        body.addWidget(self._operator_insight)
        body.addStretch(1)
        return box

    def _build_audience(self, parent: QWidget) -> QWidget:
        """Второй вид: абоненты и распределения по числу SMS-сегментов."""
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_subscriber_cards(page))

        box, body, _hint = self._section(
            "Распределения", "абоненты и сообщения по числу SMS-сегментов"
        )
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._subscriber_segment_chart = DistributionChart("Абоненты по числу сегментов", box)
        self._subscriber_operator_chart = PieChart("Абоненты по операторам", box)
        self._message_segment_chart = DistributionChart(
            "Сообщения по числу сегментов",
            box,
            exact_gradient=DARK_MUSTARD_GRADIENT,
        )

        charts = QGridLayout()
        charts.setHorizontalSpacing(12)
        charts.setVerticalSpacing(12)
        charts.addWidget(self._sub_block(box, self._subscriber_segment_chart), 0, 0)
        charts.addWidget(self._sub_block(box, self._subscriber_operator_chart), 0, 1)
        charts.addWidget(self._sub_block(box, self._message_segment_chart), 0, 2)
        for column in range(3):
            charts.setColumnStretch(column, 1)
        body.addLayout(charts)

        hint = QLabel(
            "Абонент — уникальный номер получателя с отправленными сегментами; "
            "оператор абонента — тот, по которому у него больше сообщений. "
            "Сообщения с ошибкой отправки (0 сегментов) не входят.",
            box,
        )
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        body.addWidget(hint)

        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _build_subscriber_cards(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        definitions = (
            ("subscribers", "Уникальных абонентов", "номеров получателей"),
            ("subscriber_segments", "Сегментов на абонента", "в среднем за период"),
            ("subscriber_messages", "Сообщений на абонента", "в среднем за период"),
        )
        for column, (key, title, hint) in enumerate(definitions):
            card = _MetricCard(title, hint, container)
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
            self._cards[key] = card
        return container

    def _sub_block(
        self,
        parent: QWidget,
        content: QWidget,
        *,
        expanding: bool = False,
    ) -> QFrame:
        """Подблок секции: скруглённая карточка с отдельным фоном.

        По умолчанию высота подблока равна содержимому: так диаграммы
        распределений не растягиваются на весь экран. `expanding=True` —
        для подблоков, которые должны занять свободную высоту секции.
        """
        frame = QFrame(parent)
        frame.setObjectName("subBlock")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        frame.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if expanding else QSizePolicy.Policy.Fixed,
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(6)
        frame_layout.addWidget(content, stretch=1 if expanding else 0)
        return frame

    def _build_warnings_section(self, parent: QWidget) -> QWidget:
        """Свёрнутая панель предупреждений и допущений."""
        box = QFrame(parent)
        box.setObjectName("warningsCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 8, 14, 10)
        layout.setSpacing(4)

        self._warnings_toggle = QPushButton(box)
        self._warnings_toggle.setObjectName("warningsToggle")
        self._warnings_toggle.setCheckable(True)
        self._warnings_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._warnings_toggle.clicked.connect(self._toggle_warnings)
        layout.addWidget(self._warnings_toggle)

        self._warnings = QPlainTextEdit(box)
        self._warnings.setObjectName("warningsView")
        self._warnings.setReadOnly(True)
        self._warnings.setMinimumHeight(96)
        self._warnings.setMaximumHeight(140)
        self._warnings.setVisible(False)
        layout.addWidget(self._warnings)
        self._set_warnings(())
        return box

    def _toggle_warnings(self) -> None:
        expanded = self._warnings_toggle.isChecked()
        self._warnings.setVisible(expanded)
        self._update_warnings_title()

    def _set_warnings(self, lines: Sequence[str]) -> None:
        self._warning_lines = tuple(lines)
        text = "\n".join(f"• {line}" for line in lines) if lines else "Предупреждений нет."
        self._warnings.setPlainText(text)
        self._update_warnings_title()

    def _update_warnings_title(self) -> None:
        expanded = self._warnings_toggle.isChecked()
        marker = "▾" if expanded else "▸"
        count = len(self._warning_lines)
        suffix = f" · {count}" if count else ""
        self._warnings_toggle.setText(f"{marker} Предупреждения и допущения{suffix}")

    def reload(self) -> None:
        """Перечитать список загрузок и обновить сводку."""
        try:
            batches = self._list_batches.execute()
        except Exception as exc:  # БД может быть недоступна
            QMessageBox.critical(self, "Ошибка", str(exc))
            return

        current = self._batch_combo.currentData()
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        for batch in batches:
            self._batch_combo.addItem(_batch_title(batch), batch.id)
        if current is not None:
            index = self._batch_combo.findData(current)
            if index >= 0:
                self._batch_combo.setCurrentIndex(index)
        self._batch_combo.blockSignals(False)

        if not batches:
            self._fill_empty()
            return
        self.refresh()

    def refresh(self) -> None:
        batch_id = self._batch_combo.currentData()
        self._runner.run(
            lambda _token: self._dashboard.execute(batch_id),
            on_success=self._show,
            on_error=self._failed,
        )

    def _batch_changed(self, _index: int) -> None:
        self.refresh()

    def _show(self, summary: DashboardSummary) -> None:
        self._last_summary = summary
        if summary.batch is None or summary.statistics is None:
            self._fill_empty(summary)
            return

        statistics = summary.statistics
        batch = summary.batch
        self._batch_label.setText(_subtitle(batch))
        self._fill_cards(summary)
        self._fill_main(statistics)
        self._fill_operators(summary.operators)
        self._fill_daily(summary.daily_segments)
        self._fill_additional(summary.segmentation)
        self._set_warnings(summary.warnings)
        QTimer.singleShot(0, self._update_structure_mode)

    def _fill_cards(self, summary: DashboardSummary) -> None:
        statistics = summary.statistics
        if statistics is None:
            return

        self._cards["messages"].set_value(format_int(statistics.message_count))
        self._cards["messages"].set_hint(f"SMS-сегментов: {format_int(statistics.segments)}")
        self._cards["cost"].set_value(format_money(statistics.cost))
        self._cards["cost"].set_hint(
            f"средняя цена сегмента {format_money(statistics.average_segment_cost)}"
        )
        self._cards["delivered_share"].set_value(format_percent(statistics.delivered_share))
        self._cards["delivered_share"].set_hint(
            f"{format_int(statistics.delivered)} из {format_int(statistics.message_count)}"
        )
        self._cards["templates"].set_value(format_int(summary.template_count))
        self._cards["templates"].set_hint(
            f"активных {format_int(summary.active_templates)} · "
            f"неактивных {format_int(summary.inactive_templates)}"
        )
        self._cards["candidates"].set_value(format_int(summary.candidates))
        self._cards["candidates"].set_hint(_candidates_hint(summary), rich=True)

        benefit = summary.total_monthly_net_benefit
        if benefit is None:
            self._cards["benefit"].set_value("—")
            self._cards["benefit"].set_hint("анализ не выполнялся")
            self._cards["benefit"].setToolTip("")
            self._fill_potential(summary, None)
            return
        tone = "neutral"
        if benefit.amount > 0:
            tone = "positive"
        elif benefit.amount < 0:
            tone = "negative"
        self._cards["benefit"].set_value(format_money(benefit), tone=tone)
        self._cards["benefit"].set_hint(BENEFIT_BASE_HINT)
        self._cards["benefit"].setToolTip(_benefit_tooltip(summary))
        self._fill_potential(summary, benefit)

    def _fill_potential(self, summary: DashboardSummary, benefit: Money | None) -> None:
        potential = summary.potential_benefit
        if benefit is None or potential is None or potential.amount <= 0:
            self._potential.setVisible(False)
            self._potential.setText("")
            return

        parts = [f"Потенциал роста: {_saving_span(potential)} в месяц"]
        savings = _benefit_savings(summary)
        if savings:
            detail = " · ".join(f"{label} {_saving_text(value)}" for label, value in savings)
            parts.append(detail)
        self._potential.setText(" · ".join(parts))
        self._potential.setVisible(True)

    def _fill_main(self, statistics: BatchStatistics) -> None:
        self._set_cell("total_messages", format_int(statistics.message_count))
        self._set_cell("total_segments", format_int(statistics.segments))
        self._set_cell("total_cost", format_money(statistics.cost))
        self._set_cell("total_average", format_money(statistics.average_segment_cost))

        self._set_cell("ordinary_messages", format_int(statistics.ordinary_messages))
        self._set_cell("ordinary_segments", format_int(statistics.ordinary_segments))
        self._set_cell("ordinary_cost", format_money(statistics.ordinary_cost))
        self._set_cell("ordinary_average", format_money(statistics.ordinary_average_segment_cost))

        self._set_cell("templated_messages", format_int(statistics.templated_messages))
        self._set_cell("templated_segments", format_int(statistics.templated_segments))
        self._set_cell("templated_cost", format_money(statistics.templated_cost))
        self._set_cell("templated_average", format_money(statistics.templated_average_segment_cost))

        palette = active_palette()
        self._class_shares["total"].set_share(
            1.0 if statistics.segments else 0.0, palette.text_muted
        )
        self._class_shares["ordinary"].set_share(
            statistics.ordinary_segment_share, palette.negative
        )
        self._class_shares["templated"].set_share(
            statistics.templated_segment_share, TEMPLATED_CHART_COLOR
        )

        self._share_chart.set_rows(
            (
                ShareRow(
                    "Сегменты",
                    format_int(statistics.segments),
                    (
                        SharePart("Обычные", float(statistics.ordinary_segments), palette.negative),
                        SharePart(
                            "Шаблонированные",
                            float(statistics.templated_segments),
                            TEMPLATED_CHART_COLOR,
                        ),
                    ),
                ),
                ShareRow(
                    "Счёт",
                    format_money(statistics.cost),
                    (
                        SharePart(
                            "Обычные",
                            float(statistics.ordinary_cost.amount),
                            palette.negative,
                        ),
                        SharePart(
                            "Шаблонированные",
                            float(statistics.templated_cost.amount),
                            TEMPLATED_CHART_COLOR,
                        ),
                    ),
                ),
            )
        )
        self._segment_share_pie.set_slices(
            (
                PieSlice("Обычные", float(statistics.ordinary_segments), palette.negative),
                PieSlice(
                    "Шаблонированные",
                    float(statistics.templated_segments),
                    TEMPLATED_CHART_COLOR,
                ),
            )
        )
        self._cost_share_pie.set_slices(
            (
                PieSlice("Обычные", float(statistics.ordinary_cost.amount), palette.negative),
                PieSlice(
                    "Шаблонированные",
                    float(statistics.templated_cost.amount),
                    TEMPLATED_CHART_COLOR,
                ),
            )
        )
        self._fill_structure_insight(statistics)

    def _fill_structure_insight(self, statistics: BatchStatistics) -> None:
        ordinary = statistics.ordinary_average_segment_cost
        templated = statistics.templated_average_segment_cost
        palette = active_palette()
        if ordinary is None or templated is None or ordinary.amount <= 0:
            self._structure_insight.setText("Средняя цена сегмента: —")
            return

        line = (
            "Средняя цена сегмента: "
            f'<span style="color: {palette.negative};">{format_money(ordinary)}</span> обычный · '
            f'<span style="color: {TEMPLATED_CHART_COLOR};">{format_money(templated)}</span> '
            "шаблонированный"
        )
        difference = (templated.amount - ordinary.amount) / ordinary.amount
        if difference < 0:
            verdict = (
                f'<span style="color: {palette.positive}; font-weight: 600;">'
                f"Шаблонированный сегмент дешевле на {abs(difference) * 100:.1f}%</span>"
            )
        elif difference > 0:
            verdict = (
                f'<span style="color: {palette.negative}; font-weight: 600;">'
                f"Шаблонированный сегмент дороже на {difference * 100:.1f}%</span>"
            )
        else:
            verdict = "Стоимость сегмента одинаковая"
        self._structure_insight.setText(f"{line}<br>{verdict}")

    def _fill_daily(self, daily: Sequence[DailySegments]) -> None:
        data = build_daily_chart(daily)
        self._daily_chart.set_data(data.bars, legend=data.legend)
        self._daily_caption.setText(data.caption)
        self._daily_caption.setVisible(bool(data.caption))

    def _fill_additional(self, segmentation: SegmentationStatistics | None) -> None:
        if segmentation is None:
            self._fill_additional_empty()
            return

        subscribers = segmentation.subscribers
        self._cards["subscribers"].set_value(format_int(subscribers))
        self._cards["subscribers"].set_hint(
            f"операторов: {len(segmentation.subscribers_by_operator)}"
        )
        self._cards["subscriber_segments"].set_value(
            format_average(segmentation.average_subscriber_segments)
        )
        self._cards["subscriber_messages"].set_value(
            format_average(segmentation.average_subscriber_messages)
        )

        self._subscriber_segment_chart.set_bars(
            group_buckets(segmentation.subscribers_by_segments),
            caption=f"всего {format_int(subscribers)}",
        )
        self._message_segment_chart.set_bars(
            group_buckets(segmentation.messages_by_segments),
            caption=f"всего {format_int(segmentation.subscriber_messages)}",
        )
        self._subscriber_operator_chart.setMinimumHeight(
            max(
                AUDIENCE_PIE_MIN_HEIGHT,
                self._subscriber_segment_chart.minimumHeight(),
                self._message_segment_chart.minimumHeight(),
            )
        )
        self._subscriber_operator_chart.set_slices(
            _subscriber_operator_slices(segmentation.subscribers_by_operator)
        )

    def _fill_additional_empty(self) -> None:
        for key in ("subscribers", "subscriber_segments", "subscriber_messages"):
            self._cards[key].reset()
        self._subscriber_segment_chart.set_bars(())
        self._message_segment_chart.set_bars(())
        self._subscriber_operator_chart.setMinimumHeight(AUDIENCE_PIE_MIN_HEIGHT)
        self._subscriber_operator_chart.set_slices(())

    def _fill_empty(self, summary: DashboardSummary | None = None) -> None:
        self._last_summary = summary
        for card in self._cards.values():
            card.reset()
        for cell in self._cells.values():
            cell.setText("—")
        for meter in self._class_shares.values():
            meter.set_share(0.0)
        self._share_chart.set_rows(())
        self._segment_share_pie.set_slices(())
        self._cost_share_pie.set_slices(())
        self._structure_insight.setText("Средняя цена сегмента: —")
        self._fill_operators(())
        self._fill_daily(())
        self._fill_additional_empty()
        self._potential.setVisible(False)
        self._potential.setText("")
        self._batch_label.setText("Статистика ещё не импортирована.")
        warnings = summary.warnings if summary is not None else ()
        self._set_warnings(warnings)
        QTimer.singleShot(0, self._update_structure_mode)

    def _fill_operators(self, operators: Sequence[OperatorStatistics]) -> None:
        """Заполнить таблицу операторов: топ по сообщениям плюс «Другие»."""
        self._clear_operator_rows()
        parent = self._operator_rows.parentWidget()
        total_messages = sum(item.messages for item in operators)
        rows = _top_operators(operators)

        if len(operators) > OPERATOR_TOP:
            self._operator_hint.setText(f"топ-{OPERATOR_TOP} · доля — от сообщений")
        else:
            self._operator_hint.setText("доля — от сообщений")
        self._operator_hint.setVisible(True)

        if not rows:
            empty = QLabel("Нет данных", parent)
            empty.setObjectName("tableEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._operator_rows.addWidget(empty, 1, 0, 1, len(OPERATOR_COLUMNS))
            self._operator_insight.setText("")
            return

        for row, item in enumerate(rows, start=1):
            share = item.messages / total_messages if total_messages else 0.0
            if item.operator == _OTHER_OPERATOR:
                name = item.operator
                name_style = "tableCellMuted"
                color = OTHER_COLOR
            else:
                name = format_operators((item.operator,))
                name_style = "tableCell"
                color = operator_color(item.operator)
            values = (
                name,
                format_int(item.messages),
                format_int(item.segments),
                format_money(item.cost),
            )
            for column, value in enumerate(values):
                cell = QLabel(value, parent)
                cell.setObjectName(name_style if column == 0 else "tableCell")
                cell.setAlignment(_column_alignment(column))
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                cell.setToolTip(item.operator)
                self._operator_rows.addWidget(cell, row, column)
            meter = ShareMeter(share, color, parent)
            self._operator_rows.addWidget(
                meter, row, len(OPERATOR_COLUMNS) - 1, Qt.AlignmentFlag.AlignRight
            )
        self._operator_insight.setText(_operator_concentration(operators))

    def _clear_operator_rows(self) -> None:
        """Удалить строки данных, оставив заголовки."""
        while self._operator_rows.count() > len(OPERATOR_COLUMNS):
            item = self._operator_rows.takeAt(self._operator_rows.count() - 1)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _failed(self, message: str) -> None:
        if message == CANCELLED_MESSAGE:
            return
        QMessageBox.critical(self, "Ошибка", message)

    def _set_cell(self, key: str, value: str) -> None:
        self._cells[key].setText(value)


_OTHER_OPERATOR = "Другие"


def _structure_pies_fit(
    available_height: int,
    expanded_structure: int,
    operators: int,
    spacing: int,
) -> bool:
    """Хватает ли высоты правой колонки на две круговые диаграммы."""
    return available_height >= expanded_structure + operators + spacing


def _operator_concentration(operators: Sequence[OperatorStatistics]) -> str:
    """Строка-вывод: крупнейший оператор и доля топ-3 по сообщениям."""
    total = sum(item.messages for item in operators)
    if not operators or total <= 0:
        return ""
    leader = operators[0]
    top_three = sum(item.messages for item in operators[:3])
    return (
        f"Крупнейший — {format_operators((leader.operator,))}: "
        f"{format_percent(leader.messages / total)} сообщений · "
        f"топ-3 — {format_percent(top_three / total)}"
    )


def _top_operators(
    operators: Sequence[OperatorStatistics],
    limit: int = OPERATOR_TOP,
) -> tuple[OperatorStatistics, ...]:
    """Топ операторов по сообщениям; остальные складываются в строку «Другие»."""
    if len(operators) <= limit:
        return tuple(operators)
    rest = operators[limit:]
    cost = Money.zero()
    for item in rest:
        cost = cost + item.cost
    other = OperatorStatistics(
        operator=_OTHER_OPERATOR,
        messages=sum(item.messages for item in rest),
        segments=sum(item.segments for item in rest),
        cost=cost,
    )
    return (*operators[:limit], other)


def _benefit_hint(summary: DashboardSummary) -> str:
    """Расчётные строки под значением карточки, обычным текстом."""
    return "\n".join(_benefit_lines(summary, _saving_text))


def _benefit_hint_html(summary: DashboardSummary) -> str:
    """Те же строки с крупными выделенными суммами экономии."""
    return "<br>".join(_benefit_lines(summary, _saving_span))


def _benefit_tooltip(summary: DashboardSummary) -> str:
    """Подсказка карточки: пояснение значения плюс расчётные строки."""
    return "\n".join([BENEFIT_BASE_HINT, *_benefit_lines(summary, _saving_text)])


def _benefit_lines(
    summary: DashboardSummary,
    render: Callable[[Money], str],
) -> list[str]:
    """Потенциал и его слагаемые: месячная сумма и одна строка детализации."""
    potential = summary.potential_benefit
    if potential is None or potential.amount == 0:
        return []
    lines = [f"потенциал: {render(potential)} в месяц"]
    savings = _benefit_savings(summary)
    if savings:
        lines.append(" · ".join(f"{label} {render(value)}" for label, value in savings))
    return lines


def _candidates_hint(summary: DashboardSummary) -> str:
    """Подпись карточки «Кандидатов»: всего и сколько из них выгодных."""
    if summary.profitable_candidates_benefit is None:
        return "по последнему анализу"
    return (
        "по последнему анализу<br>"
        f"выгодных: {_accent_span(format_int(summary.profitable_candidates))}"
    )


def _benefit_savings(summary: DashboardSummary) -> tuple[tuple[str, Money], ...]:
    """Слагаемые потенциала: внедрение кандидатов и удаление убыточных шаблонов."""
    savings: list[tuple[str, Money]] = []
    candidates = summary.profitable_candidates_benefit
    if candidates is not None and candidates.amount > 0:
        savings.append(("внедрение кандидатов", candidates))
    losses = summary.loss_templates_benefit
    if losses is not None and losses.amount < 0:
        savings.append(("удаление убыточных шаблонов", -losses))
    return tuple(savings)


def _saving_text(value: Money) -> str:
    """Сумма экономии со знаком: «+1 500.00 ₽»."""
    if value.amount >= 0:
        return f"+{format_money(value)}"
    return f"−{format_money(-value)}"


def _saving_span(value: Money) -> str:
    """Сумма экономии крупным зелёным шрифтом внутри rich-text подписи."""
    return _accent_span(_saving_text(value))


def _accent_span(text: str) -> str:
    """Выделить число в подписи: крупный зелёный полужирный шрифт."""
    return (
        f'<span style="color: {active_palette().positive}; '
        f'font-size: {BENEFIT_SAVING_FONT_SIZE}px; font-weight: 600;">'
        f"{text}</span>"
    )


def _subscriber_operator_slices(
    shares: Sequence[SubscriberOperatorShare],
) -> tuple[PieSlice, ...]:
    """Сектора абонентов по операторам; оператор абонента — по большинству сообщений."""
    return _slices_from_entries((item.operator, float(item.subscribers)) for item in shares)


def _slices_from_entries(
    entries: Iterable[tuple[str, float]],
    *,
    limit: int = CHART_OPERATOR_LIMIT,
) -> tuple[PieSlice, ...]:
    ordered = sorted(
        ((label, amount) for label, amount in entries if amount > 0),
        key=lambda entry: entry[1],
        reverse=True,
    )
    slices = [PieSlice(label, amount, operator_color(label)) for label, amount in ordered[:limit]]
    rest = sum(amount for _, amount in ordered[limit:])
    if rest > 0:
        slices.append(PieSlice("Другие", rest, OTHER_COLOR))
    return tuple(slices)


def _column_alignment(column: int) -> Qt.AlignmentFlag:
    if column == 0:
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


def _subtitle(batch: ImportBatch) -> str:
    """Файл, период и ошибки импорта одной строкой под заголовком."""
    parts = [
        Path(batch.source_path).name,
        format_period(batch.period_from, batch.period_to),
        f"импортирован {batch.imported_at.strftime('%d.%m.%Y %H:%M')}",
    ]
    if batch.send_error_rows or batch.delivery_error_rows:
        parts.append(
            f"ошибок отправки {format_int(batch.send_error_rows)}, "
            f"доставки {format_int(batch.delivery_error_rows)}"
        )
    return " · ".join(parts)


def _batch_title(batch: ImportBatch) -> str:
    return (
        f"{Path(batch.source_path).name} · "
        f"{format_period(batch.period_from, batch.period_to)} · "
        f"{format_int(batch.message_count)} сообщ."
    )
