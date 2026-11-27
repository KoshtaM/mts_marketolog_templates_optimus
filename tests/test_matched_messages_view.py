"""Тесты колонок окна сообщений шаблона и шаблона-кандидата."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from mts_templates.application.dto import MatchedMessageView
from mts_templates.presentation.desktop.dialogs.matched_messages_dialog import COLUMNS
from mts_templates.presentation.desktop.models.table_model import RowsTableModel
from mts_templates.presentation.desktop.widgets.candidates_page import COLUMNS as CANDIDATE_COLUMNS
from mts_templates.presentation.desktop.widgets.templates_page import COLUMNS as TEMPLATE_COLUMNS

MSK = timezone(timedelta(hours=3))

ROW = MatchedMessageView(
    message_id="T0",
    text="Ваш код 1111",
    segments=1,
    masked_recipient="79*****0000",
    sent_at=datetime(2026, 11, 1, 10, 0, tzinfo=MSK),
    operator="MTS",
    delivery_status="Успешная доставка",
)


def make_model(row: MatchedMessageView) -> RowsTableModel:
    model = RowsTableModel(COLUMNS)
    model.set_rows([row])
    return model


def test_templates_table_has_no_button_column() -> None:
    titles = [column.title for column in TEMPLATE_COLUMNS]

    assert titles[0] == "Шаблон"
    assert "⋯" not in titles


def test_candidates_table_has_no_button_column() -> None:
    titles = [column.title for column in CANDIDATE_COLUMNS]

    assert titles[0] == "Шаблон-кандидат"
    assert "⋯" not in titles


def test_templates_table_layout() -> None:
    titles = [column.title for column in TEMPLATE_COLUMNS]
    widths = {column.title: column.width for column in TEMPLATE_COLUMNS}

    assert titles[-1] == "Отправитель"
    assert set(titles).issuperset({"Достав.", "Срабат.", "% Срабат."})
    assert not set(titles).intersection({"Доставлено", "Срабатываний", "Срабатывание"})
    assert "Дрейф" not in titles
    assert widths["Сообщений"] == 50
    assert widths["Достав."] == 57
    assert widths["Срабат."] == 67
    assert widths["% Срабат."] == 60


def test_column_headers_match_requirements() -> None:
    assert [column.title for column in COLUMNS] == [
        "Сообщение",
        "Длина",
        "Номер",
        "Дата/Время отправки",
        "Оператор",
        "Статус доставки",
    ]


def test_row_values_are_formatted_for_display() -> None:
    model = make_model(ROW)

    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == ROW.text
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "1"
    assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == "79*****0000"
    assert model.data(model.index(0, 3), Qt.ItemDataRole.DisplayRole) == "01.11.2026 10:00"
    assert model.data(model.index(0, 4), Qt.ItemDataRole.DisplayRole) == "MTS"
    assert model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole) == "Успешная доставка"


def test_full_message_text_is_available_in_tooltip() -> None:
    long_text = "Длинный текст " + "сообщения " * 40
    row = replace(ROW, text=long_text)
    model = make_model(row)

    display = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    assert isinstance(display, str)
    assert len(display) < len(long_text)
    assert display.endswith("…")
    assert model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole) == long_text
