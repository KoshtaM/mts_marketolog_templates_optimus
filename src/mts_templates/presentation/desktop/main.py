"""Точка входа десктопного приложения."""

from __future__ import annotations

import logging
import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from mts_templates.composition import build_container
from mts_templates.infrastructure.config import load_settings
from mts_templates.infrastructure.logging import setup_logging
from mts_templates.presentation.desktop.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    """Запустить приложение и вернуть код выхода."""
    settings = load_settings()
    setup_logging(settings.logs_dir)
    logger.info("Запуск приложения, каталог данных: %s", settings.data_dir)

    app = QApplication(sys.argv)
    app.setApplicationName("MTS SMS Templates Optimus")
    app.setOrganizationName("MtsTemplates")

    try:
        container = build_container(settings=settings)
    except Exception as exc:
        logger.exception("Не удалось инициализировать приложение")
        QMessageBox.critical(
            None,
            "Ошибка запуска",
            f"Не удалось открыть базу данных или конфигурацию:\n{exc}",
        )
        return 1

    window = MainWindow(container)
    window.show()

    try:
        return int(app.exec())
    except Exception:
        logger.exception("Непредвиденная ошибка приложения")
        traceback.print_exc()
        return 1
    finally:
        container.database.close()


if __name__ == "__main__":
    sys.exit(main())
