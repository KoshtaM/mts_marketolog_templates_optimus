"""Экран «Шаблоны»: активность и экономическая выгода зарегистрированных шаблонов."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

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
    ImportBatch,
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
from mts_templates.domain.value_objects import Money
from mts_templates.presentation.desktop.benefit_style import (
    RowPalette,
    benefit_color,
    row_palette,
    semantic_text,
)
from mts_templates.presentation.desktop.dialogs.template_text_dialog import TemplateTextDialog
from mts_templates.presentation.desktop.formatting import (
    format_int,
    format_money,
    format_operators,
    format_percent,
    format_period,
)
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import build_table, fit_columns
from mts_templates.presentation.desktop.table_filters import operator_rows_for_template
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.benefit_totals import BenefitTotal
from mts_templates.presentation.desktop.widgets.busy_overlay import BusyOverlay
from mts_templates.presentation.desktop.widgets.segment_dashboard import (
    DashboardSeries,
    DashboardTile,
    SegmentDashboard,
)
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

OPERATOR_TITLE = "Срабатывание по операторам получателя"
SUMMARY_MIN_WIDTH = 160
DASHBOARD_STRETCH = 3
SUMMARY_STRETCH = 2
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
        tooltip=lambda item: item.text,
    ),
    Column(
        "Операторы",
        lambda item: format_operators(item.operators),
        width=130,
        tooltip=lambda item: format_operators(item.operators),
    ),
    Column("Отправитель", lambda item: item.sender, width=100),
    Column("Активен", lambda item: item.active, width=65),
    Column(
        "Сообщений",
        lambda item: item.matched_messages,
        formatter=format_int,
        width=75,
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
    Column("Доставлено", lambda item: item.delivered_messages, formatter=format_int, width=85),
    Column("Получателей", lambda item: item.unique_recipients, formatter=format_int, width=85),
    Column("Срабатываний", lambda item: item.triggered_messages, formatter=format_int, width=100),
    Column("Срабатывание", lambda item: item.trigger_rate, formatter=format_percent, width=90),
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
        list_batches: ListBatches,
        settings_provider: Callable[[], AppSettings],
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._analyze_templates = analyze_templates
        self._list_batches = list_batches
        self._settings_provider = settings_provider
        self._thresholds: BenefitThresholds = settings_provider().benefit_thresholds
        self._runner = runner
        self._operator_triggers: tuple[OperatorTriggerView, ...] = ()
        self._row_palette = _theme_row_palette()

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
        self._operator_model = RowsTableModel(
            OPERATOR_COLUMNS, self, row_color=self._operator_row_color
        )
        self._operator_table, _ = build_table(self._operator_model, self, stretch_column=None)
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
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
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

        self._summary.setWordWrap(True)
        self._summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._summary.setMinimumWidth(SUMMARY_MIN_WIDTH)
        layout.addWidget(self._summary)
        layout.addWidget(self._warnings, stretch=1)
        return panel

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
            self._batch_combo.addItem(_batch_title(batch), batch.id)
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
        self._operator_triggers = view.operator_triggers
        self._model.set_rows(view.metrics)
        self._apply_filter(self._filter.text())
        fit_columns(self._table, max_widths={0: 300})
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
        """Щелчок по тексту шаблона показывает его целиком с копированием."""
        if index.column() != 0:
            return
        source = self._proxy.mapToSource(index)
        if not source.isValid():
            return
        metric = self._model.row_at(source.row())
        TemplateTextDialog(
            metric.text,
            title=f"Текст шаблона · {metric.template_id}",
            parent=self,
        ).exec()

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
    )


def _batch_title(batch: ImportBatch) -> str:
    return (
        f"{Path(batch.source_path).name} · "
        f"{format_period(batch.period_from, batch.period_to)} · "
        f"{format_int(batch.message_count)} сообщ."
    )
