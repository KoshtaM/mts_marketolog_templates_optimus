"""SQLite-запросы по сообщениям: потоковая выгрузка и агрегаты."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime

from mts_templates.application.dto import (
    BatchStatistics,
    OperatorStatistics,
    SegmentationStatistics,
    SegmentCountBucket,
    SubscriberOperatorShare,
)
from mts_templates.domain.entities import SmsMessage
from mts_templates.domain.value_objects import MessageClass, Money, Operator
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.repositories import kopecks_to_money

_MESSAGE_COLUMNS = (
    "id, sent_at, recipient, operator, sender, text, segments, message_class, "
    "cost_kopecks, delivered"
)


class SqliteMessageQueryRepository:
    """Чтение сообщений батча без загрузки всего файла в память."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def iter_messages(self, batch_id: str) -> Iterator[SmsMessage]:
        cursor = self._database.connect().execute(
            f"SELECT {_MESSAGE_COLUMNS} FROM messages WHERE batch_id = ? ORDER BY sent_at, id",
            (batch_id,),
        )
        for row in cursor:
            yield _row_to_message(row)

    def statistics(self, batch_id: str) -> BatchStatistics:
        totals = self._database.fetchone(
            """
            SELECT COUNT(*) AS messages,
                   COALESCE(SUM(segments), 0) AS segments,
                   COALESCE(SUM(cost_kopecks), 0) AS cost,
                   COALESCE(SUM(delivered), 0) AS delivered,
                   COUNT(DISTINCT sender) AS senders
            FROM messages
            WHERE batch_id = ?
            """,
            (batch_id,),
        )
        if totals is None:
            raise LookupError(f"Нет сообщений для загрузки {batch_id}")

        by_class = {
            str(row["message_class"]): row
            for row in self._database.fetchall(
                """
                SELECT message_class,
                       COUNT(*) AS messages,
                       COALESCE(SUM(segments), 0) AS segments,
                       COALESCE(SUM(cost_kopecks), 0) AS cost
                FROM messages
                WHERE batch_id = ?
                GROUP BY message_class
                """,
                (batch_id,),
            )
        }

        ordinary = by_class.get(MessageClass.ORDINARY.value)
        templated = by_class.get(MessageClass.TEMPLATED.value)

        return BatchStatistics(
            message_count=int(totals["messages"]),
            segments=int(totals["segments"]),
            cost=kopecks_to_money(int(totals["cost"])),
            delivered=int(totals["delivered"]),
            ordinary_messages=_int(ordinary, "messages"),
            ordinary_segments=_int(ordinary, "segments"),
            ordinary_cost=kopecks_to_money(_int(ordinary, "cost")),
            ordinary_rate=_rate(ordinary),
            templated_messages=_int(templated, "messages"),
            templated_segments=_int(templated, "segments"),
            templated_cost=kopecks_to_money(_int(templated, "cost")),
            templated_rate=_rate(templated),
            senders=int(totals["senders"]),
        )

    def operator_statistics(self, batch_id: str) -> tuple[OperatorStatistics, ...]:
        """Сообщения, сегменты и счёт по операторам получателя."""
        rows = self._database.fetchall(
            """
            SELECT operator,
                   COUNT(*) AS messages,
                   COALESCE(SUM(segments), 0) AS segments,
                   COALESCE(SUM(cost_kopecks), 0) AS cost
            FROM messages
            WHERE batch_id = ?
            GROUP BY operator
            ORDER BY messages DESC, operator
            """,
            (batch_id,),
        )
        return tuple(
            OperatorStatistics(
                operator=str(row["operator"]),
                messages=int(row["messages"]),
                segments=int(row["segments"]),
                cost=kopecks_to_money(int(row["cost"])),
            )
            for row in rows
        )

    def segmentation_statistics(self, batch_id: str) -> SegmentationStatistics:
        """Уникальные абоненты и распределения по числу SMS-сегментов.

        Абоненту приписывается оператор, по которому у него больше всего
        сообщений: иначе один номер попал бы в несколько групп и сумма
        по операторам не совпала бы с общим числом абонентов.
        """
        totals = self._database.fetchone(
            """
            SELECT COUNT(DISTINCT recipient) AS subscribers,
                   COALESCE(SUM(segments), 0) AS segments,
                   COUNT(*) AS messages
            FROM messages
            WHERE batch_id = ? AND segments > 0
            """,
            (batch_id,),
        )
        if totals is None:
            raise LookupError(f"Нет сообщений для загрузки {batch_id}")
        subscribers = int(totals["subscribers"])
        subscriber_segments = int(totals["segments"])
        subscriber_messages = int(totals["messages"])

        subscriber_buckets = self._database.fetchall(
            """
            WITH subscriber_segments AS (
                SELECT recipient, SUM(segments) AS segments
                FROM messages
                WHERE batch_id = ? AND segments > 0
                GROUP BY recipient
            )
            SELECT segments, COUNT(*) AS count
            FROM subscriber_segments
            GROUP BY segments
            ORDER BY segments
            """,
            (batch_id,),
        )
        operator_rows = self._database.fetchall(
            """
            WITH subscriber_operators AS (
                SELECT recipient, operator, COUNT(*) AS messages
                FROM messages
                WHERE batch_id = ? AND segments > 0
                GROUP BY recipient, operator
            ),
            ranked AS (
                SELECT operator,
                       ROW_NUMBER() OVER (
                           PARTITION BY recipient ORDER BY messages DESC, operator ASC
                       ) AS position
                FROM subscriber_operators
            )
            SELECT operator, COUNT(*) AS subscribers
            FROM ranked
            WHERE position = 1
            GROUP BY operator
            ORDER BY subscribers DESC, operator
            """,
            (batch_id,),
        )
        message_buckets = self._database.fetchall(
            """
            SELECT segments, COUNT(*) AS count
            FROM messages
            WHERE batch_id = ? AND segments > 0
            GROUP BY segments
            ORDER BY segments
            """,
            (batch_id,),
        )
        zero_segment_row = self._database.fetchone(
            "SELECT COUNT(*) AS count FROM messages WHERE batch_id = ? AND segments = 0",
            (batch_id,),
        )

        return SegmentationStatistics(
            subscribers=subscribers,
            subscriber_segments=subscriber_segments,
            subscriber_messages=subscriber_messages,
            subscribers_by_segments=_buckets(subscriber_buckets, subscribers),
            subscribers_by_operator=tuple(
                SubscriberOperatorShare(
                    operator=str(row["operator"]),
                    subscribers=int(row["subscribers"]),
                    share=_share(int(row["subscribers"]), subscribers),
                )
                for row in operator_rows
            ),
            messages_by_segments=_buckets(message_buckets, subscriber_messages),
            zero_segment_messages=int(zero_segment_row["count"]) if zero_segment_row else 0,
        )


def _row_to_message(row: sqlite3.Row) -> SmsMessage:
    return SmsMessage(
        message_id=str(row["id"]),
        sent_at=datetime.fromisoformat(str(row["sent_at"])),
        recipient=str(row["recipient"]),
        operator=Operator.from_raw(str(row["operator"])),
        sender=str(row["sender"]),
        text=str(row["text"]),
        segments=int(row["segments"]),
        message_class=MessageClass(str(row["message_class"])),
        cost=kopecks_to_money(int(row["cost_kopecks"])),
        delivered=bool(row["delivered"]),
    )


def _int(row: sqlite3.Row | None, key: str) -> int:
    if row is None:
        return 0
    return int(row[key])


def _share(value: int, total: int) -> float:
    return value / total if total else 0.0


def _buckets(rows: list[sqlite3.Row], total: int) -> tuple[SegmentCountBucket, ...]:
    return tuple(
        SegmentCountBucket(
            segments=int(row["segments"]),
            count=int(row["count"]),
            share=_share(int(row["count"]), total),
        )
        for row in rows
    )


def _rate(row: sqlite3.Row | None) -> Money | None:
    if row is None:
        return None
    segments = int(row["segments"])
    if segments <= 0:
        return None
    return kopecks_to_money(int(row["cost"])) / segments
