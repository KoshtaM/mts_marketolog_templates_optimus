"""Фоновые задачи: длительные операции не блокируют UI."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mts_templates.domain.errors import OperationCancelled

logger = logging.getLogger(__name__)

CANCELLED_MESSAGE = "Операция отменена пользователем."


class CancelToken:
    """Флаг отмены, который проверяют use cases во время длительной работы."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class TaskSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    """Выполняет функцию в пуле потоков и отдаёт результат через сигналы."""

    def __init__(self, operation: Callable[[CancelToken], Any], token: CancelToken) -> None:
        super().__init__()
        self._operation = operation
        self._token = token
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._operation(self._token)
        except OperationCancelled:
            logger.info("Фоновая операция отменена")
            self.signals.failed.emit(CANCELLED_MESSAGE)
            return
        except Exception as exc:  # любая ошибка должна дойти до UI
            logger.exception("Фоновая операция завершилась ошибкой")
            self.signals.failed.emit(str(exc))
            return
        self.signals.succeeded.emit(result)


class BackgroundRunner(QObject):
    """Запускает задачи, держит их живыми и умеет отменять."""

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tasks: set[Task] = set()
        self._tokens: set[CancelToken] = set()

    def run(
        self,
        operation: Callable[[CancelToken], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[str], None],
    ) -> None:
        token = CancelToken()
        task = Task(operation, token)
        self._tasks.add(task)
        self._tokens.add(token)
        task.signals.succeeded.connect(on_success)
        task.signals.failed.connect(on_error)
        task.signals.succeeded.connect(lambda _: self._finish(task, token))
        task.signals.failed.connect(lambda _: self._finish(task, token))
        self.busy_changed.emit(True)
        QThreadPool.globalInstance().start(task)

    def cancel(self) -> None:
        """Попросить все активные операции остановиться на ближайшей проверке."""
        for token in list(self._tokens):
            token.cancel()

    def _finish(self, task: Task, token: CancelToken) -> None:
        self._tasks.discard(task)
        self._tokens.discard(token)
        if not self._tasks:
            self.busy_changed.emit(False)
