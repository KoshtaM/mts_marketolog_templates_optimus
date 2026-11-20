"""SQLite-репозиторий зарегистрированных шаблонов."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from mts_templates.domain.entities import SmsTemplate
from mts_templates.domain.value_objects import Operator
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.repositories import (
    kopecks_to_money,
    money_to_kopecks,
)

_COLUMNS = (
    "id, name, text, sender, active, monthly_fee_kopecks, operators_json, traffic_type, example"
)


class SqliteTemplateRepository:
    """Хранит шаблоны; импорт идемпотентен по `id`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def list_all(self) -> tuple[SmsTemplate, ...]:
        rows = self._database.fetchall(f"SELECT {_COLUMNS} FROM templates ORDER BY id")
        return tuple(_row_to_template(row) for row in rows)

    def find(self, template_id: str) -> SmsTemplate | None:
        row = self._database.fetchone(
            f"SELECT {_COLUMNS} FROM templates WHERE id = ?",
            (template_id,),
        )
        return None if row is None else _row_to_template(row)

    def count(self) -> int:
        row = self._database.fetchone("SELECT COUNT(*) AS count FROM templates")
        return int(row["count"]) if row else 0

    def count_active(self) -> int:
        row = self._database.fetchone("SELECT COUNT(*) AS count FROM templates WHERE active = 1")
        return int(row["count"]) if row else 0

    def replace_all(self, templates: Sequence[SmsTemplate]) -> tuple[int, int, int]:
        """Заменить набор шаблонов; вернуть `(добавлено, обновлено, удалено)`.

        Шаблоны, которых нет в новой выгрузке, удаляются: иначе сгруппированные
        записи прошлого импорта остались бы в базе и плата за шаблон удвоилась.
        """
        if not templates:
            return 0, 0, 0

        connection = self._database.connect()
        existing = {
            str(row["id"]) for row in connection.execute("SELECT id FROM templates").fetchall()
        }
        incoming = {template.template_id for template in templates}
        removed = sorted(existing - incoming)
        try:
            with connection:
                if removed:
                    connection.executemany(
                        "DELETE FROM templates WHERE id = ?", [(item,) for item in removed]
                    )
                connection.executemany(
                    """
                    INSERT INTO templates (id, name, text, sender, active, monthly_fee_kopecks,
                                           operators_json, traffic_type, example)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        text = excluded.text,
                        sender = excluded.sender,
                        active = excluded.active,
                        monthly_fee_kopecks = excluded.monthly_fee_kopecks,
                        operators_json = excluded.operators_json,
                        traffic_type = excluded.traffic_type,
                        example = excluded.example
                    """,
                    (
                        (
                            template.template_id,
                            template.name,
                            template.text,
                            template.sender,
                            int(template.active),
                            money_to_kopecks(template.monthly_fee),
                            json.dumps(
                                sorted(operator.value for operator in template.operators),
                                ensure_ascii=False,
                            ),
                            template.traffic_type,
                            template.example,
                        )
                        for template in templates
                    ),
                )
        except sqlite3.Error as exc:
            raise RuntimeError(f"Не удалось сохранить шаблоны: {exc}") from exc

        updated = sum(1 for template in templates if template.template_id in existing)
        return len(templates) - updated, updated, len(removed)


def _row_to_template(row: sqlite3.Row) -> SmsTemplate:
    return SmsTemplate(
        template_id=str(row["id"]),
        name=str(row["name"]),
        text=str(row["text"]),
        sender=str(row["sender"]),
        active=bool(row["active"]),
        monthly_fee=kopecks_to_money(int(row["monthly_fee_kopecks"])),
        operators=frozenset(
            Operator.from_raw(str(item)) for item in json.loads(row["operators_json"] or "[]")
        ),
        traffic_type=str(row["traffic_type"]),
        example=str(row["example"]),
    )
