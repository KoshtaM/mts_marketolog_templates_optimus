# Паттерны PySide6

Готовые заготовки для слоя `presentation`. Адаптировать под реальные DTO и use cases.

## Composition root

```python
# composition.py
from dataclasses import dataclass

from mts_templates.application.use_cases.analyze_templates import AnalyzeTemplates
from mts_templates.application.use_cases.find_candidates import FindCandidates
from mts_templates.application.use_cases.import_statistics import ImportStatistics
from mts_templates.infrastructure.excel.statistics_reader import StatisticsReader
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.repositories import (
    SqliteAnalysisRepository,
    SqliteMessageRepository,
    SqliteTemplateRepository,
)


@dataclass(frozen=True)
class AppContext:
    import_statistics: ImportStatistics
    analyze_templates: AnalyzeTemplates
    find_candidates: FindCandidates


def build_context(db_path: str) -> AppContext:
    db = Database(db_path)
    db.migrate()
    messages = SqliteMessageRepository(db)
    templates = SqliteTemplateRepository(db)
    analysis = SqliteAnalysisRepository(db)
    reader = StatisticsReader()
    return AppContext(
        import_statistics=ImportStatistics(reader, messages, templates),
        analyze_templates=AnalyzeTemplates(messages, templates, analysis),
        find_candidates=FindCandidates(messages, templates, analysis),
    )
```

## Worker

```python
# presentation/desktop/workers.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(object)
    progress = Signal(int, int, str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, progress=self.signals.progress.emit, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - граница UI
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
```

Запуск:

```python
worker = Worker(context.import_statistics.execute, request)
worker.signals.progress.connect(self.on_progress)
worker.signals.result.connect(self.on_import_done)
worker.signals.error.connect(self.on_error)
QThreadPool.globalInstance().start(worker)
```

## Пагинируемая таблица

```python
# presentation/desktop/models/paged_table_model.py
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class PagedTableModel(QAbstractTableModel):
    def __init__(
        self,
        headers: Sequence[str],
        loader: Callable[[int, int], tuple[list[Sequence[Any]], int]],
        page_size: int = 100,
    ) -> None:
        super().__init__()
        self._headers = list(headers)
        self._loader = loader
        self._page_size = page_size
        self._page = 0
        self._rows: list[Sequence[Any]] = []
        self._total = 0

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._rows[index.row()][index.column()]
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return str(self._page * self._page_size + section + 1)

    def reload(self) -> None:
        self.beginResetModel()
        self._rows, self._total = self._loader(self._page * self._page_size, self._page_size)
        self.endResetModel()

    def set_page(self, page: int) -> None:
        self._page = max(0, page)
        self.reload()

    @property
    def total(self) -> int:
        return self._total
```

`loader` — функция, которая ходит в application use case и возвращает `(rows, total)`. SQL-пагинация: `LIMIT ? OFFSET ?`.

## Закраска строки по значению

Цвет фона всей строки задаётся через `BackgroundRole` и функцию от строки. Настройки цвета читаются из application-настроек, а не хардкодятся в модели.

```python
class RowsTableModel(QAbstractTableModel):
    def __init__(self, columns, *, row_color=None) -> None:
        super().__init__()
        self._row_color = row_color

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.BackgroundRole and self._row_color is not None:
            return self._row_color(self._rows[index.row()])
        return None

    def refresh(self) -> None:
        top = self.index(0, 0)
        bottom = self.index(len(self._rows) - 1, len(self._columns) - 1)
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.BackgroundRole])
```

- Возвращать `QColor` или `None`; `None` — цвет по умолчанию.
- После изменения настроек вызывать `refresh()`, а не пересчитывать анализ.
- Логику уровней держать в отдельном модуле без Qt (возвращает имя цвета), `QColor` создавать в виджете.
- Кандидаты красятся теми же порогами, что и шаблоны, но по `net_monthly` —
  цвет считается по модели месяца, а фактические суммы периода показываются
  отдельными колонками.

## Галочка и крестик вместо «да/нет»

```python
# formatting.py
def format_bool_icon(value: bool) -> str:
    return "✔" if value else "✘"

# table_model.py
if isinstance(value, bool):
    return format_bool_icon(value)          # DisplayRole
if role == Qt.ItemDataRole.ForegroundRole and isinstance(value, bool):
    return QColor("#1b7f3a" if value else "#c0392b")
```

- Один форматтер и один `ForegroundRole` на все булевы колонки: не заводить
  отдельный делегат на каждую таблицу.
- `TextAlignmentRole` для булевых значений — по центру, чтобы иконка не липла
  к краю.
- HTML в `QTableView` не рендерится, иконки-эмодзи в `QIcon` не нужны.

## Связанные таблицы по выделению

```python
def operator_rows_for_template(template_id, rows):
    if template_id is None:
        return ()
    return tuple(row for row in rows if row.template_id == template_id)

# в странице
self._table.selectionModel().currentRowChanged.connect(self._selection_changed)

def _selection_changed(self, current, _previous):
    index = self._proxy.mapToSource(current)
    item = self._model.row_at(index.row()) if index.isValid() else None
    self._operator_model.set_rows(operator_rows_for_template(
        item.template_id if item else None, self._operator_triggers))
```

- Фильтровать исходные DTO до `set_rows`, а не прятать строки в прокси: иначе
  счётчики и заголовки расходятся с тем, что видно.
- После перезаполнения модели выделение сбрасывается — выделять первую строку
  (`selectRow(0)`) или очищать связанную таблицу.
- Фильтр основной таблицы не применять к связанной: она уже ограничена
  выделением.

## Делегат для денег

```python
from decimal import Decimal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyledItemDelegate

class MoneyDelegate(QStyledItemDelegate):
    def displayText(self, value, locale) -> str:
        if value is None or value == "":
            return ""
        amount = Decimal(str(value))
        return f"{amount:,.2f} ₽".replace(",", " ").replace(".", ",")
```

## Ошибки

```python
def on_error(self, exc: Exception) -> None:
    logger.exception("UI operation failed")
    QMessageBox.critical(
        self,
        "Ошибка",
        "Не удалось выполнить операцию.\n"
        f"Код: {getattr(exc, 'code', 'unknown')}\n"
        "Подробности — в журнале приложения.",
    )
```

Не показывать traceback и PII. В лог — тип ошибки, код, контекст без телефонов/текстов.

## Настройки

```python
# infrastructure/config.py
from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


def user_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "MtsTemplates"


@dataclass(frozen=True)
class Settings:
    baseline_model: str = "observed"
    template_fee_rub: str = "2000.00"
    min_segments: int = 5
    cluster_eps: float = 0.15


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return Settings(**data.get("analysis", {}))
```

## pytest-qt smoke test

```python
def test_main_window_opens(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    window = MainWindow(build_context(str(tmp_path / "test.db")))
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible()
    assert window.tabs.count() >= 1
```

## Правила

- Не блокировать GUI-поток.
- Не передавать виджеты в worker.
- Не строить SQL в виджетах.
- Не хранить бизнес-логику в view model: view model только готовит DTO и команды.
- Все деньги — `Decimal`; форматирование — в UI.
- Все длительные операции — с прогрессом и отменой.
- Все пользовательские ошибки — по-русски и без stack trace.
