"""SQLite-репозиторий прогонов анализа."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from mts_templates.domain.analytics.activity import DaySegments, OperatorTrigger, TemplateMetrics
from mts_templates.domain.analytics.analysis import AnalysisRun, CandidateGroup
from mts_templates.domain.value_objects import Operator, Period
from mts_templates.infrastructure.persistence.sqlite.database import Database
from mts_templates.infrastructure.persistence.sqlite.repositories import (
    kopecks_to_money,
    money_to_kopecks,
)


class SqliteAnalysisRepository:
    """Хранит результаты прогонов; ключ — `batch_id + config_hash`."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def find(self, batch_id: str, config_hash: str) -> AnalysisRun | None:
        row = self._database.fetchone(
            "SELECT * FROM analysis_runs WHERE batch_id = ? AND config_hash = ?",
            (batch_id, config_hash),
        )
        return None if row is None else self._load(row)

    def latest(self, batch_id: str) -> AnalysisRun | None:
        row = self._database.fetchone(
            "SELECT * FROM analysis_runs WHERE batch_id = ? ORDER BY created_at DESC LIMIT 1",
            (batch_id,),
        )
        return None if row is None else self._load(row)

    def invalidate_all(self) -> None:
        """Удалить все прогоны: метрики зависят от набора шаблонов."""
        connection = self._database.connect()
        try:
            with connection:
                connection.execute("DELETE FROM analysis_runs")
        except sqlite3.Error as exc:
            raise RuntimeError(f"Не удалось сбросить кэш анализа: {exc}") from exc

    def save(self, run: AnalysisRun) -> None:
        connection = self._database.connect()
        try:
            with connection:
                connection.execute(
                    "DELETE FROM analysis_runs WHERE batch_id = ? AND config_hash = ?",
                    (run.batch_id, run.config_hash),
                )
                connection.execute(
                    """
                    INSERT INTO analysis_runs (id, batch_id, config_hash, created_at, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.batch_id,
                        run.config_hash,
                        run.created_at.isoformat(),
                        json.dumps(
                            {
                                "period_from": run.period.start.isoformat(),
                                "period_to": run.period.end.isoformat(),
                                "message_count": run.message_count,
                                "matched_message_count": run.matched_message_count,
                                "warnings": list(run.warnings),
                                "operator_triggers": [
                                    {
                                        "template_id": item.template_id,
                                        "operator": item.operator.value,
                                        "listed": item.listed,
                                        "matched_messages": item.matched_messages,
                                        "triggered_messages": item.triggered_messages,
                                        "matched_segments": item.matched_segments,
                                    }
                                    for item in run.operator_triggers
                                ],
                                "daily_segments": _daily_payload(run.daily_segments),
                                "daily_templated_segments": _daily_payload(
                                    run.daily_templated_segments
                                ),
                                "template_daily_segments": {
                                    metrics.template_id: _daily_payload(metrics.daily_segments)
                                    for metrics in run.metrics
                                    if metrics.daily_segments
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO template_metrics
                        (run_id, template_id, active, matched_messages, matched_segments,
                         actual_cost_kopecks, baseline_cost_kopecks, template_fee_kopecks,
                         net_benefit_kopecks, trigger_rate, delivered_messages, unique_recipients,
                         triggered_messages, off_operator_messages)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            run.run_id,
                            metrics.template_id,
                            int(metrics.active),
                            metrics.matched_messages,
                            metrics.matched_segments,
                            money_to_kopecks(metrics.actual_cost),
                            money_to_kopecks(metrics.baseline_cost),
                            money_to_kopecks(metrics.template_fee),
                            money_to_kopecks(metrics.net_benefit),
                            float(metrics.trigger_rate),
                            metrics.delivered_messages,
                            metrics.unique_recipients,
                            metrics.triggered_messages,
                            metrics.off_operator_messages,
                        )
                        for metrics in run.metrics
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO candidate_groups
                        (run_id, group_id, template_text, messages, segments,
                         actual_cost_kopecks, templated_cost_kopecks, monthly_saving_kopecks,
                         template_fee_kopecks, net_monthly_kopecks, confidence, payback_months,
                         coverage, senders_json, operators_json, period_from, period_to,
                         is_partial, examples_json, status, warnings_json, foreign_matches)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            run.run_id,
                            candidate.candidate_id,
                            candidate.template_text,
                            candidate.messages,
                            candidate.segments,
                            money_to_kopecks(candidate.actual_cost),
                            money_to_kopecks(candidate.templated_cost),
                            money_to_kopecks(candidate.monthly_saving),
                            money_to_kopecks(candidate.template_fee),
                            money_to_kopecks(candidate.net_monthly),
                            float(candidate.confidence),
                            float(candidate.payback_months)
                            if candidate.payback_months is not None
                            else None,
                            float(candidate.coverage),
                            json.dumps(list(candidate.senders), ensure_ascii=False),
                            json.dumps(
                                [operator.value for operator in candidate.operators],
                                ensure_ascii=False,
                            ),
                            candidate.period.start.isoformat(),
                            candidate.period.end.isoformat(),
                            int(candidate.is_partial_period),
                            json.dumps(list(candidate.examples), ensure_ascii=False),
                            candidate.status,
                            json.dumps(list(candidate.warnings), ensure_ascii=False),
                            candidate.foreign_matches,
                        )
                        for candidate in run.candidates
                    ),
                )
        except sqlite3.Error as exc:
            raise RuntimeError(f"Не удалось сохранить прогон анализа: {exc}") from exc

    def _load(self, row: sqlite3.Row) -> AnalysisRun:
        payload = json.loads(str(row["payload_json"]))
        period = Period(
            start=datetime.fromisoformat(str(payload["period_from"])),
            end=datetime.fromisoformat(str(payload["period_to"])),
        )
        run_id = str(row["id"])
        template_daily = {
            str(template_id): _day_segments(items)
            for template_id, items in dict(payload.get("template_daily_segments", {})).items()
        }
        metrics = tuple(self._load_metrics(run_id, template_daily))
        candidates = tuple(self._load_candidates(run_id, period))
        return AnalysisRun(
            run_id=run_id,
            batch_id=str(row["batch_id"]),
            config_hash=str(row["config_hash"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            period=period,
            message_count=int(payload.get("message_count", 0)),
            matched_message_count=int(payload.get("matched_message_count", 0)),
            metrics=metrics,
            candidates=candidates,
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            operator_triggers=tuple(
                _operator_trigger(item) for item in payload.get("operator_triggers", [])
            ),
            daily_segments=_day_segments(payload.get("daily_segments", [])),
            daily_templated_segments=_day_segments(payload.get("daily_templated_segments", [])),
        )

    def _load_metrics(
        self,
        run_id: str,
        template_daily: dict[str, tuple[DaySegments, ...]],
    ) -> list[TemplateMetrics]:
        rows = self._database.fetchall(
            """
            SELECT template_id, active, matched_messages, matched_segments,
                   actual_cost_kopecks, baseline_cost_kopecks, template_fee_kopecks,
                   net_benefit_kopecks, trigger_rate, delivered_messages, unique_recipients,
                   triggered_messages, off_operator_messages
            FROM template_metrics
            WHERE run_id = ?
            ORDER BY net_benefit_kopecks DESC, template_id
            """,
            (run_id,),
        )
        return [
            TemplateMetrics(
                template_id=str(row["template_id"]),
                matched_messages=int(row["matched_messages"]),
                matched_segments=int(row["matched_segments"]),
                delivered_messages=int(row["delivered_messages"]),
                unique_recipients=int(row["unique_recipients"]),
                actual_cost=kopecks_to_money(int(row["actual_cost_kopecks"])),
                baseline_cost=kopecks_to_money(int(row["baseline_cost_kopecks"])),
                template_fee=kopecks_to_money(int(row["template_fee_kopecks"])),
                net_benefit=kopecks_to_money(int(row["net_benefit_kopecks"])),
                triggered_messages=int(row["triggered_messages"]),
                off_operator_messages=int(row["off_operator_messages"]),
                trigger_rate=Decimal(str(row["trigger_rate"])),
                active=bool(row["active"]),
                daily_segments=template_daily.get(str(row["template_id"]), ()),
            )
            for row in rows
        ]

    def _load_candidates(self, run_id: str, fallback: Period) -> list[CandidateGroup]:
        rows = self._database.fetchall(
            """
            SELECT group_id, template_text, messages, segments, actual_cost_kopecks,
                   templated_cost_kopecks, monthly_saving_kopecks, template_fee_kopecks,
                   net_monthly_kopecks, confidence, payback_months, coverage,
                   senders_json, operators_json, period_from, period_to, is_partial,
                   examples_json, status, warnings_json, foreign_matches
            FROM candidate_groups
            WHERE run_id = ?
            ORDER BY net_monthly_kopecks DESC, group_id
            """,
            (run_id,),
        )
        return [
            CandidateGroup(
                candidate_id=str(row["group_id"]),
                template_text=str(row["template_text"]),
                messages=int(row["messages"]),
                segments=int(row["segments"]),
                actual_cost=kopecks_to_money(int(row["actual_cost_kopecks"])),
                templated_cost=kopecks_to_money(int(row["templated_cost_kopecks"])),
                monthly_saving=kopecks_to_money(int(row["monthly_saving_kopecks"])),
                template_fee=kopecks_to_money(int(row["template_fee_kopecks"])),
                net_monthly=kopecks_to_money(int(row["net_monthly_kopecks"])),
                payback_months=(
                    Decimal(str(row["payback_months"]))
                    if row["payback_months"] is not None
                    else None
                ),
                confidence=Decimal(str(row["confidence"])),
                coverage=Decimal(str(row["coverage"])),
                senders=tuple(str(item) for item in json.loads(row["senders_json"] or "[]")),
                operators=tuple(
                    Operator.from_raw(str(item))
                    for item in json.loads(row["operators_json"] or "[]")
                ),
                period=_period_from_row(row, fallback),
                is_partial_period=bool(row["is_partial"]),
                examples=tuple(str(item) for item in json.loads(row["examples_json"] or "[]")),
                status=str(row["status"] or "auto_validated"),
                warnings=tuple(str(item) for item in json.loads(row["warnings_json"] or "[]")),
                foreign_matches=int(row["foreign_matches"] or 0),
            )
            for row in rows
        ]


def _daily_payload(daily: tuple[DaySegments, ...]) -> list[dict[str, object]]:
    """Дневной ряд для JSON: только дни с сегментами, по возрастанию даты."""
    return [
        {"day": item.day.isoformat(), "segments": item.segments}
        for item in daily
        if item.segments > 0
    ]


def _day_segments(items: Any) -> tuple[DaySegments, ...]:
    return tuple(
        DaySegments(
            day=date.fromisoformat(str(item["day"])),
            segments=int(item["segments"]),
        )
        for item in items
    )


def _operator_trigger(item: dict[str, Any]) -> OperatorTrigger:
    return OperatorTrigger(
        template_id=str(item["template_id"]),
        operator=Operator.from_raw(str(item["operator"])),
        listed=bool(item["listed"]),
        matched_messages=int(item["matched_messages"]),
        triggered_messages=int(item["triggered_messages"]),
        matched_segments=int(item.get("matched_segments", 0)),
    )


def _period_from_row(row: sqlite3.Row, fallback: Period) -> Period:
    if not row["period_from"] or not row["period_to"]:
        return fallback
    return Period(
        start=datetime.fromisoformat(str(row["period_from"])),
        end=datetime.fromisoformat(str(row["period_to"])),
    )
