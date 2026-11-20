"""Экран импорта статистики и шаблонов."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import (
    ImportReport,
    ImportStatisticsRequest,
    ImportTemplatesRequest,
    TemplateFilePreview,
    TemplateImportReport,
)
from mts_templates.application.ports import SettingsStore
from mts_templates.application.settings import AppSettings
from mts_templates.application.use_cases.import_statistics import ImportStatistics
from mts_templates.application.use_cases.import_templates import (
    ImportTemplates,
    PreviewTemplateFile,
)
from mts_templates.presentation.desktop.dialogs.column_mapping_dialog import (
    ColumnMappingDialog,
)
from mts_templates.presentation.desktop.formatting import format_money, format_period
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
        settings_store: SettingsStore,
        settings: AppSettings,
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._import_statistics = import_statistics
        self._preview_templates = preview_templates
        self._import_templates = import_templates
        self._settings_store = settings_store
        self._settings = settings
        self._runner = runner

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
