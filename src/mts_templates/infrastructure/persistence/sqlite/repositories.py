"""SQLite-репозиторий импорта статистики."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from mts_templates.application.dto import ImportBatch, StoredStatistics
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import Money
from mts_templates.infrastructure.persistence.sqlite.database import Database

KOPECKS = Decimal("100")


def money_to_kopecks(money: Money) -> int:
    return int((money.amount * KOPECKS).to_integral_value(rounding=ROUND_HALF_UP))


def kopecks_to_money(kopecks: int) -> Money:
    return Money(Decimal(kopecks) / KOPECKS)


class SqliteImportRepository:
    """Сохраняет загрузку статистики атомарно."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def find_batch(self, source_sha256: str) -> ImportBatch | None:
        row = self._database.fetchone(
            "SELECT * FROM import_batches WHERE source_sha256 = ?",
            (source_sha256,),
        )
        return None if row is None else _row_to_batch(row)

    def get(self, batch_id: str) -> ImportBatch | None:
        row = self._database.fetchone("SELECT * FROM import_batches WHERE id = ?", (batch_id,))
        return None if row is None else _row_to_batch(row)

    def list_batches(self) -> tuple[ImportBatch, ...]:
        rows = self._database.fetchall("SELECT * FROM import_batches ORDER BY imported_at DESC, id")
        return tuple(_row_to_batch(row) for row in rows)

    def save(self, stored: StoredStatistics) -> None:
        batch = stored.batch
        connection = self._database.connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO import_batches
                        (id, source_path, source_sha256, kind, imported_at, period_from,
                         period_to, row_count, message_count, total_cost_kopecks,
                         status, warnings_json, segment_count, duplicate_message_ids,
                         delivered_rows, partial_delivered_rows, send_error_rows,
                         delivery_error_rows, empty_package_rows)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch.id,
                        batch.source_path,
                        batch.source_sha256,
                        batch.kind,
                        batch.imported_at.isoformat(),
                        batch.period_from.isoformat() if batch.period_from else None,
                        batch.period_to.isoformat() if batch.period_to else None,
                        batch.row_count,
                        batch.message_count,
                        money_to_kopecks(batch.total_cost),
                        batch.status,
                        json.dumps(batch.warnings, ensure_ascii=False),
                        batch.segment_count,
                        batch.duplicate_message_ids,
                        batch.delivered_rows,
                        batch.partial_delivered_rows,
                        batch.send_error_rows,
                        batch.delivery_error_rows,
                        batch.empty_package_rows,
                    ),
                )
                self._insert_messages(connection, batch.id, stored.messages)
        except sqlite3.Error as exc:
            raise RuntimeError(f"Не удалось сохранить импорт: {exc}") from exc

    def _insert_messages(
        self,
        connection: sqlite3.Connection,
        batch_id: str,
        messages: Sequence[SmsMessage],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO messages
                (id, batch_id, sent_at, recipient, operator, sender, text, segments,
                 message_class, cost_kopecks, delivered, package_type,
                 send_status, delivery_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    message.message_id,
                    batch_id,
                    message.sent_at.isoformat(),
                    message.recipient,
                    message.operator.value,
                    message.sender,
                    message.text,
                    message.segments,
                    message.message_class.value,
                    money_to_kopecks(message.cost),
                    int(message.delivered),
                    message.billing_rows[0].package_type if message.billing_rows else None,
                    message.send_status or None,
                    message.delivery_status or None,
                )
                for message in messages
            ),
        )

        billing_rows = [
            (
                message.message_id,
                row.package_type or None,
                money_to_kopecks(row.price_per_segment) if row.price_per_segment else None,
                money_to_kopecks(row.cost),
                row.segments,
            )
            for message in messages
            for row in message.billing_rows
        ]
        if billing_rows:
            connection.executemany(
                """
                INSERT INTO billing_rows
                    (message_id, package_type, price_per_segment_kopecks,
                     cost_kopecks, segments)
                VALUES (?, ?, ?, ?, ?)
                """,
                billing_rows,
            )


def _row_to_batch(row: sqlite3.Row) -> ImportBatch:
    warnings = json.loads(row["warnings_json"] or "[]")
    return ImportBatch(
        id=str(row["id"]),
        source_path=str(row["source_path"]),
        source_sha256=str(row["source_sha256"]),
        kind=str(row["kind"]),
        imported_at=datetime.fromisoformat(str(row["imported_at"])),
        row_count=int(row["row_count"]),
        message_count=int(row["message_count"]),
        total_cost=kopecks_to_money(int(row["total_cost_kopecks"])),
        period_from=_optional_datetime(row["period_from"]),
        period_to=_optional_datetime(row["period_to"]),
        status=str(row["status"]),
        warnings=tuple(str(item) for item in warnings),
        segment_count=int(row["segment_count"] or 0),
        duplicate_message_ids=int(row["duplicate_message_ids"] or 0),
        delivered_rows=int(row["delivered_rows"] or 0),
        partial_delivered_rows=int(row["partial_delivered_rows"] or 0),
        send_error_rows=int(row["send_error_rows"] or 0),
        delivery_error_rows=int(row["delivery_error_rows"] or 0),
        empty_package_rows=int(row["empty_package_rows"] or 0),
    )


def _optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))
