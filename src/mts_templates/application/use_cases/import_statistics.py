"""Use case: импорт Excel-выгрузки статистики."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from mts_templates.application.dto import (
    ImportBatch,
    ImportReport,
    ImportStatisticsRequest,
    StoredStatistics,
)
from mts_templates.application.ports import ImportRepository, StatisticsReader
from mts_templates.domain.analytics.import_aggregation import (
    DELIVERY_ERROR_STATUS,
    PARTIAL_DELIVERY_STATUS,
    SEND_ERROR_STATUS,
    RawSmsRow,
    aggregate_rows,
)
from mts_templates.domain.errors import OperationCancelled, StatisticsImportError
from mts_templates.domain.value_objects import Money

STATISTICS_KIND = "statistics"
BATCH_STATUS_OK = "ok"
CANCEL_CHECK_EVERY = 5_000

DUPLICATES_WARNING = (
    "В выгрузке есть повторяющиеся ID сообщения: стоимость просуммирована, "
    "сообщение посчитано один раз."
)
EMPTY_PACKAGE_WARNING = (
    "Есть строки без типа пакета и цены (ошибки отправки): исключены из экономики."
)


class ImportStatistics:
    """Идемпотентный импорт статистики по SHA-256 файла."""

    def __init__(
        self,
        reader: StatisticsReader,
        repository: ImportRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._reader = reader
        self._repository = repository
        self._clock = clock

    def execute(
        self,
        request: ImportStatisticsRequest,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ImportReport:
        path = request.path
        if not path.is_file():
            raise StatisticsImportError(f"Файл не найден: {path}")

        _raise_if_cancelled(should_cancel)
        digest = file_sha256(path)
        existing = self._repository.find_batch(digest)
        if existing is not None:
            return _report_from_batch(existing, reused=True)

        warnings: list[str] = []
        rows: list[RawSmsRow] = []
        for index, row in enumerate(self._reader.read(path, warnings), start=1):
            rows.append(row)
            if should_cancel is not None and index % CANCEL_CHECK_EVERY == 0:
                _raise_if_cancelled(should_cancel)
        if not rows:
            raise StatisticsImportError("В файле нет строк со статистикой")

        _raise_if_cancelled(should_cancel)
        aggregation = aggregate_rows(rows)
        messages = aggregation.messages
        total_cost = sum((message.cost for message in messages), Money.zero())
        duplicate_ids = aggregation.duplicate_message_ids

        empty_package_rows = sum(
            1 for row in rows if row.package_type is None and row.price_per_segment is None
        )
        if duplicate_ids:
            warnings.append(DUPLICATES_WARNING)
        if empty_package_rows:
            warnings.append(EMPTY_PACKAGE_WARNING)

        sent_at_list = [row.sent_at for row in rows]
        batch = ImportBatch(
            id=str(uuid.uuid4()),
            source_path=str(path),
            source_sha256=digest,
            kind=STATISTICS_KIND,
            imported_at=self._clock(),
            row_count=len(rows),
            message_count=len(messages),
            total_cost=total_cost,
            period_from=min(sent_at_list),
            period_to=max(sent_at_list),
            status=BATCH_STATUS_OK,
            warnings=tuple(warnings),
            segment_count=sum(message.segments for message in messages),
            duplicate_message_ids=duplicate_ids,
            delivered_rows=sum(1 for row in rows if row.delivered),
            partial_delivered_rows=sum(
                1 for row in rows if row.delivery_status == PARTIAL_DELIVERY_STATUS
            ),
            send_error_rows=sum(1 for row in rows if row.send_status == SEND_ERROR_STATUS),
            delivery_error_rows=sum(
                1 for row in rows if row.delivery_status == DELIVERY_ERROR_STATUS
            ),
            empty_package_rows=empty_package_rows,
        )
        self._repository.save(StoredStatistics(batch=batch, messages=messages))

        return ImportReport(
            batch=batch,
            reused=False,
            duplicate_message_ids=batch.duplicate_message_ids,
            segment_count=batch.segment_count,
            delivered_rows=batch.delivered_rows,
            partial_delivered_rows=batch.partial_delivered_rows,
            send_error_rows=batch.send_error_rows,
            delivery_error_rows=batch.delivery_error_rows,
            empty_package_rows=batch.empty_package_rows,
            issues=aggregation.issues,
        )


def _raise_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise OperationCancelled("Операция отменена пользователем")


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _report_from_batch(batch: ImportBatch, *, reused: bool) -> ImportReport:
    return ImportReport(
        batch=batch,
        reused=reused,
        duplicate_message_ids=batch.duplicate_message_ids,
        segment_count=batch.segment_count,
        delivered_rows=batch.delivered_rows,
        partial_delivered_rows=batch.partial_delivered_rows,
        send_error_rows=batch.send_error_rows,
        delivery_error_rows=batch.delivery_error_rows,
        empty_package_rows=batch.empty_package_rows,
        issues=(),
    )
