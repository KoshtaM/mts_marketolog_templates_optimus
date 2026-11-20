"""Интеграционный тест: xlsx → SQLite → отчёт."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mts_templates.application.dto import ImportStatisticsRequest
from mts_templates.composition import build_container
from mts_templates.domain.errors import OperationCancelled, StatisticsImportError
from tests.fixtures import STATISTICS_HEADERS, write_statistics_xlsx

TEMPLATED_PACKAGE = "Подписка. Все операторы (шаблонированный)"
ORDINARY_PACKAGE = "Подписка. Все операторы"


def sample_rows() -> list[dict[str, object]]:
    base = {
        "Имя отправителя": "TEST",
        "Номер получателя": "79000000000",
        "Оператор получателя": "MTS",
        "Дата попытки отправки": "2026-11-05T12:00:00+03:00",
        "Статус отправки": "Отправлено",
        "Статус доставки СМС или ММС": "Успешная доставка",
        "Канал": "SMS",
        "Количество sms в пакете при покупке": 999999999,
    }
    return [
        {
            **base,
            "ID сообщения": "A",
            "Текст сообщения": "Код 1234",
            "Цена за один сегмент": 11,
            "Стоимость": 0,
            "Количество сегментов в sms": 1,
            "Тип пакета": TEMPLATED_PACKAGE,
        },
        {
            **base,
            "ID сообщения": "A",
            "Текст сообщения": "Код 1234",
            "Цена за один сегмент": 35,
            "Стоимость": 35,
            "Количество сегментов в sms": 1,
            "Тип пакета": TEMPLATED_PACKAGE,
        },
        {
            **base,
            "ID сообщения": "B",
            "Текст сообщения": "Оплата получена",
            "Цена за один сегмент": 9.6,
            "Стоимость": 19.2,
            "Количество сегментов в sms": 2,
            "Тип пакета": ORDINARY_PACKAGE,
        },
        {
            **base,
            "ID сообщения": "C",
            "Текст сообщения": "",
            "Цена за один сегмент": None,
            "Стоимость": None,
            "Количество сегментов в sms": 0,
            "Тип пакета": None,
            "Статус отправки": "Ошибка отправки",
            "Статус доставки СМС или ММС": None,
        },
    ]


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


def test_import_statistics_end_to_end(tmp_path: Path, database_path: Path) -> None:
    source = write_statistics_xlsx(tmp_path / "statistics.xlsx", sample_rows())
    container = build_container(database_path)

    report = container.import_statistics.execute(ImportStatisticsRequest(path=source))

    assert report.reused is False
    assert report.batch.row_count == 4
    assert report.batch.message_count == 3
    assert report.batch.total_cost.rounded().amount == Decimal("54.20")
    assert report.duplicate_message_ids == 1
    assert report.segment_count == 4
    assert report.delivered_rows == 3
    assert report.partial_delivered_rows == 0
    assert report.send_error_rows == 1
    assert report.delivery_error_rows == 0
    assert report.empty_package_rows == 1
    assert report.issues == ()
    assert report.has_issues is True

    messages = container.database.fetchall(
        "SELECT id, cost_kopecks, segments FROM messages ORDER BY id"
    )
    assert [(row["id"], row["cost_kopecks"], row["segments"]) for row in messages] == [
        ("A", 3500, 2),
        ("B", 1920, 2),
        ("C", 0, 0),
    ]

    billing = container.database.fetchall(
        "SELECT message_id, cost_kopecks FROM billing_rows ORDER BY id"
    )
    assert [(row["message_id"], row["cost_kopecks"]) for row in billing] == [
        ("A", 0),
        ("A", 3500),
        ("B", 1920),
        ("C", 0),
    ]
    container.database.close()


def test_repeated_import_is_idempotent(tmp_path: Path, database_path: Path) -> None:
    source = write_statistics_xlsx(tmp_path / "statistics.xlsx", sample_rows())
    container = build_container(database_path)

    first = container.import_statistics.execute(ImportStatisticsRequest(path=source))
    second = container.import_statistics.execute(ImportStatisticsRequest(path=source))

    assert second.reused is True
    assert second.batch.id == first.batch.id
    assert container.database.fetchone("SELECT COUNT(*) AS count FROM import_batches")["count"] == 1
    container.database.close()


def test_missing_required_column_fails_fast(tmp_path: Path, database_path: Path) -> None:
    headers = [column for column in STATISTICS_HEADERS if column != "Стоимость"]
    source = write_statistics_xlsx(tmp_path / "broken.xlsx", sample_rows(), headers=headers)
    container = build_container(database_path)

    with pytest.raises(StatisticsImportError, match="Стоимость"):
        container.import_statistics.execute(ImportStatisticsRequest(path=source))

    assert container.database.fetchone("SELECT COUNT(*) AS count FROM import_batches")["count"] == 0
    container.database.close()


def test_header_order_does_not_matter(tmp_path: Path, database_path: Path) -> None:
    headers = tuple(reversed(STATISTICS_HEADERS))
    source = write_statistics_xlsx(tmp_path / "reordered.xlsx", sample_rows(), headers=headers)
    container = build_container(database_path)

    report = container.import_statistics.execute(ImportStatisticsRequest(path=source))

    assert report.batch.message_count == 3
    container.database.close()


def test_import_can_be_cancelled(tmp_path: Path, database_path: Path) -> None:
    source = write_statistics_xlsx(tmp_path / "statistics.xlsx", sample_rows())
    container = build_container(database_path)

    with pytest.raises(OperationCancelled):
        container.import_statistics.execute(
            ImportStatisticsRequest(path=source), should_cancel=lambda: True
        )

    assert container.database.fetchone("SELECT COUNT(*) AS count FROM import_batches")["count"] == 0
    container.database.close()


def test_naive_dates_get_msk_offset(tmp_path: Path, database_path: Path) -> None:
    rows = sample_rows()
    rows[2]["Дата попытки отправки"] = "2026-11-05 12:00:00"
    source = write_statistics_xlsx(tmp_path / "naive.xlsx", rows)
    container = build_container(database_path)

    report = container.import_statistics.execute(ImportStatisticsRequest(path=source))

    assert any("+03:00" in warning for warning in report.batch.warnings)
    container.database.close()
