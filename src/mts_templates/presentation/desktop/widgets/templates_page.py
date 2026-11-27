"""Экран «Шаблоны»: активность и экономическая выгода зарегистрированных шаблонов."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    AnalysisView,
    AnalyzeRequest,
    MatchedMessageView,
    OperatorTriggerView,
    TemplateMetricsView,
)
from mts_templates.application.settings import AppSettings, BenefitThresholds
from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates
from mts_templates.application.use_cases.dashboard import (
    ListBatches,
    negative_benefit,
    positive_benefit,
)
from mts_templates.application.use_cases.get_template_trend import GetTemplateTrend
from mts_templates.application.use_cases.list_matched_messages import ListMatchedMessages
from mts_templates.domain.analytics.trend import Deterioration, TemplateTrend, detect_deterioration
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.benefit_style import (
    RowPalette,
    benefit_color,
    row_palette,
    semantic_text,
)
from mts_templates.presentation.desktop.dialogs.matched_messages_dialog import (
    MatchedMessagesDialog,
)
from mts_templates.presentation.desktop.formatting import (
    format_batch_title,
    format_int,
    format_money,
    format_operators,
    format_percent,
    format_period,
)
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import (
    build_table,
    fit_columns,
    sort_by_title,
)
from mts_templates.presentation.desktop.table_filters import operator_rows_for_template
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.benefit_totals import BenefitTotal
from mts_templates.presentation.desktop.widgets.busy_overlay import BusyOverlay
from mts_templates.presentation.desktop.widgets.segment_dashboard import (
    DashboardDrift,
    DashboardDriftFragment,
    DashboardSeries,
    DashboardTile,
    SegmentDashboard,
)
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

OPERATOR_TITLE = "Срабатывание по операторам получателя"
SUMMARY_MIN_WIDTH = 160
DASHBOARD_STRETCH = 3
SUMMARY_STRETCH = 2
TABLE_STRETCH = 4
LOWER_STRETCH = 3
SPLIT_WEIGHT_SCALE = 1000
MESSAGES_HINT = "Нажмите, чтобы показать сообщения, подпавшие под шаблон"
NARROW_COLUMNS = frozenset({"Сообщений", "Достав.", "Срабат.", "% Срабат."})
TEMPLATE_DASHBOARD_TILES = (
    "% от всех сегментов",
    "% от шаблонированных",
    "Выгода/мес",
    "Срабатывание",
)


def _theme_row_palette() -> RowPalette:
    """Фоны подсветки строк под активную тему."""
    palette = active_palette()
    return row_palette(palette.surface, palette.positive, palette.negative)


COLUMNS = (
    Column(
        "Шаблон",
        lambda item: item.text,
        width=300,
        tooltip=lambda item: f"{item.text}\n\n{MESSAGES_HINT}",
    ),
    Column(
        "Операторы",
        lambda item: format_operators(item.operators),
        width=130,
        tooltip=lambda item: format_operators(item.operators),
    ),
    Column("Активен", lambda item: item.active, width=65),
    Column(
        "Дрейф",
        lambda item: item.drift is not None,
        width=70,
        tooltip=lambda item: (
            f"Кандидат: {item.drift.candidate_id} · похожесть {item.drift.similarity:.0%}"
            if item.drift is not None
            else "Дрейф не обнаружен: текст сообщений не изменялся"
        ),
    ),
    Column(
        "Сообщений",
        lambda item: item.matched_messages,
        formatter=format_int,
        width=50,
        tooltip=lambda item: (
            f"за период: {format_int(item.matched_messages)} · "
            f"в месяц: {format_int(item.monthly_messages)}"
        ),
    ),
    Column(
        "Сегментов",
        lambda item: item.matched_segments,
        formatter=format_int,
        width=80,
        tooltip=lambda item: (
            f"за период: {format_int(item.matched_segments)} · "
            f"в месяц: {format_int(item.monthly_segments)}"
        ),
    ),
    Column(
        "% от всех",
        lambda item: item.share_of_all_segments,
        formatter=format_percent,
        width=80,
        tooltip=lambda item: (
            "Доля сегментов сообщений, подпавших под шаблон, во всех сегментах сообщений за период"
        ),
    ),
    Column(
        "% от шабл.",
        lambda item: item.share_of_templated_segments,
        formatter=format_percent,
        width=85,
        tooltip=lambda item: (
            "Доля сегментов сообщений, подпавших под шаблон, "
            "в сегментах шаблонированных сообщений за период"
        ),
    ),
    Column("Достав.", lambda item: item.delivered_messages, formatter=format_int, width=57),
    Column("Получателей", lambda item: item.unique_recipients, formatter=format_int, width=85),
    Column("Срабат.", lambda item: item.triggered_messages, formatter=format_int, width=67),
    Column("% Срабат.", lambda item: item.trigger_rate, formatter=format_percent, width=60),
    Column("Вне списка", lambda item: item.off_operator_messages, formatter=format_int, width=80),
    Column(
        "Стоимость/мес",
        lambda item: item.monthly_actual_cost,
        width=100,
        tooltip=lambda item: f"за период: {format_money(item.actual_cost)}",
    ),
    Column(
        "Без шаблона/мес",
        lambda item: item.monthly_baseline_cost,
        width=115,
        tooltip=lambda item: f"за период: {format_money(item.baseline_cost)}",
    ),
    Column("Шаблон/мес", lambda item: item.template_fee, width=90),
    Column(
        "Выгода/мес",
        lambda item: item.monthly_net_benefit,
        width=100,
        tooltip=lambda item: f"за период: {format_money(item.net_benefit)}",
    ),
    Column("Отправитель", lambda item: item.sender, width=100),
)

OPERATOR_COLUMNS = (
    Column("Оператор", lambda item: item.operator, width=120),
    Column("В списке", lambda item: item.listed, width=70),
    Column("Сообщений", lambda item: item.matched_messages, formatter=format_int, width=75),
    Column("Сегментов", lambda item: item.matched_segments, formatter=format_int, width=80),
    Column("Доля (%)", lambda item: item.share, formatter=format_percent, width=70),
    Column("Срабатываний", lambda item: item.triggered_messages, formatter=format_int, width=100),
    Column("Срабатывание", lambda item: item.trigger_rate, formatter=format_percent, width=90),
)


class TemplatesPage(QWidget):
    """Показывает метрики шаблонов и запускает анализ по выбранной загрузке."""

    analysis_completed = Signal()

    def __init__(
        self,
        *,
        analyze_templates: AnalyzeTemplates,
        matched_messages: ListMatchedMessages,
        list_batches: ListBatches,
        template_trend: GetTemplateTrend,
        settings_provider: Callable[[], AppSettings],
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._analyze_templates = analyze_templates
        self._matched_messages = matched_messages
        self._list_batches = list_batches
        self._template_trend = template_trend
        self._settings_provider = settings_provider
        self._thresholds: BenefitThresholds = settings_provider().benefit_thresholds
        self._runner = runner
        self._batch_id: str | None = None
        self._messages_dialog: MatchedMessagesDialog | None = None
        self._operator_triggers: tuple[OperatorTriggerView, ...] = ()
        self._row_palette = _theme_row_palette()
        self._trend: TemplateTrend | None = None
        self._deterioration: Deterioration | None = None
        self._trend_view = QPlainTextEdit(self)
        self._trend_view.setReadOnly(True)

        self._batch_combo = QComboBox(self)
        self._analyze_button = QPushButton("Выполнить анализ", self)
        self._recalc_button = QPushButton("Пересчитать", self)
        self._filter = QLineEdit(self)
        self._summary = QLabel("Анализ ещё не выполнялся.", self)
        self._warnings = QPlainTextEdit(self)
        self._warnings.setObjectName("warningsView")
        self._warnings.setReadOnly(True)
        self._warnings.setMaximumHeight(180)
        self._model = RowsTableModel(COLUMNS, self, row_color=self._row_color)
        self._table, self._proxy = build_table(self._model, self, stretch_column=0)
        sort_by_title(self._table, "Выгода/мес", Qt.SortOrder.DescendingOrder)
        self._operator_model = RowsTableModel(
            OPERATOR_COLUMNS, self, row_color=self._operator_row_color
        )
        self._operator_table, _ = build_table(
            self._operator_model,
            self,
            stretch_column=None,
            secondary_sort=("Доля (%)", Qt.SortOrder.DescendingOrder),
        )
        sort_by_title(self._operator_table, "В списке", Qt.SortOrder.DescendingOrder)
        self._profit_total = BenefitTotal("Выгода выгодных шаблонов, ₽/мес", self, inline=True)
        self._loss_total = BenefitTotal("Убыток убыточных шаблонов, ₽/мес", self, inline=True)
        self._all_total = BenefitTotal("Выгода всех шаблонов, ₽/мес", self, inline=True)
        self._operator_title = QLabel(OPERATOR_TITLE, self)
        self._operator_title.setWordWrap(True)
        self._dashboard = SegmentDashboard(
            TEMPLATE_DASHBOARD_TILES,
            empty_title="Шаблон не выбран",
            parent=self,
        )
        self._busy = BusyOverlay(self._table)

        self._build()
        self.reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Загрузка:", self))
        top.addWidget(self._batch_combo, stretch=1)
        top.addWidget(self._analyze_button)
        top.addWidget(self._recalc_button)
        layout.addLayout(top)

        self._filter.setPlaceholderText("Фильтр по названию, отправителю или тексту шаблона")
        layout.addWidget(self._filter)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._table)
        splitter.addWidget(self._build_operator_section())
        splitter.setStretchFactor(0, TABLE_STRETCH)
        splitter.setStretchFactor(1, LOWER_STRETCH)
        # setSizes принимает пиксели и обрезает их по минимальным размерам виджетов,
        # поэтому веса умножаются: Qt нормирует большие значения на доступную высоту.
        splitter.setSizes([TABLE_STRETCH * SPLIT_WEIGHT_SCALE, LOWER_STRETCH * SPLIT_WEIGHT_SCALE])
        layout.addWidget(splitter, stretch=1)

        self._analyze_button.clicked.connect(lambda: self._analyze(force=False))
        self._recalc_button.clicked.connect(lambda: self._analyze(force=True))
        self._filter.textChanged.connect(self._apply_filter)
        self._batch_combo.currentIndexChanged.connect(self._batch_changed)
        self._table.selectionModel().currentRowChanged.connect(self._selection_changed)
        self._table.clicked.connect(self._cell_clicked)
        self._show_operator_rows(None)

    def _build_operator_section(self) -> QWidget:
        """Таблица операторов, мини-дашборд шаблона и общая сводка по всем шаблонам."""
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        left = QWidget(container)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(self._operator_title)
        left_layout.addWidget(self._operator_table, stretch=1)

        right = QWidget(container)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)
        right_layout.addWidget(self._dashboard, stretch=DASHBOARD_STRETCH)
        right_layout.addWidget(self._build_general_summary(right), stretch=SUMMARY_STRETCH)

        row.addWidget(left, stretch=0)
        row.addWidget(right, stretch=1)
        return container

    def _build_general_summary(self, parent: QWidget) -> QWidget:
        """Суммы выгоды и убытка по всем шаблонам, текстовая сводка и предупреждения."""
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        totals = QVBoxLayout()
        totals.setContentsMargins(0, 0, 0, 0)
        totals.setSpacing(8)
        for total in (self._profit_total, self._loss_total, self._all_total):
            totals.addWidget(total)
        layout.addLayout(totals)

        layout.addWidget(self._trend_view)
        self._summary.setWordWrap(True)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._summary.setMinimumWidth(SUMMARY_MIN_WIDTH)
        layout.addWidget(self._summary)
        layout.addWidget(self._warnings, stretch=1)
        return panel

    def _selected_template_id(self) -> str | None:
        """Выделенный в таблице шаблон, иначе первый в отфильтрованном наборе."""
        current = self._table.currentIndex()
        if current.isValid():
            source = self._proxy.mapToSource(current)
            if source.isValid():
                return str(self._model.row_at(source.row()).template_id)
        rows = self._model.rows()
        return rows[0].template_id if rows else None

    def _update_trend(self) -> None:
        """История шаблона по загрузкам и алерт о деградации срабатываний."""
        trend: TemplateTrend | None = None
        deterioration: Deterioration | None = None
        template_id = self._selected_template_id()
        if template_id is not None:
            try:
                trend = self._template_trend.execute(template_id)
                deterioration = detect_deterioration(trend)
            except Exception:
                trend = None
        self._trend = trend
        self._deterioration = deterioration
        if trend is None or not trend.points:
            self._trend_view.setPlainText("История шаблонов по загрузкам пока не построена.")
            return
        lines = [f"История по загрузкам ({len(trend.points)}):"]
        for point in trend.points:
            lines.append(
                f"{format_period(point.period.start, point.period.end)}: "
                f"сегментов {format_int(point.segments)}, "
                f"срабатываний {format_int(point.triggered_messages)}, "
                f"выгода {format_money(point.net_benefit)}/мес"
            )
        if deterioration is not None:
            lines.append(
                "АЛЕРТ: шаблон перестал срабатывать — в предыдущей загрузке было "
                f"{deterioration.previous_triggered_messages} срабатываний, сейчас "
                f"{deterioration.current_triggered_messages}."
            )
        self._trend_view.setPlainText("\n".join(lines))

    def _fit_operator_width(self) -> None:
        """Отдать таблице операторов её колонки, оставив остальное отчёту справа."""
        table = self._operator_table
        header = table.horizontalHeader()
        width = sum(table.columnWidth(index) for index in range(header.count()))
        width += table.frameWidth() * 2 + table.verticalScrollBar().sizeHint().width()
        table.setFixedWidth(width)
        self._operator_title.setMaximumWidth(width)

    def reload(self) -> None:
        """Перечитать список загрузок, сохранив выбранную."""
        try:
            batches = self._list_batches.execute()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return

        current = self._batch_combo.currentData()
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        for batch in batches:
            self._batch_combo.addItem(format_batch_title(batch), batch.id)
        if current is not None:
            index = self._batch_combo.findData(current)
            if index >= 0:
                self._batch_combo.setCurrentIndex(index)
        self._batch_combo.blockSignals(False)

        has_batches = bool(batches)
        self._analyze_button.setEnabled(has_batches)
        self._recalc_button.setEnabled(has_batches)
        if not has_batches:
            self._summary.setText("Статистика ещё не импортирована.")
            self._warnings.setPlainText("")
            self._model.set_rows(())
            self._operator_triggers = ()
            self._dashboard.clear()
            self._show_operator_rows(None)
            self._reset_totals()

    def reload_settings(self) -> None:
        """Применить новые пороги выгоды и перерисовать строки таблицы."""
        try:
            self._thresholds = self._settings_provider().benefit_thresholds
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать настройки: {exc}")
            return
        self._model.refresh()

    def refresh_theme(self) -> None:
        """Пересчитать цвета строк и итогов под активную тему."""
        self._row_palette = _theme_row_palette()
        self._busy.refresh_theme()
        self._model.refresh()
        self._operator_model.refresh()
        self._dashboard.refresh_theme()
        rows = self._model.rows()
        if rows:
            self._fill_totals(rows)
        else:
            self._reset_totals()

    def _batch_changed(self, _index: int) -> None:
        self._model.set_rows(())
        self._batch_id = None
        self._operator_triggers = ()
        self._dashboard.clear()
        self._show_operator_rows(None)
        self._summary.setText("Нажмите «Выполнить анализ», чтобы посчитать метрики.")
        self._reset_totals()

    def _analyze(self, *, force: bool) -> None:
        batch_id = self._batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "Нет данных", "Сначала импортируйте статистику.")
            return
        self._set_busy(True, "Пересчёт анализа…" if force else "Выполняется анализ…")
        self._runner.run(
            lambda token: self._analyze_templates.execute(
                AnalyzeRequest(batch_id=str(batch_id), force=force),
                should_cancel=lambda: token.cancelled,
            ),
            on_success=self._show,
            on_error=self._failed,
        )

    def _show(self, view: AnalysisView) -> None:
        self._set_busy(False)
        self._batch_id = view.batch_id
        self._operator_triggers = view.operator_triggers
        self._model.set_rows(view.metrics)
        self._apply_filter(self._filter.text())
        fit_columns(
            self._table,
            max_widths={
                0: 300,
                **{
                    index: column.width
                    for index, column in enumerate(COLUMNS)
                    if column.title in NARROW_COLUMNS
                },
            },
        )
        summary = (
            f"Период {format_period(view.period_from, view.period_to)} · "
            f"подпало под шаблоны {format_int(view.matched_message_count)} из "
            f"{format_int(view.message_count)} сообщений · "
            f"срабатывание {format_percent(view.trigger_rate)} · "
            f"выгода шаблонов/мес {format_money(view.total_monthly_net_benefit)} · "
            f"неактивных {format_int(view.inactive_templates)}"
        )
        if view.is_partial_period:
            summary += " · неполный период: денежные суммы и объёмы смоделированы на 30 дней"
        self._summary.setText(summary)
        self._fill_totals(view.metrics)
        self._dashboard.set_context(
            view.daily_total_segments,
            view.daily_templated_segments,
            (view.period_from.date(), view.period_to.date()),
        )
        lines = list(view.warnings)
        if not lines:
            lines.append("Предупреждений нет.")
        self._warnings.setPlainText("\n".join(f"• {line}" for line in lines))
        self._update_trend()
        self._select_first_row()
        self.analysis_completed.emit()

    def _fill_totals(self, metrics: tuple[TemplateMetricsView, ...]) -> None:
        """Суммы по выгодным, убыточным и всем шаблонам за месяц."""
        palette = active_palette()
        profit_color = semantic_text(palette.positive, palette.window)
        loss_color = semantic_text(palette.negative, palette.window)
        self._profit_total.set_value(
            format_money(positive_benefit(item.monthly_net_benefit for item in metrics)),
            profit_color,
        )
        loss = negative_benefit(item.monthly_net_benefit for item in metrics)
        self._loss_total.set_value(
            format_money(loss) if loss.amount < 0 else format_money(Money.zero()),
            loss_color,
        )
        total = sum((item.monthly_net_benefit for item in metrics), Money.zero())
        total_color = profit_color if total.amount >= 0 else loss_color
        self._all_total.set_value(format_money(total), total_color)

    def _reset_totals(self) -> None:
        for total in (self._profit_total, self._loss_total, self._all_total):
            total.reset()

    def _select_first_row(self) -> None:
        """Выделить первый шаблон, чтобы разбивка по операторам была не пустой."""
        if self._proxy.rowCount() > 0:
            self._table.selectRow(0)
            return
        self._show_operator_rows(None)

    def _cell_clicked(self, index: QModelIndex) -> None:
        """Щелчок по тексту шаблона открывает список подпавших сообщений."""
        if index.column() != 0:
            return
        self._show_template_messages(index)

    def _show_template_messages(self, index: QModelIndex) -> None:
        """Кнопка справа от текста шаблона открывает список подпавших сообщений."""
        source = self._proxy.mapToSource(index)
        if not source.isValid() or not self._batch_id:
            return
        metric = self._model.row_at(source.row())
        batch_id = self._batch_id
        self._set_busy(True, "Загрузка сообщений…")
        self._runner.run(
            lambda token: self._matched_messages.for_template(
                batch_id,
                metric.template_id,
                should_cancel=lambda: token.cancelled,
            ),
            on_success=lambda rows: self._open_messages_dialog(rows, metric),
            on_error=self._messages_failed,
        )

    def _open_messages_dialog(
        self, rows: tuple[MatchedMessageView, ...], metric: TemplateMetricsView
    ) -> None:
        self._set_busy(False)
        if self._messages_dialog is None:
            self._messages_dialog = MatchedMessagesDialog(self)
        self._messages_dialog.set_rows(
            rows,
            title=f"Сообщения шаблона · ID {metric.template_id}",
            template_text=metric.text,
        )
        self._messages_dialog.show()
        self._messages_dialog.raise_()

    def _messages_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Ошибка загрузки сообщений", message)

    def _selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        index = self._proxy.mapToSource(current)
        if not index.isValid():
            self._show_operator_rows(None)
            return
        self._show_operator_rows(self._model.row_at(index.row()).template_id)

    def _show_operator_rows(self, template_id: str | None) -> None:
        """Показать операторов и мини-дашборд только для выделенного шаблона."""
        metric = (
            next(
                (item for item in self._model.rows() if item.template_id == template_id),
                None,
            )
            if template_id is not None
            else None
        )
        self._operator_model.set_rows(
            operator_rows_for_template(template_id, self._operator_triggers)
        )
        fit_columns(self._operator_table)
        self._fit_operator_width()
        self._dashboard.show_series(_template_series(metric))
        if metric is None:
            self._operator_title.setText(OPERATOR_TITLE)
            return
        self._operator_title.setText(
            f"{OPERATOR_TITLE} — {metric.name} ({format_operators(metric.operators)})"
        )

    def _apply_filter(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)
        if not self._table.currentIndex().isValid():
            self._show_operator_rows(None)

    def _row_color(self, item: TemplateMetricsView) -> QColor | None:
        color = benefit_color(item.monthly_net_benefit, self._thresholds, self._row_palette)
        return QColor(color) if color is not None else None

    def _operator_row_color(self, item: OperatorTriggerView) -> QColor:
        """Умеренно-зелёный для оператора из списка шаблона, красный — вне списка."""
        palette = self._row_palette
        return QColor(palette.listed_color if item.listed else palette.loss_color)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._analyze_button.setEnabled(not busy)
        self._recalc_button.setEnabled(not busy)
        self._batch_combo.setEnabled(not busy)
        if busy:
            self._busy.start(text)
        else:
            self._busy.stop()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        if message == CANCELLED_MESSAGE:
            self._summary.setText("Анализ отменён.")
            return
        QMessageBox.critical(self, "Ошибка анализа", message)


def _template_series(metric: TemplateMetricsView | None) -> DashboardSeries | None:
    """Представление выбранного шаблона для общего мини-дашборда."""
    if metric is None:
        return None
    benefit = metric.monthly_net_benefit
    tone = "positive" if benefit.amount > 0 else "negative" if benefit.amount < 0 else "neutral"
    return DashboardSeries(
        title=f"{metric.name} · ID {metric.template_id}",
        tooltip=metric.text,
        matched=metric.daily_segments,
        tiles=(
            DashboardTile(format_percent(metric.share_of_all_segments)),
            DashboardTile(format_percent(metric.share_of_templated_segments)),
            DashboardTile(format_money(benefit), tone),
            DashboardTile(format_percent(metric.trigger_rate)),
        ),
        drift=_dashboard_drift(metric),
    )


def _dashboard_drift(metric: TemplateMetricsView) -> DashboardDrift | None:
    """Дрейф шаблона для пометки в мини-дашборде."""
    drift = metric.drift
    if drift is None:
        return None
    return DashboardDrift(
        similarity=drift.similarity,
        candidate_text=drift.candidate_text,
        before=tuple(
            DashboardDriftFragment(kind=fragment.kind, text=fragment.text)
            for fragment in drift.template_fragments
        ),
        after=tuple(
            DashboardDriftFragment(kind=fragment.kind, text=fragment.text)
            for fragment in drift.candidate_fragments
        ),
    )
