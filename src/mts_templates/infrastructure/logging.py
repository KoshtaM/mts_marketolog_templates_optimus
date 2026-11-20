"""Логирование приложения: файл с ротацией в каталоге данных, без PII."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "mts-templates.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> Path:
    """Настроить корневой логгер и вернуть путь к файлу лога."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / LOG_FILE_NAME

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_mts_handler", False):
            root.removeHandler(handler)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(FORMAT))
    file_handler._mts_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    return log_path
