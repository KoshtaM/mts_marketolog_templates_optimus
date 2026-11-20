"""Экран «Настройки»: параметры анализа, baseline, пороги выгоды и стоимость шаблона."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.ports import SettingsStore
from mts_templates.application.settings import (
    BASELINE_CATALOG,
    BASELINE_OBSERVED,
    AppSettings,
    BenefitThresholds,
)
from mts_templates.domain.analytics.normalization import (
    PUNCTUATION_DELETE,
    PUNCTUATION_KEEP,
    PUNCTUATION_SPACE,
)
from mts_templates.domain.value_objects import Money

BASELINE_ITEMS = (
    (BASELINE_OBSERVED, "Средняя стоимость сегмента обычных SMS × сегменты срабатываний"),
    (BASELINE_CATALOG, "Расчёт по каталогу тарифов"),
)

PUNCTUATION_ITEMS = (
    (PUNCTUATION_DELETE, "Удалять"),
    (PUNCTUATION_SPACE, "Заменять пробелом"),
    (PUNCTUATION_KEEP, "Сохранять"),
)

BENEFIT_LEVEL_TITLES = (
    "Уровень 1 — еле выгоден",
    "Уровень 2 — немного выгоден",
    "Уровень 3 — выгоден",
    "Уровень 4 — очень выгоден",
    "Уровень 5 — супер выгоден",
)


class SettingsPage(QWidget):
    """Позволяет изменить параметры, влияющие на результат анализа."""

    settings_saved = Signal()

    def __init__(
        self,
        *,
        settings_store: SettingsStore,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_store = settings_store
        self._settings = settings

        self._baseline = QComboBox(self)
        for value, title in BASELINE_ITEMS:
            self._baseline.addItem(title, value)

        self._min_segments = QSpinBox(self)
        self._min_segments.setRange(1, 10_000)

        self._min_support = QSpinBox(self)
        self._min_support.setRange(1, 10_000)

        self._min_text = QSpinBox(self)
        self._min_text.setRange(1, 1_000)

        self._max_foreign = QSpinBox(self)
        self._max_foreign.setRange(0, 1_000)

        self._max_w_words = QSpinBox(self)
        self._max_w_words.setRange(1, 20)

        self._max_d_words = QSpinBox(self)
        self._max_d_words.setRange(1, 20)

        self._max_tail_depth = QSpinBox(self)
        self._max_tail_depth.setRange(0, 10)

        self._punctuation = QComboBox(self)
        for value, title in PUNCTUATION_ITEMS:
            self._punctuation.addItem(title, value)

        self._fold_yo = QCheckBox("Свёртывать ё → е при сравнении", self)
        self._sender_case = QCheckBox("Учитывать регистр имени отправителя", self)

        self._fee = QDoubleSpinBox(self)
        self._fee.setRange(0.0, 1_000_000.0)
        self._fee.setSingleStep(100.0)
        self._fee.setDecimals(2)

        self._thresholds = tuple(self._make_threshold_box() for _ in BENEFIT_LEVEL_TITLES)

        self._delivered_only = QCheckBox("Учитывать только доставленные сообщения", self)
        self._data_dir = QLabel(str(settings.data_dir), self)
        self._data_dir.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._save_button = QPushButton("Сохранить настройки", self)

        self._build()
        self._load(settings)

    def _make_threshold_box(self) -> QDoubleSpinBox:
        box = QDoubleSpinBox(self)
        box.setRange(0.0, 10_000_000.0)
        box.setSingleStep(500.0)
        box.setDecimals(2)
        box.setSuffix(" ₽")
        return box

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        analysis_box = QGroupBox("Параметры анализа", self)
        form = QFormLayout(analysis_box)
        form.addRow("Методика baseline", self._baseline)
        form.addRow("Минимум сообщений в группе", self._min_support)
        form.addRow("Минимум сегментов в группе", self._min_segments)
        form.addRow("Минимальная длина постоянного текста", self._min_text)
        form.addRow("Допустимо чужих совпадений", self._max_foreign)
        form.addRow("Максимум слов в %w{1,n}", self._max_w_words)
        form.addRow("Максимум чисел в %d{1,n}", self._max_d_words)
        form.addRow("Глубина хвостового якоря объединения", self._max_tail_depth)
        form.addRow("Пунктуация при сравнении", self._punctuation)
        form.addRow("", self._fold_yo)
        form.addRow("", self._sender_case)
        form.addRow("Стоимость шаблона, ₽/мес", self._fee)
        form.addRow("", self._delivered_only)
        layout.addWidget(analysis_box)

        benefit_box = QGroupBox("Пороги выгоды шаблона, ₽", self)
        benefit_form = QFormLayout(benefit_box)
        for title, box in zip(BENEFIT_LEVEL_TITLES, self._thresholds, strict=True):
            benefit_form.addRow(title, box)
        hint = QLabel(
            "Строки таблицы шаблонов закрашиваются по выгоде: пять зелёных уровней "
            "от порога 1 до порога 5, убыток — слабо-красным.",
            self,
        )
        hint.setWordWrap(True)
        benefit_form.addRow("", hint)
        layout.addWidget(benefit_box)

        paths_box = QGroupBox("Данные", self)
        paths_layout = QFormLayout(paths_box)
        paths_layout.addRow("Каталог данных", self._data_dir)
        hint = QLabel(
            "База SQLite, логи и пользовательские настройки хранятся в каталоге данных. "
            "Сами выгрузки в приложение не копируются.",
            self,
        )
        hint.setWordWrap(True)
        paths_layout.addRow("", hint)
        layout.addWidget(paths_box)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self._save_button)
        layout.addLayout(bottom)
        layout.addStretch(1)

        self._save_button.clicked.connect(self._save)

    def _load(self, settings: AppSettings) -> None:
        self._settings = settings
        index = self._baseline.findData(settings.baseline_mode)
        self._baseline.setCurrentIndex(index if index >= 0 else 0)
        self._min_segments.setValue(settings.min_cluster_segments)
        self._min_support.setValue(settings.min_support)
        self._min_text.setValue(settings.min_text_length)
        self._max_foreign.setValue(settings.max_foreign_matches)
        self._max_w_words.setValue(settings.max_w_words)
        self._max_d_words.setValue(settings.max_d_words)
        self._max_tail_depth.setValue(settings.max_tail_depth)
        self._punctuation.setCurrentIndex(
            max(0, self._punctuation.findData(settings.punctuation_policy))
        )
        self._fold_yo.setChecked(settings.fold_yo)
        self._sender_case.setChecked(settings.sender_case_sensitive)
        self._fee.setValue(float(settings.template_fee.amount))
        for box, level in zip(self._thresholds, settings.benefit_thresholds.levels, strict=True):
            box.setValue(float(level.amount))
        self._delivered_only.setChecked(settings.delivered_only)
        self._data_dir.setText(str(settings.data_dir))

    def reload(self, settings: AppSettings | None = None) -> None:
        """Перечитать настройки из хранилища или применить переданные."""
        if settings is None:
            try:
                settings = self._settings_store.load()
            except Exception as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self._load(settings)

    def _save(self) -> None:
        try:
            levels = [Money(Decimal(str(round(box.value(), 2)))) for box in self._thresholds]
            thresholds = BenefitThresholds(
                level_1=levels[0],
                level_2=levels[1],
                level_3=levels[2],
                level_4=levels[3],
                level_5=levels[4],
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Проверьте пороги", str(exc))
            return

        updated = self._settings.with_overrides(
            baseline_mode=str(self._baseline.currentData()),
            min_support=self._min_support.value(),
            min_cluster_segments=self._min_segments.value(),
            min_text_length=self._min_text.value(),
            max_foreign_matches=self._max_foreign.value(),
            max_w_words=self._max_w_words.value(),
            max_d_words=self._max_d_words.value(),
            max_tail_depth=self._max_tail_depth.value(),
            punctuation_policy=str(self._punctuation.currentData()),
            fold_yo=self._fold_yo.isChecked(),
            sender_case_sensitive=self._sender_case.isChecked(),
            template_fee=Money(Decimal(str(round(self._fee.value(), 2)))),
            delivered_only=self._delivered_only.isChecked(),
            benefit_thresholds=thresholds,
        )
        try:
            self._settings_store.save(updated)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {exc}")
            return
        self._settings = updated
        QMessageBox.information(
            self,
            "Настройки сохранены",
            "Параметры применятся при следующем запуске анализа. "
            "Уже посчитанный анализ будет пересчитан при изменении параметров.",
        )
        self.settings_saved.emit()
