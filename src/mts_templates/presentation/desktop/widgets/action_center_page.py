"""Экран «Центр действий»: рабочий список потерь и проблем по загрузке."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
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
    ActionCenterView,
    ActionItemView,
    ImportBatch,
    MatchedMessageView,
)
from mts_templates.application.use_cases.dashboard import ListBatches
from mts_templates.application.use_cases.get_action_center import GetActionCenter
from mts_templates.application.use_cases.list_matched_messages import ListMatchedMessages
from mts_templates.presentation.desktop.benefit_style import RowPalette, row_palette, semantic_text
from mts_templates.presentation.desktop.dialogs.matched_messages_dialog import MatchedMessagesDialog
from mts_templates.presentation.desktop.formatting import (
    format_int,
    format_money,
    format_period,
)
from mts_templates.presentation.desktop.models.table_model import Column, RowsTableModel
from mts_templates.presentation.desktop.models.table_view import (
    build_table,
    fit_columns,
    sort_by_title,
)
from mts_templates.presentation.desktop.theme import active_palette
from mts_templates.presentation.desktop.widgets.benefit_totals import BenefitTotal, neutral_color
from mts_templates.presentation.desktop.widgets.busy_overlay import BusyOverlay
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

TABLE_STRETCH = 4
LOWER_STRETCH = 3
SPLIT_WEIGHT_SCALE = 1000

COLUMNS = (
    Column(
        "Приоритет",
        lambda item: item.severity,
        formatter=lambda value: str(int(value or 0)),
        width=90,
        tooltip=lambda item: _severity_title(item.severity),
    ),
    Column(
        "Проблема",
        lambda item: item.title,
        width=300,
        tooltip=lambda item: f"{item.title}. {item.detail}",
    ),
    Column(
        "Шаблон / объект",
        lambda item: item.subject,
        width=360,
        tooltip=lambda item: item.subject,
    ),
    Column("Оператор", lambda item: item.operator or "—", width=120),
    Column("Сообщений", lambda item: item.messages, formatter=format_int, width=90),
    Column("Сегментов", lambda item: item.segments, formatter=format_int, width=90),
    Column(
        "Потери/мес",
        lambda item: item.monthly_loss,
        formatter=format_money,
        width=110,
        tooltip=lambda item: f"за период: {format_money(item.monthly_loss)}",
    ),
)


def _severity_title(severity: int) -> str:
    if severity >= 3:
        return "Критично"
    if severity == 2:
        return "Высокий"
    if severity == 1:
        return "Средний"
    return "Инфо"


def _theme_row_palette() -> RowPalette:
    """Фоны подсветки строк под активную тему."""
    palette = active_palette()
    return row_palette(palette.surface, palette.positive, palette.negative)


def _batch_title(batch: ImportBatch) -> str:
    return (
        f"{Path(batch.source_path).name} · "
        f"{format_period(batch.period_from, batch.period_to)} · "
        f"{format_int(batch.message_count)} сообщ."
    )


class ActionCenterPage(QWidget):
    """Рабочий список проблем: суммы потерь в месяц и переход к сообщениям."""

    def __init__(
        self,
        *,
        action_center: GetActionCenter,
        matched_messages: ListMatchedMessages,
        list_batches: ListBatches,
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._action_center = action_center
        self._matched_messages = matched_messages
        self._list_batches = list_batches
        self._runner = runner
        self._batch_id: str | None = None
        self._messages_dialog: MatchedMessagesDialog | None = None
        self._row_palette = _theme_row_palette()

        self._batch_combo = QComboBox(self)
        self._analyze_button = QPushButton("Выполнить анализ", self)
        self._recalc_button = QPushButton("Пересчитать", self)
        self._filter = QLineEdit(self)
        self._summary = QLabel("Центр действий ещё не собран.", self)
        self._warnings = QPlainTextEdit(self)
        self._warnings.setObjectName("warningsView")
        self._warnings.setReadOnly(True)
        self._warnings.setMaximumHeight(180)
        self._total_loss = BenefitTotal("Потери в месяц", self, inline=True)
        self._off_loss = BenefitTotal("Убыток от операторов вне списка, ₽/мес", self, inline=True)
        self._untriggered_loss = BenefitTotal(
            "Срабатывание ниже 100 %, ₽/мес",
            self,
            inline=True,
        )
        self._unmatched_label = QLabel("", self)
        self._model = RowsTableModel(COLUMNS, self, row_color=self._row_color)
        self._table, self._proxy = build_table(self._model, self, stretch_column=0)
        sort_by_title(self._table, "Потери/мес", Qt.SortOrder.DescendingOrder)
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

        self._filter.setPlaceholderText("Фильтр по проблеме, шаблону, оператору")
        layout.addWidget(self._filter)

        losses_row = QHBoxLayout()
        losses_row.addWidget(self._total_loss, stretch=1)
        losses_row.addWidget(self._off_loss, stretch=1)
        losses_row.addWidget(self._untriggered_loss, stretch=1)
        layout.addLayout(losses_row)
        layout.addWidget(self._unmatched_label)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._table)
        splitter.addWidget(self._build_warnings())
        splitter.setStretchFactor(0, TABLE_STRETCH)
        splitter.setStretchFactor(1, LOWER_STRETCH)
        splitter.setSizes([TABLE_STRETCH * SPLIT_WEIGHT_SCALE, LOWER_STRETCH * SPLIT_WEIGHT_SCALE])
        layout.addWidget(splitter, stretch=1)

        self._analyze_button.clicked.connect(lambda: self._analyze(force=False))
        self._recalc_button.clicked.connect(lambda: self._analyze(force=True))
        self._filter.textChanged.connect(self._apply_filter)
        self._batch_combo.currentIndexChanged.connect(self._batch_changed)
        self._table.selectionModel().currentRowChanged.connect(self._selection_changed)
        self._table.clicked.connect(self._cell_clicked)

    def _build_warnings(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._summary)
        layout.addWidget(self._warnings, stretch=1)
        return container

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
            self._reset_totals()
            self._unmatched_label.setVisible(False)
            self._filter.clear()

    def refresh_theme(self) -> None:
        """Перерисовать цвета строк под активную тему."""
        self._row_palette = _theme_row_palette()
        self._busy.refresh_theme()
        self._model.refresh()

    def _batch_changed(self, _index: int) -> None:
        self._model.set_rows(())
        self._batch_id = None
        self._reset_totals()
        self._unmatched_label.setVisible(False)
        self._summary.setText("Нажмите «Выполнить анализ», чтобы собрать центр действий.")
        self._warnings.setPlainText("")

    def _analyze(self, *, force: bool) -> None:
        batch_id = self._batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "Нет данных", "Сначала импортируйте статистику.")
            return
        self._set_busy(True, "Пересчёт центра действий…" if force else "Выполняется анализ…")
        self._runner.run(
            lambda token: self._action_center.execute(
                str(batch_id),
                force=force,
                should_cancel=lambda: token.cancelled,
            ),
            on_success=self._show,
            on_error=self._failed,
        )

    def _show(self, center: ActionCenterView) -> None:
        self._set_busy(False)
        self._batch_id = center.batch_id
        self._model.set_rows(center.items)
        self._apply_filter(self._filter.text())
        fit_columns(
            self._table,
            max_widths={0: 90, 1: 300, 2: 360, 3: 120, 4: 90, 5: 90, 6: 110},
        )
        self._apply_totals(center)
        summary = (
            f"Период {format_period(center.period_from, center.period_to)} · "
            f"потери в месяц {format_money(center.total_monthly_loss)} · "
            f"шаблонов с убытком {format_int(center.loss_templates)} · "
            f"несопоставленных шаблонированных {format_int(center.unmatched_templated_messages)}"
        )
        if center.is_partial_period:
            summary += " · неполный период: денежные суммы и объёмы смоделированы на 30 дней"
        self._summary.setText(summary)
        lines = list(center.warnings)
        if not lines:
            lines.append("Предупреждений нет.")
        self._warnings.setPlainText("\n".join(f"• {line}" for line in lines))
        self._select_first_row()

    def _apply_totals(self, center: ActionCenterView) -> None:
        loss_color = semantic_text(active_palette().negative, active_palette().window)
        neutral = neutral_color()
        self._total_loss.set_value(format_money(center.total_monthly_loss), loss_color)
        self._off_loss.set_value(
            format_money(center.off_operator_loss),
            loss_color if center.off_operator_loss.amount > 0 else neutral,
        )
        self._untriggered_loss.set_value(
            format_money(center.untriggered_loss),
            loss_color if center.untriggered_loss.amount > 0 else neutral,
        )
        self._unmatched_label.setVisible(center.unmatched_templated_messages > 0)
        if center.unmatched_templated_messages > 0:
            self._unmatched_label.setText(
                f"Шаблонировано без шаблона: {format_int(center.unmatched_templated_messages)} сообщений "
                f"· {format_int(center.unmatched_templated_segments)} сегментов · "
                f"оплачено за период {format_money(center.unmatched_templated_cost)}"
            )

    def _select_first_row(self) -> None:
        if self._proxy.rowCount() > 0:
            self._table.selectRow(0)

    def _apply_filter(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def _row_color(self, item: ActionItemView) -> QColor | None:
        if item.severity <= 0 or item.monthly_loss.amount <= 0:
            return None
        return QColor(self._row_palette.loss_color)

    def _selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        index = self._proxy.mapToSource(current)
        if not index.isValid():
            return

    def _cell_clicked(self, index: QModelIndex) -> None:
        source = self._proxy.mapToSource(index)
        if not source.isValid() or source.column() != 0:
            return
        self._open_drill_down(source.row())

    def _open_drill_down(self, row: int) -> None:
        item: ActionItemView = self._model.row_at(row)
        batch_id = self._batch_id
        if not batch_id:
            return
        self._set_busy(True, "Загрузка сообщений…")
        if item.kind == "unmatched_templated" or item.drill_down == "unmatched_templated":
            self._runner.run(
                lambda token: self._matched_messages.unmatched_templated(
                    batch_id,
                    should_cancel=lambda: token.cancelled,
                ),
                on_success=lambda rows: self._open_messages_dialog(rows, item, unmatched=True),
                on_error=self._messages_failed,
            )
            return
        template_id = item.template_id
        if not template_id:
            return
        self._runner.run(
            lambda token: self._matched_messages.for_template(
                batch_id,
                template_id,
                operator=item.operator,
                untriggered_only=item.kind in ("off_operator", "untriggered"),
                should_cancel=lambda: token.cancelled,
            ),
            on_success=lambda rows: self._open_messages_dialog(rows, item, unmatched=False),
            on_error=self._messages_failed,
        )

    def _open_messages_dialog(
        self,
        rows: Sequence[MatchedMessageView],
        item: ActionItemView,
        *,
        unmatched: bool,
    ) -> None:
        self._set_busy(False)
        if self._messages_dialog is None:
            self._messages_dialog = MatchedMessagesDialog(self)
        text = item.subject
        text_label = "Полный текст шаблона:"
        if unmatched and rows:
            text = rows[0].text
            text_label = "Текст сообщения:"
        self._messages_dialog.set_rows(
            list(rows),
            title=item.title,
            template_text=text,
            text_label=text_label,
        )
        self._messages_dialog.show()

    def _messages_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Ошибка загрузки сообщений", message)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        if busy:
            self._busy.start(text)
        else:
            self._busy.stop()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        if message == CANCELLED_MESSAGE:
            self._summary.setText("Операция отменена.")
            return
        QMessageBox.critical(self, "Ошибка", message)

    def _reset_totals(self) -> None:
        self._total_loss.reset()
        self._off_loss.reset()
        self._untriggered_loss.reset()
