"""Главное окно приложения: вкладки экранов и связывание сигналов."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QWidget,
)

from mts_templates.composition import Container
from mts_templates.presentation.desktop.widgets.candidates_page import CandidatesPage
from mts_templates.presentation.desktop.widgets.dashboard_page import DashboardPage
from mts_templates.presentation.desktop.widgets.export_page import ExportPage
from mts_templates.presentation.desktop.widgets.import_page import ImportPage
from mts_templates.presentation.desktop.widgets.settings_page import SettingsPage
from mts_templates.presentation.desktop.widgets.templates_page import TemplatesPage
from mts_templates.presentation.desktop.workers import BackgroundRunner

WINDOW_TITLE = "MTS SMS Templates Optimus — анализ шаблонов и выгоды"


class MainWindow(QMainWindow):
    """Собирает экраны приложения в одном окне."""

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._runner = BackgroundRunner(self)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1280, 820)

        self._tabs = QTabWidget(self)
        self.setCentralWidget(self._tabs)

        self._import_page = ImportPage(
            import_statistics=container.import_statistics,
            preview_templates=container.preview_templates,
            import_templates=container.import_templates,
            settings_store=container.settings_store,
            settings=container.settings,
            runner=self._runner,
        )
        self._dashboard_page = DashboardPage(
            dashboard=container.dashboard,
            list_batches=container.list_batches,
            runner=self._runner,
        )
        self._templates_page = TemplatesPage(
            analyze_templates=container.analyze_templates,
            list_batches=container.list_batches,
            settings_provider=container.settings_store.load,
            runner=self._runner,
        )
        self._candidates_page = CandidatesPage(
            find_candidates=container.find_candidates,
            list_batches=container.list_batches,
            settings_provider=container.settings_store.load,
            runner=self._runner,
        )
        self._export_page = ExportPage(
            export_report=container.export_report,
            list_batches=container.list_batches,
            settings_store=container.settings_store,
            settings=container.settings,
            runner=self._runner,
        )
        self._settings_page = SettingsPage(
            settings_store=container.settings_store,
            settings=container.settings,
        )

        self._add_page(self._import_page, "Импорт")
        self._add_page(self._dashboard_page, "Дашборд")
        self._add_page(self._templates_page, "Шаблоны")
        self._add_page(self._candidates_page, "Кандидаты")
        self._add_page(self._export_page, "Экспорт")
        self._add_page(self._settings_page, "Настройки")

        self._connect_signals()
        self._build_status_bar()
        self.statusBar().showMessage(
            f"Данные: {container.settings.data_dir} · база: {container.database.path.name}"
        )

    def _add_page(self, page: QWidget, title: str) -> None:
        self._tabs.addTab(page, title)

    def _build_status_bar(self) -> None:
        """Индикатор длительных операций и кнопка отмены в статус-баре."""
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setMaximumWidth(160)
        self._progress.setVisible(False)

        self._cancel_button = QPushButton("Отмена", self)
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._runner.cancel)

        status = self.statusBar()
        status.addPermanentWidget(self._progress)
        status.addPermanentWidget(self._cancel_button)
        self._runner.busy_changed.connect(self._on_busy_changed)

    def _on_busy_changed(self, busy: bool) -> None:
        self._progress.setVisible(busy)
        self._cancel_button.setVisible(busy)
        self._cancel_button.setEnabled(busy)

    def _connect_signals(self) -> None:
        self._import_page.data_changed.connect(self._on_data_changed)
        self._templates_page.analysis_completed.connect(self._on_analysis_changed)
        self._candidates_page.candidates_found.connect(self._on_analysis_changed)
        self._settings_page.settings_saved.connect(self._on_settings_saved)

    def _on_data_changed(self) -> None:
        self._dashboard_page.reload()
        self._templates_page.reload()
        self._candidates_page.reload()
        self._export_page.reload()
        self.statusBar().showMessage("Данные обновлены.", 5000)

    def _on_analysis_changed(self) -> None:
        self._dashboard_page.refresh()
        self._export_page.reload()

    def _on_settings_saved(self) -> None:
        self._settings_page.reload()
        self._templates_page.reload_settings()
        self._candidates_page.reload_settings()
        self.statusBar().showMessage("Настройки сохранены.", 5000)

    def closeEvent(self, event: object) -> None:
        self._container.database.close()
        super().closeEvent(event)  # type: ignore[arg-type]
