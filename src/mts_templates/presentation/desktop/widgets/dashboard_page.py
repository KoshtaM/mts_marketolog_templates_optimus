"""Экран дашборда: сводка по выбранной загрузке."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    BatchStatistics,
    DashboardSummary,
    ImportBatch,
    OperatorStatistics,
    SegmentationStatistics,
    SubscriberOperatorShare,
)
from mts_templates.application.use_cases.dashboard import GetDashboardSummary, ListBatches
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.distribution import group_buckets
from mts_templates.presentation.desktop.formatting import (
    format_average,
    format_average_segments,
    format_int,
    format_money,
    format_percent,
    format_period,
)
from mts_templates.presentation.desktop.operator_colors import OTHER_COLOR, operator_color
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.theme_catalog import Theme, ThemePalette
from mts_templates.presentation.desktop.widgets.distribution_chart import (
    DARK_MUSTARD_GRADIENT,
    DistributionChart,
)
from mts_templates.presentation.desktop.widgets.pie_chart import PieChart, PieSlice
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

CHART_OPERATOR_LIMIT = 5

# Шаблонированные SMS в диаграммах долей — «морская волна»: чистый зелёный
# зарезервирован за корпоративным цветом МегаФона в диаграммах операторов.
TEMPLATED_CHART_COLOR = "#0d9488"

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
#metricTitle {
    color: $text_muted;
    font-size: 12px;
}
#metricValue {
    color: $text;
    font-size: 21px;
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
#metricValueCaption {
    color: $text_muted;
    font-size: 11px;
}
#sectionTitle {
    color: $text;
    font-size: 15px;
    font-weight: 600;
}
#sectionHint {
    color: $text_muted;
    font-size: 11px;
}
#mainHeader {
    background: $header;
    color: $header_text;
    font-size: 18px;
    padding: 2px 6px;
    border-radius: 4px;
}
#mainRowLabel {
    color: $text;
    font-size: 20px;
}
#mainRowLabelTotal {
    color: $text;
    font-size: 20px;
    font-weight: 600;
}
#mainCell {
    color: $text;
    font-size: 20px;
}
#mainCellShareOrdinary {
    color: $negative;
    font-size: 20px;
    font-weight: 600;
}
#mainCellShareTemplated {
    color: $positive;
    font-size: 20px;
    font-weight: 600;
}
#operatorTitle {
    color: $text;
    font-size: 15px;
    font-weight: 600;
}
#operatorHeader {
    background: $header;
    color: $header_text;
    font-size: 14px;
    padding: 2px 6px;
    border-radius: 4px;
}
#operatorCell {
    color: $text;
    font-size: 17px;
}
#subtitle {
    color: $text_muted;
    font-size: 12px;
}
#toolbarLabel {
    color: $text_muted;
}
#warningsView {
    background: transparent;
    border: none;
    border-left: 3px solid $warning;
    padding-left: 8px;
    color: $text_muted;
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
    color: $surface;
    border: none;
    border-radius: 8px;
    padding: 7px 18px;
    font-weight: 600;
}
#primaryButton:hover {
    background: $accent_hover;
}
#primaryButton:pressed {
    background: $accent_hover;
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
        header=palette.header,
        header_text=palette.header_text,
        accent=palette.accent,
        accent_hover=palette.accent_hover,
        positive=palette.positive,
        negative=palette.negative,
        warning=palette.warning,
    )


MAIN_COLUMNS = ("", "Сообщений", "Сегментов", "Счёт", "Средняя стоимость сегмента", "Процент")
MAIN_ROWS = (
    ("total", "Всего", "mainRowLabelTotal"),
    ("ordinary", "Обычные", "mainRowLabel"),
    ("templated", "Шаблонированные", "mainRowLabel"),
)
OPERATOR_COLUMNS = (
    "Оператор",
    "Всего сообщений",
    "Всего сегментов",
    "Счёт",
    "Средняя стоимость сегмента",
    "Доля (%)",
)
BENEFIT_BASE_HINT = "после вычета стоимости шаблонов"
BENEFIT_SAVING_FONT_SIZE = 15
# Карточки «Процент доставленных» и «Выгода шаблонов» на 30 % шире остальных.
CARD_WIDTH_FACTOR = 130
CARD_STRETCH = (100, 100, CARD_WIDTH_FACTOR)


class _MetricCard(QFrame):
    """Карточка одного показателя: заголовок, значение и пояснение.

    `hint_inline=True` ставит пояснение в одну строку со значением (для карточки
    выгоды: «270.00 ₽ · после вычета стоимости шаблонов»), а `_hint` оставляет
    под ним — под расчётные строки потенциала.
    """

    def __init__(
        self,
        title: str,
        hint: str,
        parent: QWidget,
        *,
        hint_inline: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._default_hint = "" if hint_inline else hint

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(3)

        title_label = QLabel(title, self)
        title_label.setObjectName("metricTitle")
        self._value = QLabel("—", self)
        self._value.setObjectName("metricValue")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._hint = QLabel(self._default_hint, self)
        self._hint.setObjectName("metricHint")
        self._hint.setWordWrap(True)

        layout.addWidget(title_label)
        if hint_inline:
            caption = QLabel(hint, self)
            caption.setObjectName("metricValueCaption")
            value_row = QHBoxLayout()
            value_row.setContentsMargins(0, 0, 0, 0)
            value_row.setSpacing(8)
            value_row.addWidget(self._value)
            value_row.addWidget(caption, 1, Qt.AlignmentFlag.AlignBottom)
            layout.addLayout(value_row)
        else:
            layout.addWidget(self._value)
        layout.addWidget(self._hint)
        layout.addStretch(1)

    def set_value(self, text: str, *, tone: str = "neutral") -> None:
        self._value.setText(text)
        if self._value.property("tone") == tone:
            return
        self._value.setProperty("tone", tone)
        self._repolish()

    def set_hint(self, text: str, *, rich: bool = False) -> None:
        """Показать подпись. `rich=True` — текст с HTML-разметкой (суммы)."""
        self._hint.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
        self._hint.setText(text)

    def reset(self) -> None:
        self.set_value("—")
        self.set_hint(self._default_hint)

    def _repolish(self) -> None:
        style = self._value.style()
        style.unpolish(self._value)
        style.polish(self._value)


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
        self._warnings = QPlainTextEdit(self)
        self._warnings.setObjectName("warningsView")
        self._warnings.setReadOnly(True)
        self._warnings.setMinimumHeight(110)

        self._build()
        self.reload()

    def apply_theme(self, theme: Theme) -> None:
        """Пересобрать локальные стили дашборда под выбранную тему."""
        self.setStyleSheet(dashboard_style(theme.palette))
        self.update()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget(self)
        content.setObjectName("dashboardContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(10)
        caption = QLabel("Загрузка", content)
        caption.setObjectName("toolbarLabel")
        header.addWidget(caption)
        header.addWidget(self._batch_combo, stretch=1)
        header.addWidget(self._refresh_button)
        layout.addLayout(header)

        layout.addWidget(self._batch_label)
        layout.addWidget(self._build_summary())
        layout.addWidget(self._build_main_section())
        layout.addWidget(self._build_additional_section())
        layout.addWidget(self._build_warnings_section())
        layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        scroll.viewport().setObjectName("dashboardViewport")
        outer.addWidget(scroll)

        self._batch_combo.currentIndexChanged.connect(self._batch_changed)
        self._refresh_button.clicked.connect(self.refresh)

    def _build_summary(self) -> QWidget:
        """Блок «Сводка»: карточки непересекающихся показателей."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Сводка", container)
        title.setObjectName("sectionTitle")
        title.setIndent(2)
        layout.addWidget(title)
        layout.addWidget(self._build_cards())
        return container

    def _build_cards(self) -> QWidget:
        container = QWidget(self)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        definitions = (
            ("messages", "Количество сообщений", "SMS-сегментов: —"),
            ("delivered", "Доставлено", "успешная доставка"),
            ("delivered_share", "Процент доставленных", "от количества сообщений"),
            ("templates", "Шаблонов", "активных —"),
            ("candidates", "Кандидатов", "по последнему анализу"),
            ("benefit", "Выгода шаблонов", "после вычета стоимости шаблонов"),
        )
        for index, (key, title, hint) in enumerate(definitions):
            row, column = divmod(index, 3)
            card = _MetricCard(title, hint, container, hint_inline=key == "benefit")
            grid.addWidget(card, row, column)
            self._cards[key] = card
        # Карточки «Процент доставленных» и «Выгода шаблонов» шире остальных на 30 %.
        for column, stretch in enumerate(CARD_STRETCH):
            grid.setColumnStretch(column, stretch)
        return container

    def _build_main_section(self) -> QWidget:
        """Блок «Основное»: таблицы и круговые диаграммы долей."""
        box = QFrame(self)
        box.setObjectName("sectionCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Основное", box)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self._segment_chart = PieChart("Доли SMS-сегментов", box)
        self._cost_chart = PieChart("Доли расходов", box)
        self._operator_segment_chart = PieChart("Сегменты по операторам", box)
        self._operator_cost_chart = PieChart("Счёт по операторам", box)

        content = QGridLayout()
        content.setHorizontalSpacing(16)
        content.setVerticalSpacing(12)
        content.addWidget(self._build_main_table(box), 0, 0)
        content.addWidget(self._segment_chart, 0, 1)
        content.addWidget(self._cost_chart, 0, 2)
        content.addWidget(self._build_operator_section(box), 1, 0)
        content.addWidget(self._operator_segment_chart, 1, 1)
        content.addWidget(self._operator_cost_chart, 1, 2)
        content.setColumnStretch(0, 6)
        content.setColumnStretch(1, 2)
        content.setColumnStretch(2, 2)
        layout.addLayout(content)

        hint = QLabel(
            "Доли и средняя стоимость считаются по SMS-сегментам, а не по сообщениям.",
            box,
        )
        hint.setObjectName("sectionHint")
        layout.addWidget(hint)
        return box

    def _build_main_table(self, parent: QWidget) -> QWidget:
        """Таблица сообщений и SMS-сегментов по классам."""
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        for column in range(len(MAIN_COLUMNS)):
            grid.setColumnStretch(column, 1)
        for column, text in enumerate(MAIN_COLUMNS):
            if not text:
                continue
            label = QLabel(text, container)
            label.setObjectName("mainHeader")
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            label.setAlignment(_column_alignment(column))
            grid.addWidget(label, 0, column)

        for row, (prefix, text, style_name) in enumerate(MAIN_ROWS, start=1):
            name = QLabel(text, container)
            name.setObjectName(style_name)
            grid.addWidget(name, row, 0)
            for column, suffix in enumerate(
                ("messages", "segments", "cost", "average", "share"), start=1
            ):
                cell = QLabel("—", container)
                cell.setObjectName(_cell_style(prefix, suffix))
                cell.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(cell, row, column)
                self._cells[f"{prefix}_{suffix}"] = cell

        layout.addLayout(grid)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        length_label = QLabel("Средняя длина сообщения", container)
        length_label.setObjectName("mainRowLabel")
        self._cells["average_segments"] = QLabel("—", container)
        self._cells["average_segments"].setObjectName("mainCell")
        footer.addWidget(length_label)
        footer.addWidget(self._cells["average_segments"])
        footer.addStretch(1)
        layout.addLayout(footer)
        return container

    def _build_additional_section(self) -> QWidget:
        """Блок «Дополнительно»: абоненты и распределения по числу SMS-сегментов."""
        box = QFrame(self)
        box.setObjectName("sectionCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Дополнительно", box)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_subscriber_cards(box))

        self._subscriber_segment_chart = DistributionChart(
            "Распределение уникальных абонентов по количеству отправленных им сегментов", box
        )
        self._subscriber_operator_chart = PieChart(
            "Распределение уникальных абонентов по мобильным операторам", box
        )
        self._message_segment_chart = DistributionChart(
            "Распределение сообщений по количеству сегментов, из которых они состоят",
            box,
            exact_gradient=DARK_MUSTARD_GRADIENT,
        )

        charts = QGridLayout()
        charts.setHorizontalSpacing(16)
        charts.setVerticalSpacing(12)
        charts.addWidget(self._subscriber_segment_chart, 0, 0)
        charts.addWidget(self._subscriber_operator_chart, 0, 1)
        charts.addWidget(self._message_segment_chart, 0, 2)
        for column in range(3):
            charts.setColumnStretch(column, 1)
        layout.addLayout(charts)

        hint = QLabel(
            "Абонент — уникальный номер получателя с отправленными сегментами; "
            "оператор абонента — тот, по которому у него больше сообщений. "
            "Сегменты 1–9 показаны отдельно, дальше — диапазоны. "
            "Сообщения с ошибкой отправки (0 сегментов) не входят.",
            box,
        )
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return box

    def _build_subscriber_cards(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        definitions = (
            ("subscribers", "Уникальных абонентов", "номеров получателей"),
            ("subscriber_segments", "Сегментов на абонента", "в среднем за период"),
            ("subscriber_messages", "Сообщений на абонента", "в среднем за период"),
        )
        for column, (key, title, hint) in enumerate(definitions):
            card = _MetricCard(title, hint, container)
            grid.addWidget(card, 0, column)
            self._cards[key] = card
        return container

    def _build_operator_section(self, parent: QWidget) -> QWidget:
        """Таблица по операторам получателя под основной таблицей."""
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        title = QLabel("По операторам получателя", container)
        title.setObjectName("operatorTitle")
        layout.addWidget(title)

        self._operator_rows = QGridLayout()
        self._operator_rows.setHorizontalSpacing(12)
        self._operator_rows.setVerticalSpacing(6)
        for column in range(len(OPERATOR_COLUMNS)):
            self._operator_rows.setColumnStretch(column, 1)
        for column, text in enumerate(OPERATOR_COLUMNS):
            label = QLabel(text, container)
            label.setObjectName("operatorHeader")
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            label.setAlignment(_column_alignment(column))
            self._operator_rows.addWidget(label, 0, column)
        layout.addLayout(self._operator_rows)

        hint = QLabel(
            "Сортировка — по убыванию количества сообщений; доля — от всех сообщений загрузки.",
            container,
        )
        hint.setObjectName("sectionHint")
        layout.addWidget(hint)
        return container

    def _build_warnings_section(self) -> QWidget:
        box = QFrame(self)
        box.setObjectName("sectionCard")
        box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(8)

        title = QLabel("Предупреждения и допущения", box)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(self._warnings, stretch=1)
        return box

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
        if summary.batch is None or summary.statistics is None:
            self._fill_empty(summary)
            return

        statistics = summary.statistics
        batch = summary.batch
        self._batch_label.setText(_subtitle(batch))
        self._fill_cards(summary)
        self._fill_main(statistics)
        self._fill_operators(summary.operators)
        self._fill_additional(summary.segmentation)

        lines = list(summary.warnings)
        if not lines:
            lines.append("Предупреждений нет.")
        self._warnings.setPlainText("\n".join(f"• {line}" for line in lines))

    def _fill_cards(self, summary: DashboardSummary) -> None:
        statistics = summary.statistics
        if statistics is None:
            return

        self._cards["messages"].set_value(format_int(statistics.message_count))
        self._cards["messages"].set_hint(f"SMS-сегментов: {format_int(statistics.segments)}")
        self._cards["delivered"].set_value(format_int(statistics.delivered))
        self._cards["delivered_share"].set_value(format_percent(statistics.delivered_share))
        self._cards["templates"].set_value(format_int(summary.template_count))
        self._cards["templates"].set_hint(f"активных {format_int(summary.active_templates)}")
        self._cards["candidates"].set_value(format_int(summary.candidates))
        self._cards["candidates"].set_hint(
            _candidates_hint(summary), rich=summary.profitable_candidates_benefit is not None
        )

        benefit = summary.total_net_benefit
        if benefit is None:
            self._cards["benefit"].set_value("—")
            self._cards["benefit"].set_hint("анализ не выполнялся")
            return
        tone = "neutral"
        if benefit.amount > 0:
            tone = "positive"
        elif benefit.amount < 0:
            tone = "negative"
        self._cards["benefit"].set_value(format_money(benefit), tone=tone)
        self._cards["benefit"].set_hint(_benefit_hint_html(summary), rich=True)
        self._cards["benefit"].setToolTip(_benefit_tooltip(summary))

    def _fill_main(self, statistics: BatchStatistics) -> None:
        self._set_cell("total_messages", format_int(statistics.message_count))
        self._set_cell("total_segments", format_int(statistics.segments))
        self._set_cell("total_cost", format_money(statistics.cost))
        self._set_cell("total_average", format_money(statistics.average_segment_cost))
        self._set_cell("total_share", format_percent(1.0) if statistics.segments else "—")

        self._set_cell("ordinary_messages", format_int(statistics.ordinary_messages))
        self._set_cell("ordinary_segments", format_int(statistics.ordinary_segments))
        self._set_cell("ordinary_cost", format_money(statistics.ordinary_cost))
        self._set_cell("ordinary_average", format_money(statistics.ordinary_average_segment_cost))
        self._set_cell("ordinary_share", format_percent(statistics.ordinary_segment_share))

        self._set_cell("templated_messages", format_int(statistics.templated_messages))
        self._set_cell("templated_segments", format_int(statistics.templated_segments))
        self._set_cell("templated_cost", format_money(statistics.templated_cost))
        self._set_cell("templated_average", format_money(statistics.templated_average_segment_cost))
        self._set_cell("templated_share", format_percent(statistics.templated_segment_share))

        self._set_cell("average_segments", format_average_segments(statistics.average_segments))

        palette = active_palette()
        self._segment_chart.set_slices(
            (
                PieSlice("Обычные", float(statistics.ordinary_segments), palette.negative),
                PieSlice(
                    "Шаблонированные",
                    float(statistics.templated_segments),
                    TEMPLATED_CHART_COLOR,
                ),
            )
        )
        self._cost_chart.set_slices(
            (
                PieSlice("Обычные", float(statistics.ordinary_cost.amount), palette.negative),
                PieSlice(
                    "Шаблонированные",
                    float(statistics.templated_cost.amount),
                    TEMPLATED_CHART_COLOR,
                ),
            )
        )

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
        self._subscriber_operator_chart.set_slices(
            _subscriber_operator_slices(segmentation.subscribers_by_operator)
        )

    def _fill_additional_empty(self) -> None:
        for key in ("subscribers", "subscriber_segments", "subscriber_messages"):
            self._cards[key].reset()
        self._subscriber_segment_chart.set_bars(())
        self._message_segment_chart.set_bars(())
        self._subscriber_operator_chart.set_slices(())

    def _fill_empty(self, summary: DashboardSummary | None = None) -> None:
        for card in self._cards.values():
            card.reset()
        for cell in self._cells.values():
            cell.setText("—")
        for chart in (
            self._segment_chart,
            self._cost_chart,
            self._operator_segment_chart,
            self._operator_cost_chart,
        ):
            chart.set_slices(())
        self._fill_additional_empty()
        self._fill_operators(())
        self._batch_label.setText("Статистика ещё не импортирована.")
        warnings = summary.warnings if summary is not None else ()
        self._warnings.setPlainText("\n".join(f"• {line}" for line in warnings))

    def _fill_operators(self, operators: Sequence[OperatorStatistics]) -> None:
        """Заполнить таблицу операторов: сортировка уже сделана в SQL."""
        self._clear_operator_rows()
        parent = self._operator_rows.parentWidget()
        total_messages = sum(item.messages for item in operators)
        self._operator_segment_chart.set_slices(
            _operator_slices(operators, lambda item: float(item.segments))
        )
        self._operator_cost_chart.set_slices(
            _operator_slices(operators, lambda item: float(item.cost.amount))
        )
        if not operators:
            empty = QLabel("Нет данных", parent)
            empty.setObjectName("operatorCell")
            self._operator_rows.addWidget(empty, 1, 0)
            return

        for row, item in enumerate(operators, start=1):
            share = item.messages / total_messages if total_messages else 0.0
            values = (
                item.operator,
                format_int(item.messages),
                format_int(item.segments),
                format_money(item.cost),
                format_money(item.average_segment_cost),
                format_percent(share),
            )
            for column, value in enumerate(values):
                cell = QLabel(value, parent)
                cell.setObjectName("operatorCell")
                cell.setAlignment(_column_alignment(column))
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self._operator_rows.addWidget(cell, row, column)

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


def _operator_slices(
    operators: Sequence[OperatorStatistics],
    value: Callable[[OperatorStatistics], float],
) -> tuple[PieSlice, ...]:
    """Сектора долей операторов: топ по значению, остальные — «Другие»."""
    return _slices_from_entries((item.operator, value(item)) for item in operators)


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


def _cell_style(prefix: str, suffix: str) -> str:
    if suffix != "share":
        return "mainCell"
    if prefix == "ordinary":
        return "mainCellShareOrdinary"
    if prefix == "templated":
        return "mainCellShareTemplated"
    return "mainCell"


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
