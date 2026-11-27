"""Экран импорта статистики и шаблонов."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    ImportBatch,
    ImportReport,
    ImportStatisticsRequest,
    ImportTemplatesRequest,
    TemplateFilePreview,
    TemplateImportReport,
)
from mts_templates.application.ports import SettingsStore
from mts_templates.application.settings import AppSettings
from mts_templates.application.use_cases.dashboard import ListBatches
from mts_templates.application.use_cases.import_statistics import ImportStatistics
from mts_templates.application.use_cases.import_templates import (
    ImportTemplates,
    PreviewTemplateFile,
)
from mts_templates.application.use_cases.manage_batches import (
    DeleteAllBatches,
    DeleteBatch,
    RenameBatch,
    SetBatchPeriodLabel,
)
from mts_templates.presentation.desktop.dialogs.column_mapping_dialog import (
    ColumnMappingDialog,
)
from mts_templates.presentation.desktop.formatting import (
    format_int,
    format_money,
    format_period,
)
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

EXCEL_FILTER = "Excel (*.xlsx *.xlsm)"


class ImportPage(QWidget):
    """Два независимых импорта: статистика отправок и список шаблонов."""

    data_changed = Signal()

    def __init__(
        self,
        *,
        import_statistics: ImportStatistics,
        preview_templates: PreviewTemplateFile,
        import_templates: ImportTemplates,
        list_batches: ListBatches,
        rename_batch: RenameBatch,
        set_period_label: SetBatchPeriodLabel,
        delete_batch: DeleteBatch,
        delete_all_batches: DeleteAllBatches,
        settings_store: SettingsStore,
        settings: AppSettings,
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._import_statistics = import_statistics
        self._preview_templates = preview_templates
        self._import_templates = import_templates
        self._list_batches = list_batches
        self._rename_batch = rename_batch
        self._set_period_label = set_period_label
        self._delete_batch = delete_batch
        self._delete_all_batches = delete_all_batches
        self._settings_store = settings_store
        self._settings = settings
        self._runner = runner

        self._batches: tuple[ImportBatch, ...] = ()
        self._batches_by_id: dict[str, ImportBatch] = {}

        self._statistics_path = QLineEdit(self)
        self._templates_path = QLineEdit(self)
        self._statistics_button = QPushButton("Импортировать статистику", self)
        self._templates_button = QPushButton("Импортировать шаблоны", self)
        self._log_view = QPlainTextEdit(self)
        self._log_view.setReadOnly(True)

        self._build()
        self._restore_paths()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        statistics_box = QGroupBox("Статистика МТС-Маркетолога", self)
        statistics_layout = QVBoxLayout(statistics_box)
        statistics_layout.addWidget(QLabel("Выгрузка статистики отправок за период (xlsx).", self))
        statistics_layout.addLayout(
            self._file_row(
                self._statistics_path,
                "Путь к файлу статистики",
                self._browse_statistics,
                self._statistics_button,
            )
        )
        self._statistics_button.clicked.connect(self._import_statistics_clicked)
        layout.addWidget(statistics_box)

        templates_box = QGroupBox("Список зарегистрированных шаблонов", self)
        templates_layout = QVBoxLayout(templates_box)
        templates_layout.addWidget(
            QLabel(
                "Excel со списком шаблонов. Колонки сопоставляются вручную, "
                "если их не удалось определить автоматически.",
                self,
            )
        )
        templates_layout.addLayout(
            self._file_row(
                self._templates_path,
                "Путь к файлу шаблонов",
                self._browse_templates,
                self._templates_button,
            )
        )
        self._templates_button.clicked.connect(self._import_templates_clicked)
        layout.addWidget(templates_box)

        management_box = QGroupBox("Загрузки в базе", self)
        management_layout = QVBoxLayout(management_box)
        self._batches_table = QTableWidget()
        self._batches_table.setColumnCount(5)
        self._batches_table.setHorizontalHeaderLabels(
            ["Название", "Период", "Метка периода", "Сообщений", "Стоимость"]
        )
        self._batches_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batches_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batches_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._batches_table.horizontalHeader().setStretchLastSection(True)
        self._batches_table.itemSelectionChanged.connect(self._on_batch_selection_changed)
        management_layout.addWidget(self._batches_table, stretch=1)

        management_buttons = QHBoxLayout()
        self._rename_batch_button = QPushButton("Переименовать", self)
        self._rename_batch_button.clicked.connect(self._rename_batch_clicked)
        self._period_label_button = QPushButton("Метка периода", self)
        self._period_label_button.clicked.connect(self._period_label_batch_clicked)
        self._delete_batch_button = QPushButton("Удалить", self)
        self._delete_batch_button.clicked.connect(self._delete_batch_clicked)
        self._delete_all_button = QPushButton("Удалить все", self)
        self._delete_all_button.clicked.connect(self._delete_all_batches_clicked)
        self._refresh_batches_button = QPushButton("Обновить", self)
        self._refresh_batches_button.clicked.connect(self._reload_batches)
        management_buttons.addWidget(self._rename_batch_button)
        management_buttons.addWidget(self._period_label_button)
        management_buttons.addWidget(self._delete_batch_button)
        management_buttons.addWidget(self._delete_all_button)
        management_buttons.addWidget(self._refresh_batches_button)
        management_buttons.addStretch(1)
        management_layout.addLayout(management_buttons)
        layout.addWidget(management_box, stretch=1)

        log_box = QGroupBox("Журнал операций", self)
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self._log_view)
        layout.addWidget(log_box, stretch=1)

    def _file_row(
        self,
        line_edit: QLineEdit,
        placeholder: str,
        browse_handler: Callable[[], None],
        action_button: QPushButton,
    ) -> QHBoxLayout:
        line_edit.setPlaceholderText(placeholder)
        browse = QPushButton("Обзор…", self)
        browse.clicked.connect(browse_handler)
        row = QHBoxLayout()
        row.addWidget(line_edit, stretch=1)
        row.addWidget(browse)
        row.addWidget(action_button)
        return row

    def _restore_paths(self) -> None:
        if self._settings.last_statistics_dir is not None:
            self._statistics_path.setText(str(self._settings.last_statistics_dir))
        if self._settings.last_templates_dir is not None:
            self._templates_path.setText(str(self._settings.last_templates_dir))

    def _browse_statistics(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Файл статистики", self._statistics_path.text(), EXCEL_FILTER
        )
        if path:
            self._statistics_path.setText(path)

    def _browse_templates(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Файл шаблонов", self._templates_path.text(), EXCEL_FILTER
        )
        if path:
            self._templates_path.setText(path)

    def _import_statistics_clicked(self) -> None:
        path = self._selected_path(self._statistics_path, "статистики")
        if path is None:
            return
        self._set_busy(True)
        self._runner.run(
            lambda token: self._import_statistics.execute(
                ImportStatisticsRequest(path=path),
                should_cancel=lambda: token.cancelled,
            ),
            on_success=self._statistics_imported,
            on_error=self._failed,
        )

    def _statistics_imported(self, report: ImportReport) -> None:
        self._set_busy(False)
        batch = report.batch
        self._log("Импорт статистики завершён.")
        self._log(
            f"Строк: {batch.row_count}, сообщений: {batch.message_count}, "
            f"сегментов: {batch.segment_count}."
        )
        self._log(
            f"Период: {format_period(batch.period_from, batch.period_to)}, "
            f"стоимость: {format_money(batch.total_cost)}."
        )
        self._log(
            f"Доставлено: {batch.delivered_rows}, ошибок отправки: {batch.send_error_rows}, "
            f"ошибок доставки: {batch.delivery_error_rows}, "
            f"строк без пакета: {batch.empty_package_rows}."
        )
        if getattr(report, "reused", False):
            self._log("Файл уже импортирован ранее: использована существующая загрузка.")
        for warning in batch.warnings:
            self._log(f"Внимание: {warning}")
        self._remember("last_statistics_dir", Path(batch.source_path).parent)
        self._reload_batches()
        self.data_changed.emit()

    def _import_templates_clicked(self) -> None:
        path = self._selected_path(self._templates_path, "шаблонов")
        if path is None:
            return
        self._set_busy(True)
        self._runner.run(
            lambda _token: self._preview_templates.execute(path),
            on_success=lambda preview: self._templates_previewed(preview, path),
            on_error=self._failed,
        )

    def _templates_previewed(self, preview: TemplateFilePreview, path: Path) -> None:
        self._set_busy(False)
        dialog = ColumnMappingDialog(preview, self)
        if dialog.exec() != ColumnMappingDialog.DialogCode.Accepted:
            self._log("Импорт шаблонов отменён.")
            return
        mapping = dialog.mapping()
        self._set_busy(True)
        self._runner.run(
            lambda _token: self._import_templates.execute(
                ImportTemplatesRequest(path=path, mapping=mapping)
            ),
            on_success=self._templates_imported,
            on_error=self._failed,
        )

    def _templates_imported(self, report: TemplateImportReport) -> None:
        self._set_busy(False)
        self._log(
            f"Шаблоны импортированы: новых {report.imported}, "
            f"обновлено {report.updated}, удалено {report.removed}, "
            f"дубликатов {report.duplicates}."
        )
        for warning in report.warnings:
            self._log(f"Внимание: {warning}")
        self._remember("last_templates_dir", Path(self._templates_path.text()).parent)
        self.data_changed.emit()

    def _reload_batches(self) -> None:
        batches = self._list_batches.execute()
        self._batches = batches
        self._batches_by_id = {batch.id: batch for batch in batches}
        self._batches_table.setRowCount(len(batches))
        for row, batch in enumerate(batches):
            self._batches_table.setItem(row, 0, QTableWidgetItem(self._display_name(batch)))
            self._batches_table.setItem(row, 1, QTableWidgetItem(self._format_period_text(batch)))
            self._batches_table.setItem(row, 2, QTableWidgetItem(batch.period_label or ""))
            self._batches_table.setItem(row, 3, QTableWidgetItem(format_int(batch.message_count)))
            self._batches_table.setItem(
                row, 4, QTableWidgetItem(format_int(int(batch.total_cost.amount * 100)))
            )
        self._on_batch_selection_changed()

    def _on_batch_selection_changed(self) -> None:
        has_selection = bool(self._batches_table.selectedItems())
        self._rename_batch_button.setEnabled(has_selection)
        self._period_label_button.setEnabled(has_selection)
        self._delete_batch_button.setEnabled(has_selection)

    def _selected_batch_id(self) -> str | None:
        selected = self._batches_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        if row < 0 or row >= len(self._batches):
            return None
        return self._batches[row].id

    def _selected_batch(self) -> ImportBatch | None:
        batch_id = self._selected_batch_id()
        if batch_id is None:
            return None
        return self._batches_by_id.get(batch_id)

    def _rename_batch_clicked(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            QMessageBox.information(self, "Загрузки", "Выберите загрузку в таблице.")
            return
        name, accepted = QInputDialog.getText(
            self,
            "Переименовать загрузку",
            "Новое название загрузки:",
            text=batch.name or "",
        )
        if not accepted:
            return
        try:
            self._rename_batch.execute(batch.id, name.strip() or None)
        except ValueError as error:
            QMessageBox.warning(self, "Переименовать загрузку", str(error))
            return
        self._log("Загрузка переименована.")
        self._reload_batches()
        self.data_changed.emit()

    def _period_label_batch_clicked(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            QMessageBox.information(self, "Загрузки", "Выберите загрузку в таблице.")
            return
        label, accepted = QInputDialog.getText(
            self,
            "Метка периода",
            "Текстовая метка периода (например, «Октябрь 2026»):",
            text=batch.period_label or "",
        )
        if not accepted:
            return
        try:
            self._set_period_label.execute(batch.id, label.strip() or None)
        except ValueError as error:
            QMessageBox.warning(self, "Метка периода", str(error))
            return
        self._log("Метка периода обновлена.")
        self._reload_batches()
        self.data_changed.emit()

    def _delete_batch_clicked(self) -> None:
        batch = self._selected_batch()
        if batch is None:
            QMessageBox.information(self, "Загрузки", "Выберите загрузку в таблице.")
            return
        title = self._display_name(batch)
        answer = QMessageBox.question(
            self,
            "Удалить загрузку",
            f"Удалить загрузку «{title}»?\n"
            "Сообщения, биллинговые строки и результаты анализа будут удалены безвозвратно.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self._delete_batch.execute(batch.id):
            QMessageBox.warning(self, "Удалить загрузку", "Загрузка не найдена.")
            return
        self._log("Загрузка удалена.")
        self._reload_batches()
        self.data_changed.emit()

    def _delete_all_batches_clicked(self) -> None:
        batches = self._list_batches.execute()
        if not batches:
            return
        answer = QMessageBox.question(
            self,
            "Удалить все загрузки",
            f"Удалить все загрузки статистики ({len(batches)})?\n"
            "Сообщения и результаты анализа будут удалены безвозвратно. Шаблоны не удаляются.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted = self._delete_all_batches.execute()
        self._log(f"Удалены загрузки: {deleted}.")
        self._reload_batches()
        self.data_changed.emit()

    def _display_name(self, batch: ImportBatch) -> str:
        return batch.name or Path(batch.source_path).name

    def _format_period_text(self, batch: ImportBatch) -> str:
        return batch.period_label or format_period(batch.period_from, batch.period_to) or "—"

    def _selected_path(self, line_edit: QLineEdit, what: str) -> Path | None:
        raw = line_edit.text().strip()
        if not raw:
            QMessageBox.warning(self, "Файл не выбран", f"Укажите файл {what}.")
            return None
        path = Path(raw)
        if not path.is_file():
            QMessageBox.warning(self, "Файл не найден", f"Файл не найден: {path}")
            return None
        return path

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        if message == CANCELLED_MESSAGE:
            self._log("Операция отменена.")
            return
        self._log(f"Ошибка: {message}")
        QMessageBox.critical(self, "Ошибка", message)

    def _set_busy(self, busy: bool) -> None:
        self._statistics_button.setEnabled(not busy)
        self._templates_button.setEnabled(not busy)

    def _remember(self, key: str, directory: Path) -> None:
        try:
            current = self._settings_store.load()
            self._settings_store.save(current.with_overrides(**{key: directory}))
        except OSError:
            self._log("Не удалось сохранить каталог последнего файла в настройках.")

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log_view.appendPlainText(f"[{stamp}] {message}")
