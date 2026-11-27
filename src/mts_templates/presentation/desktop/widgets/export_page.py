"""Экран «Экспорт»: Excel-отчёт по загрузке и последнему анализу."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import ExportReportRequest
from mts_templates.application.ports import SettingsStore
from mts_templates.application.settings import AppSettings
from mts_templates.application.use_cases.dashboard import ListBatches
from mts_templates.application.use_cases.export_report import ExportReport
from mts_templates.presentation.desktop.formatting import format_batch_title, format_int
from mts_templates.presentation.desktop.workers import CANCELLED_MESSAGE, BackgroundRunner

EXCEL_FILTER = "Excel (*.xlsx)"


class ExportPage(QWidget):
    """Собирает отчёт через use case и сохраняет xlsx на диск."""

    def __init__(
        self,
        *,
        export_report: ExportReport,
        list_batches: ListBatches,
        settings_store: SettingsStore,
        settings: AppSettings,
        runner: BackgroundRunner,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._export_report = export_report
        self._list_batches = list_batches
        self._settings_store = settings_store
        self._settings = settings
        self._runner = runner

        self._batch_combo = QComboBox(self)
        self._path = QLineEdit(self)
        self._export_button = QPushButton("Экспортировать", self)
        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)

        self._build()
        self.reload()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Загрузка для отчёта:", self))
        layout.addWidget(self._batch_combo)

        layout.addWidget(QLabel("Файл отчёта:", self))
        row = QHBoxLayout()
        self._path.setPlaceholderText("Путь к xlsx-файлу отчёта")
        browse = QPushButton("Обзор…", self)
        browse.clicked.connect(self._browse)
        row.addWidget(self._path, stretch=1)
        row.addWidget(browse)
        row.addWidget(self._export_button)
        layout.addLayout(row)

        hint = QLabel(
            "Отчёт содержит листы «Сводка», «Шаблоны», «Кандидаты» и «Предупреждения». "
            "Перед экспортом выполните анализ на экране «Шаблоны» или «Кандидаты».",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._log, stretch=1)

        self._export_button.clicked.connect(self._export)

    def reload(self) -> None:
        try:
            batches = self._list_batches.execute()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return

        current = self._batch_combo.currentData()
        self._batch_combo.clear()
        for batch in batches:
            self._batch_combo.addItem(format_batch_title(batch), batch.id)
        if current is not None:
            index = self._batch_combo.findData(current)
            if index >= 0:
                self._batch_combo.setCurrentIndex(index)

        has_batches = bool(batches)
        self._export_button.setEnabled(has_batches)
        if not has_batches:
            self._log.appendPlainText("Статистика ещё не импортирована.")
            return
        if not self._path.text().strip():
            self._path.setText(str(self._default_path()))

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Файл отчёта", self._path.text() or str(self._default_path()), EXCEL_FILTER
        )
        if path:
            self._path.setText(path)

    def _export(self) -> None:
        batch_id = self._batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "Нет данных", "Сначала импортируйте статистику.")
            return
        raw = self._path.text().strip()
        if not raw:
            QMessageBox.warning(self, "Файл не выбран", "Укажите путь к файлу отчёта.")
            return
        path = Path(raw)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
            self._path.setText(str(path))

        self._set_busy(True)
        self._runner.run(
            lambda _token: self._export_report.execute(
                ExportReportRequest(path=path, batch_id=str(batch_id))
            ),
            on_success=self._exported,
            on_error=self._failed,
        )

    def _exported(self, result: object) -> None:
        self._set_busy(False)
        target = result.path  # type: ignore[attr-defined]
        self._log.appendPlainText(
            f"[{datetime.now():%H:%M:%S}] Отчёт сохранён: {target} "
            f"(шаблонов {format_int(result.templates)}, "  # type: ignore[attr-defined]
            f"кандидатов {format_int(result.candidates)})."  # type: ignore[attr-defined]
        )
        self._remember(Path(target).parent)
        QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{target}")

    def _remember(self, directory: Path) -> None:
        try:
            current = self._settings_store.load()
            self._settings_store.save(current.with_overrides(last_export_dir=directory))
        except OSError:
            self._log.appendPlainText("Не удалось сохранить каталог экспорта в настройках.")

    def _set_busy(self, busy: bool) -> None:
        self._export_button.setEnabled(not busy)

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        if message == CANCELLED_MESSAGE:
            self._log.appendPlainText("Экспорт отменён.")
            return
        self._log.appendPlainText(f"Ошибка экспорта: {message}")
        QMessageBox.critical(self, "Ошибка экспорта", message)

    def _default_path(self) -> Path:
        try:
            settings = self._settings_store.load()
        except Exception:
            settings = self._settings
        directory = settings.last_export_dir or settings.data_dir
        return directory / f"mts-templates-{datetime.now():%Y-%m-%d-%H%M}.xlsx"
