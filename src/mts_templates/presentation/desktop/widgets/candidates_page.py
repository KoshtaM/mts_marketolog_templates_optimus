"""Экран «Кандидаты»: группы незашаблонированных сообщений и прогноз выгоды."""

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
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    AnalysisView,
    CandidateView,
    MatchedMessageView,
)
from mts_templates.application.settings import AppSettings, BenefitThresholds
from mts_templates.application.use_cases.dashboard import ListBatches, positive_benefit
from mts_templates.application.use_cases.find_candidates import FindCandidates
from mts_templates.application.use_cases.list_matched_messages import ListMatchedMessages
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
    format_percent,
    format_period,
)
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import (
    MIN_STRETCH_WIDTH,
    build_table,
    fit_columns,
    sort_by_title,
)
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.benefit_totals import (
    BenefitTotal,
    neutral_color,
)
from mts_templates.presentation.desktop.widgets.busy_overlay import BusyOverlay
from mts_templates.presentation.desktop.widgets.segment_dashboard import (
    DashboardSeries,
    DashboardTile,
    SegmentDashboard,
)
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

STATUS_TITLES = {
    "auto_validated": "Проверен автоматически",
    "needs_human_approval": "Требует подтверждения",
    "warning_saved": "Сохранён с предупреждением",
    "rejected": "Отклонён",
}


def _status_title(status: str) -> str:
    return STATUS_TITLES.get(status, status)


# Текст шаблона-кандидата должен занимать вдвое больше места, чем по умолчанию.
CANDIDATE_TEXT_WIDTH = 600
CANDIDATE_STRETCH_WIDTH = MIN_STRETCH_WIDTH * 2
MESSAGES_HINT = "Нажмите, чтобы показать сообщения, из которых собран кандидат"


COLUMNS = (
    Column(
        "Шаблон-кандидат",
        lambda item: item.template_text,
        width=CANDIDATE_TEXT_WIDTH,
        tooltip=lambda item: f"{item.template_text}\n\n{MESSAGES_HINT}",
    ),
    Column("Статус", lambda item: item.status, formatter=_status_title, width=150),
    Column("Сообщений", lambda item: item.messages, formatter=format_int, width=80),
    Column("Сегментов", lambda item: item.segments, formatter=format_int, width=80),
    Column("Стоимость", lambda item: item.actual_cost, width=90),
    Column("Если шаблон", lambda item: item.templated_cost, width=95),
    Column("Стоимость/мес", lambda item: item.monthly_actual_cost, width=100),
    Column("Если шаблон/мес", lambda item: item.monthly_templated_cost, width=105),
    Column("Экономия/мес", lambda item: item.monthly_saving, width=100),
    Column("Шаблон/мес", lambda item: item.template_fee, width=90),
    Column("Выгода/мес", lambda item: item.net_monthly, width=100),
    Column("Уверенность", lambda item: item.confidence, formatter=format_percent, width=90),
    Column("Покрытие", lambda item: item.coverage, formatter=format_percent, width=75),
    Column("Отправители", lambda item: ", ".join(item.senders), width=110),
    Column("Предупреждения", lambda item: ", ".join(item.warnings), width=200),
    Column("Неполный период", lambda item: item.is_partial_period, width=95),
)

WARNING_TEXT = (
    "Кандидаты не регистрируются автоматически: статус «Требует подтверждения» "
    "означает предложенную переменную %w{1,n}, её нужно проверить и подтвердить."
)
CANDIDATE_DASHBOARD_TILES = (
    "% от всех сегментов",
    "Сегментов",
    "Выгода/мес",
    "Уверенность",
)
SUMMARY_STRETCH = 1
DASHBOARD_STRETCH = 1
SUMMARY_MIN_WIDTH = 240


def _theme_row_palette() -> RowPalette:
    """Фоны подсветки строк под активную тему."""
    palette = active_palette()
    return row_palette(palette.surface, palette.positive, palette.negative)


class CandidatesPage(QWidget):
    """Ищет группы похожих обычных сообщений и показывает прогноз выгоды."""

    candidates_found = Signal()

    def __init__(
        self,
        *,
        find_candidates: FindCandidates,
        matched_messages: ListMatchedMessages,
        list_batches: ListBatches,
        settings_provider: Callable[[], AppSettings],
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._find_candidates = find_candidates
        self._matched_messages = matched_messages
        self._list_batches = list_batches
        self._settings_provider = settings_provider
        self._thresholds: BenefitThresholds = settings_provider().benefit_thresholds
        self._runner = runner
        self._batch_id: str | None = None
        self._messages_dialog: MatchedMessagesDialog | None = None
        self._candidates: tuple[CandidateView, ...] = ()
        self._row_palette = _theme_row_palette()

        self._batch_combo = QComboBox(self)
        self._search_button = QPushButton("Найти кандидатов", self)
        self._recalc_button = QPushButton("Пересчитать", self)
        self._filter = QLineEdit(self)
        self._summary = QLabel(WARNING_TEXT, self)
        self._summary.setWordWrap(True)
        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._model = RowsTableModel(COLUMNS, self, row_color=self._row_color)
        self._table, self._proxy = build_table(
            self._model,
            self,
            stretch_column=0,
            min_stretch_width=CANDIDATE_STRETCH_WIDTH,
        )
        sort_by_title(self._table, "Выгода/мес", Qt.SortOrder.DescendingOrder)
        self._profit_total = BenefitTotal("Выгода в месяц от внедрения выгодных кандидатов", self)
        self._dashboard = SegmentDashboard(
            CANDIDATE_DASHBOARD_TILES,
            empty_title="Кандидат не выбран",
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
        top.addWidget(self._search_button)
        top.addWidget(self._recalc_button)
        layout.addLayout(top)

        self._filter.setPlaceholderText("Фильтр по тексту шаблона или отправителю")
        layout.addWidget(self._filter)
        layout.addWidget(self._summary)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._table)
        splitter.addWidget(self._build_lower_section())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, stretch=1)

        self._search_button.clicked.connect(lambda: self._search(force=False))
        self._recalc_button.clicked.connect(lambda: self._search(force=True))
        self._filter.textChanged.connect(self._proxy.setFilterFixedString)
        self._batch_combo.currentIndexChanged.connect(self._batch_changed)
        self._table.selectionModel().currentRowChanged.connect(self._selection_changed)
        self._table.clicked.connect(self._cell_clicked)

    def _build_lower_section(self) -> QWidget:
        """Слева — выгода и описание кандидата, справа — его мини-дашборд."""
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        left = QWidget(container)
        left.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(self._profit_total)

        self._details.setMinimumWidth(SUMMARY_MIN_WIDTH)
        left_layout.addWidget(self._details, stretch=1)

        self._dashboard.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(left, stretch=SUMMARY_STRETCH)
        row.addWidget(self._dashboard, stretch=DASHBOARD_STRETCH)
        return container

    def reload(self) -> None:
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
        self._search_button.setEnabled(has_batches)
        self._recalc_button.setEnabled(has_batches)
        if not has_batches:
            self._model.set_rows(())
            self._details.setPlainText("Статистика ещё не импортирована.")
            self._profit_total.reset()
            self._dashboard.clear()

    def _batch_changed(self, _index: int) -> None:
        self._candidates = ()
        self._batch_id = None
        self._model.set_rows(())
        self._details.setPlainText("")
        self._profit_total.reset()
        self._dashboard.clear()

    def reload_settings(self) -> None:
        """Применить новые пороги выгоды и перерисовать строки таблицы."""
        try:
            self._thresholds = self._settings_provider().benefit_thresholds
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать настройки: {exc}")
            return
        self._model.refresh()

    def refresh_theme(self) -> None:
        """Пересчитать цвета строк и итога под активную тему."""
        self._row_palette = _theme_row_palette()
        self._busy.refresh_theme()
        self._model.refresh()
        self._dashboard.refresh_theme()
        if self._candidates:
            self._update_profit_total(self._candidates)
        else:
            self._profit_total.reset()

    def _row_color(self, item: CandidateView) -> QColor | None:
        color = benefit_color(item.net_monthly, self._thresholds, self._row_palette)
        return QColor(color) if color is not None else None

    def _search(self, *, force: bool) -> None:
        batch_id = self._batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "Нет данных", "Сначала импортируйте статистику.")
            return
        self._set_busy(True, "Пересчёт кандидатов…" if force else "Идёт поиск кандидатов…")
        self._runner.run(
            lambda token: self._find_candidates.execute(
                str(batch_id), force=force, should_cancel=lambda: token.cancelled
            ),
            on_success=self._show,
            on_error=self._failed,
        )

    def _show(self, view: AnalysisView) -> None:
        self._set_busy(False)
        self._batch_id = view.batch_id
        candidates = view.candidates
        self._candidates = candidates
        self._model.set_rows(candidates)
        fit_columns(self._table, max_widths={0: 640})
        if candidates:
            net = candidates[0].net_monthly
            for item in candidates[1:]:
                net = net + item.net_monthly
            self._summary.setText(
                f"Найдено кандидатов: {format_int(len(candidates))} · "
                f"суммарная выгода в месяц {format_money(net)}. {WARNING_TEXT}"
            )
        else:
            self._summary.setText(
                "Кандидатов не найдено. Проверьте порог кластеризации и минимальный объём "
                f"группы в настройках. {WARNING_TEXT}"
            )
        self._update_profit_total(candidates)
        self._details.setPlainText("")
        self._dashboard.set_context(
            view.daily_total_segments,
            view.daily_templated_segments,
            (view.period_from.date(), view.period_to.date()),
        )
        self._dashboard.show_series(None)
        self._select_first_row()
        self.candidates_found.emit()

    def _select_first_row(self) -> None:
        """Выделить первого кандидата, чтобы мини-дашборд был заполнен."""
        if self._proxy.rowCount() > 0:
            self._table.selectRow(0)
            return
        self._details.setPlainText("")
        self._dashboard.show_series(None)

    def _update_profit_total(self, candidates: tuple[CandidateView, ...]) -> None:
        """Сумма выгоды выгодных кандидатов цветом активной темы."""
        profitable = positive_benefit(item.net_monthly for item in candidates)
        palette = active_palette()
        color = (
            semantic_text(palette.positive, palette.window)
            if profitable.amount > 0
            else neutral_color()
        )
        self._profit_total.set_value(format_money(profitable), color)

    def _cell_clicked(self, index: QModelIndex) -> None:
        """Щелчок по тексту кандидата открывает список его сообщений."""
        if index.column() != 0:
            return
        self._show_candidate_messages(index)

    def _show_candidate_messages(self, index: QModelIndex) -> None:
        """Открыть список сообщений, из которых собран кандидат."""
        source = self._proxy.mapToSource(index)
        if not source.isValid() or not self._batch_id:
            return
        candidate = self._model.row_at(source.row())
        batch_id = self._batch_id
        self._set_busy(True, "Загрузка сообщений…")
        self._runner.run(
            lambda token: self._matched_messages.for_candidate(
                batch_id,
                candidate,
                should_cancel=lambda: token.cancelled,
            ),
            on_success=lambda rows: self._open_messages_dialog(rows, candidate),
            on_error=self._messages_failed,
        )

    def _open_messages_dialog(
        self, rows: tuple[MatchedMessageView, ...], candidate: CandidateView
    ) -> None:
        self._set_busy(False)
        if self._messages_dialog is None:
            self._messages_dialog = MatchedMessagesDialog(self)
        self._messages_dialog.set_rows(
            rows,
            title=f"Сообщения кандидата · ID {candidate.candidate_id}",
            template_text=candidate.template_text,
            template_label="Полный текст шаблона-кандидата:",
        )
        self._messages_dialog.show()
        self._messages_dialog.raise_()

    def _messages_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Ошибка загрузки сообщений", message)

    def _selection_changed(self, current: object, _previous: object) -> None:
        index = self._proxy.mapToSource(current)  # type: ignore[arg-type]
        if not index.isValid():
            self._details.setPlainText("")
            self._dashboard.show_series(None)
            return
        candidate = self._model.row_at(index.row())
        self._details.setPlainText(_describe(candidate))
        self._dashboard.show_series(_candidate_series(candidate))

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self._search_button.setEnabled(not busy)
        self._recalc_button.setEnabled(not busy)
        self._batch_combo.setEnabled(not busy)
        if busy:
            self._busy.start(text)
        else:
            self._busy.stop()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        if message == CANCELLED_MESSAGE:
            self._details.setPlainText("Поиск кандидатов отменён.")
            return
        QMessageBox.critical(self, "Ошибка поиска кандидатов", message)


def _candidate_series(candidate: CandidateView) -> DashboardSeries:
    """Представление кандидата для общего мини-дашборда.

    В режиме «Только шаблонированные» его сообщения добавляются к шаблонному
    трафику: моделируется регистрация шаблона со 100 % срабатыванием.
    """
    benefit = candidate.net_monthly
    tone = "positive" if benefit.amount > 0 else "negative" if benefit.amount < 0 else "neutral"
    return DashboardSeries(
        title=f"Кандидат · {candidate.template_text}",
        tooltip=_describe(candidate),
        matched=candidate.daily_segments,
        tiles=(
            DashboardTile(format_percent(candidate.share_of_all_segments)),
            DashboardTile(format_int(candidate.segments)),
            DashboardTile(format_money(benefit), tone),
            DashboardTile(format_percent(candidate.confidence)),
        ),
        templated_extra=candidate.daily_segments,
        series_label="кандидат",
        matched_label="Сообщения кандидата",
    )


def _describe(candidate: CandidateView) -> str:
    lines = [
        f"Шаблон: {candidate.template_text}",
        f"Статус: {_status_title(candidate.status)}",
        f"Период: {format_period(candidate.period_from, candidate.period_to)}"
        + (
            " (неполный: выгода в месяц смоделирована на 30 дней)"
            if candidate.is_partial_period
            else ""
        ),
        f"Сообщений: {format_int(candidate.messages)}, сегментов: {format_int(candidate.segments)}",
        f"Заплачено фактически: {format_money(candidate.actual_cost)}, "
        f"если шаблон: {format_money(candidate.templated_cost)}",
        f"Модель месяца: сообщений {format_int(candidate.monthly_messages)}, "
        f"сегментов {format_int(candidate.monthly_segments)}",
        f"Стоимость/мес: {format_money(candidate.monthly_actual_cost)}, "
        f"если шаблон/мес: {format_money(candidate.monthly_templated_cost)}",
        f"Экономия в месяц: {format_money(candidate.monthly_saving)}, "
        f"стоимость шаблона: {format_money(candidate.template_fee)}",
        f"Выгода в месяц: {format_money(candidate.net_monthly)}",
        f"Уверенность: {format_percent(candidate.confidence)}, "
        f"покрытие: {format_percent(candidate.coverage)}",
        f"Чужих совпадений: {format_int(candidate.foreign_matches)}",
        f"Отправители: {', '.join(candidate.senders) or '—'}",
        f"Операторы: {', '.join(candidate.operators) or '—'}",
    ]
    if candidate.warnings:
        lines.append("Предупреждения:")
        lines.extend(f"  • {warning}" for warning in candidate.warnings)
    lines.extend(["", "Примеры сообщений:"])
    lines.extend(f"  • {example}" for example in candidate.examples)
    return "\n".join(lines)
