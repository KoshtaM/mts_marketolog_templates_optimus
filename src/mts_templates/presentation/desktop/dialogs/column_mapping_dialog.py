"""Диалог сопоставления колонок файла шаблонов."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from mts_templates.application.dto import TemplateColumnMapping, TemplateFilePreview

NO_COLUMN = "— нет —"


class ColumnMappingDialog(QDialog):
    """Позволяет выбрать, какая колонка Excel чем является."""

    def __init__(self, preview: TemplateFilePreview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сопоставление колонок шаблонов")
        self.resize(520, 360)
        self._preview = preview
        self._combos: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Укажите колонки файла. Обязательна только колонка с текстом шаблона; "
            "остальные можно не выбирать."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.addRow("Текст шаблона *", self._combo("text", required=True))
        form.addRow("ID шаблона", self._combo("template_id"))
        form.addRow("Название", self._combo("name"))
        form.addRow("Имя отправителя", self._combo("sender"))
        form.addRow("Статус", self._combo("active"))
        form.addRow("Стоимость, ₽/мес", self._combo("monthly_fee"))
        form.addRow("Операторы", self._combo("operators"))
        form.addRow("Пример текста", self._combo("example"))
        form.addRow("Тип трафика", self._combo("traffic_type"))
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _combo(self, field: str, *, required: bool = False) -> QComboBox:
        combo = QComboBox(self)
        if not required:
            combo.addItem(NO_COLUMN, None)
        for column in self._preview.columns:
            combo.addItem(column, column)
            if self._preview.sample_rows:
                sample = self._preview.sample_rows[0].get(column, "")
                combo.setItemData(combo.count() - 1, sample, 3)
        suggested = self._preview.suggested
        preset = getattr(suggested, field) if suggested is not None else None
        if preset:
            index = combo.findData(preset)
            if index >= 0:
                combo.setCurrentIndex(index)
        self._combos[field] = combo
        return combo

    def mapping(self) -> TemplateColumnMapping:
        return TemplateColumnMapping(
            text=str(self._combos["text"].currentData()),
            template_id=_optional(self._combos["template_id"]),
            name=_optional(self._combos["name"]),
            sender=_optional(self._combos["sender"]),
            active=_optional(self._combos["active"]),
            monthly_fee=_optional(self._combos["monthly_fee"]),
            operators=_optional(self._combos["operators"]),
            example=_optional(self._combos["example"]),
            traffic_type=_optional(self._combos["traffic_type"]),
        )


def _optional(combo: QComboBox) -> str | None:
    value = combo.currentData()
    return None if value is None else str(value)
