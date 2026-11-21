"""Экран «Настройки»: параметры анализа, внешний вид и данные."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
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
from mts_templates.presentation.desktop.theme_catalog import (
    SYSTEM_THEME,
    THEMES,
    theme_by_id,
)
from mts_templates.presentation.desktop.widgets.theme_card import ThemeCard

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

NAV_TITLES = ("Общие", "Внешний вид", "Дополнительно")
THEME_COLUMNS = 4


class SettingsPage(QWidget):
    """Позволяет изменить параметры анализа и тему оформления."""

    settings_saved = Signal()
    theme_changed = Signal(str)

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
        self._theme_cards: dict[str, ThemeCard] = {}

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
        self._reset_theme_button = QPushButton("Сбросить к системной теме", self)

        self._nav = QListWidget(self)
        self._stack = QStackedWidget(self)

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
        self._build_nav()
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._nav)
        root.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_advanced_page())
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

    def _build_nav(self) -> None:
        self._nav.setObjectName("settingsNav")
        self._nav.setFixedWidth(190)
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        self._nav.setSpacing(2)
        for title in NAV_TITLES:
            item = QListWidgetItem(title)
            item.setSizeHint(QSize(0, 38))
            self._nav.addItem(item)

    def _build_general_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_analysis_box())
        layout.addWidget(self._build_benefit_box())

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(self._save_button)
        layout.addLayout(bottom)
        layout.addStretch(1)

        self._save_button.clicked.connect(self._save)
        return page

    def _build_analysis_box(self) -> QGroupBox:
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
        return analysis_box

    def _build_benefit_box(self) -> QGroupBox:
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
        return benefit_box

    def _build_appearance_page(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Внешний вид", content)
        title.setObjectName("settingsTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Выберите тему оформления. Она применяется сразу и сохраняется автоматически.",
            content,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for index, theme in enumerate(THEMES):
            card = ThemeCard(theme, content)
            card.clicked.connect(self._select_theme)
            self._theme_cards[theme.id] = card
            grid.addWidget(card, index // THEME_COLUMNS, index % THEME_COLUMNS)
        grid.setColumnStretch(THEME_COLUMNS, 1)
        layout.addLayout(grid)

        self._reset_theme_button.clicked.connect(lambda: self._select_theme(SYSTEM_THEME.id))
        reset_row = QHBoxLayout()
        reset_row.addWidget(self._reset_theme_button)
        reset_row.addStretch(1)
        layout.addLayout(reset_row)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_advanced_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        paths_box = QGroupBox("Данные", page)
        paths_layout = QFormLayout(paths_box)
        paths_layout.addRow("Каталог данных", self._data_dir)
        hint = QLabel(
            "База SQLite, логи и пользовательские настройки хранятся в каталоге данных. "
            "Сами выгрузки в приложение не копируются.",
            page,
        )
        hint.setWordWrap(True)
        paths_layout.addRow("", hint)
        layout.addWidget(paths_box)

        about_box = QGroupBox("О программе", page)
        about_layout = QVBoxLayout(about_box)
        about = QLabel(
            "MTS SMS Templates Optimus — анализ SMS-шаблонов, срабатывания и "
            "экономической выгоды для МТС-Маркетолога.",
            page,
        )
        about.setWordWrap(True)
        about_layout.addWidget(about)
        layout.addWidget(about_box)
        layout.addStretch(1)
        return page

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
        self._refresh_theme_cards()

    def _refresh_theme_cards(self) -> None:
        for theme_id, card in self._theme_cards.items():
            card.set_selected(theme_id == self._settings.theme)

    def reload(self, settings: AppSettings | None = None) -> None:
        """Перечитать настройки из хранилища или применить переданные."""
        if settings is None:
            try:
                settings = self._settings_store.load()
            except Exception as exc:
                QMessageBox.critical(self, "Ошибка", str(exc))
                return
        self._load(settings)

    def _select_theme(self, theme_id: str) -> None:
        """Применить тему сразу и сохранить выбор без кнопки «Сохранить»."""
        theme = theme_by_id(theme_id)
        if theme.id == self._settings.theme:
            return
        updated = self._settings.with_overrides(theme=theme.id)
        try:
            self._settings_store.save(updated)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить тему: {exc}")
            self._refresh_theme_cards()
            return
        self._settings = updated
        self._refresh_theme_cards()
        self.theme_changed.emit(theme.id)

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
