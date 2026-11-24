"""Excel-отчёт по результатам анализа (openpyxl)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from mts_templates.application.dto import (
    AnalysisView,
    ExportReportResult,
    OperatorStatistics,
    ReportBundle,
    SegmentCountBucket,
)
from mts_templates.domain.value_objects import Money

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MONEY_FORMAT = "#,##0.00 ₽"
PERCENT_FORMAT = "0.0%"
DATETIME_FORMAT = "dd.mm.yyyy hh:mm"

BASELINE_LABELS = {
    "observed": ("средняя стоимость сегмента обычных SMS периода × сегменты срабатываний"),
    "catalog": "расчёт по каталогу тарифов",
}

CANDIDATE_STATUS_TITLES = {
    "auto_validated": "Проверен автоматически",
    "needs_human_approval": "Требует подтверждения",
    "warning_saved": "Сохранён с предупреждением",
    "rejected": "Отклонён",
}

TOP_OPERATORS = 5
OTHER_OPERATOR = "Другие"
UNKNOWN_OPERATOR = "Не указан"
EXACT_SEGMENT_LIMIT = 9
TAIL_RANGES = ((10, 19), (20, 49), (50, 99), (100, None))
MAX_CHART_DAYS = 3660
CLASS_COLORS = {"Обычные": "e30611", "Шаблонированные": "0d9488", "Другие": "9ca3af"}
OPERATOR_COLORS = (
    "e30611",
    "1d1d1f",
    "00b956",
    "ffcc00",
    "2563eb",
    "7c3aed",
)


@dataclass(frozen=True, slots=True)
class _ChartBlock:
    """Диапазон служебной таблицы данных для диаграммы."""

    row: int
    first: int
    last: int
    column: int
    columns: int


class ExcelReportWriter:
    """Пишет отчёт: сводка, шаблоны, операторы, кандидаты, предупреждения."""

    def write(self, path: Path, bundle: ReportBundle) -> ExportReportResult:
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Сводка"
        self._write_summary(summary, bundle)
        self._write_templates(workbook.create_sheet("Шаблоны"), bundle)
        self._write_operators(workbook.create_sheet("Операторы"), bundle)
        self._write_candidates(workbook.create_sheet("Кандидаты"), bundle)
        self._write_charts(workbook.create_sheet("Графики"), bundle)
        self._write_warnings(workbook.create_sheet("Предупреждения"), bundle)

        path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(path)
        analysis = bundle.analysis
        return ExportReportResult(
            path=path,
            templates=len(analysis.metrics) if analysis else 0,
            candidates=len(analysis.candidates) if analysis else 0,
        )

    def _write_summary(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        batch = bundle.batch
        statistics = bundle.statistics
        analysis = bundle.analysis

        rows: list[tuple[str, object]] = [
            ("Файл статистики", batch.source_path),
            ("Импортирован", _naive(batch.imported_at)),
            ("Период с", _naive(batch.period_from)),
            ("Период по", _naive(batch.period_to)),
            ("Строк в выгрузке", batch.row_count),
            ("Сообщений", batch.message_count),
            ("SMS-сегментов", statistics.segments),
            ("Стоимость, ₽", float(statistics.cost.rounded().amount)),
            ("Доставлено сообщений", statistics.delivered),
            ("Ошибок отправки (строк)", batch.send_error_rows),
            ("Ошибок доставки (строк)", batch.delivery_error_rows),
            ("Строк без пакета/цены", batch.empty_package_rows),
            ("Обычных сообщений", statistics.ordinary_messages),
            ("Обычных сегментов", statistics.ordinary_segments),
            ("Ставка обычных, ₽/сегмент", _money_or_dash(statistics.ordinary_rate)),
            ("Шаблонированных сообщений", statistics.templated_messages),
            ("Шаблонированных сегментов", statistics.templated_segments),
            ("Ставка шаблонированных, ₽/сегмент", _money_or_dash(statistics.templated_rate)),
            ("Методика baseline", BASELINE_LABELS.get(bundle.baseline_mode, bundle.baseline_mode)),
            (
                "Методика кандидатов",
                "фактическая стоимость группы − средняя стоимость сегмента "
                "шаблонированных SMS × сегменты группы − стоимость шаблона",
            ),
            ("Стоимость шаблона, ₽/мес", float(bundle.template_fee.rounded().amount)),
            ("Отчёт сформирован", _naive(bundle.generated_at)),
        ]

        if analysis is not None:
            rows.extend(
                [
                    ("Подпало под шаблоны (сообщений)", analysis.matched_message_count),
                    (
                        "Срабатываний (тарифицированы как шаблонные)",
                        analysis.triggered_message_count,
                    ),
                    ("Срабатывание, %", analysis.trigger_rate),
                    (
                        "Методика срабатывания",
                        "доля сообщений, подпавших под шаблон по тексту и отправителю, "
                        "оплаченных как шаблонированные; разбивка по операторам — лист «Операторы»",
                    ),
                    ("Всего сообщений в анализе", analysis.message_count),
                    (
                        "Выгода шаблонов за период, ₽",
                        float(analysis.total_net_benefit.rounded().amount),
                    ),
                    (
                        "Выгода шаблонов/мес, ₽",
                        float(analysis.total_monthly_net_benefit.rounded().amount),
                    ),
                    (
                        "Модель месяца",
                        "неполный период масштабируется до 30 дней; полный — без масштабирования",
                    ),
                    ("Неактивных шаблонов", analysis.inactive_templates),
                    ("Кандидатов", len(analysis.candidates)),
                ]
            )
        else:
            rows.append(("Анализ", "не выполнялся"))

        sheet.append(["Показатель", "Значение"])
        for key, value in rows:
            sheet.append([key, value])

        for cell in sheet[1]:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
        sheet.column_dimensions["A"].width = 42
        sheet.column_dimensions["B"].width = 60

        for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row):
            label, value = row
            if label.value in (
                "Стоимость, ₽",
                "Выгода шаблонов за период, ₽",
                "Выгода шаблонов/мес, ₽",
                "Стоимость шаблона, ₽/мес",
            ):
                value.number_format = MONEY_FORMAT
            elif str(label.value).startswith("Ставка"):
                value.number_format = "0.00 ₽"
            elif label.value == "Срабатывание, %":
                value.number_format = "0.0%"
            if label.value in ("Импортирован", "Период с", "Период по", "Отчёт сформирован"):
                value.number_format = DATETIME_FORMAT

    def _write_templates(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        headers = [
            "ID",
            "Текст шаблона",
            "Операторы",
            "Отправитель",
            "Активен",
            "Сообщений",
            "Сегментов",
            "% от всех сегментов",
            "% от шаблонированных",
            "Доставлено",
            "Получателей",
            "Срабатываний",
            "Срабатывание",
            "Вне списка операторов",
            "Стоимость за период, ₽",
            "Без шаблона за период, ₽",
            "Стоимость/мес, ₽",
            "Без шаблона/мес, ₽",
            "Шаблон/мес, ₽",
            "Выгода/мес, ₽",
        ]
        sheet.append(headers)
        analysis = bundle.analysis
        for metrics in analysis.metrics if analysis else ():
            sheet.append(
                [
                    metrics.template_id,
                    metrics.text,
                    ", ".join(metrics.operators) or "все",
                    metrics.sender,
                    "да" if metrics.active else "нет",
                    metrics.matched_messages,
                    metrics.matched_segments,
                    metrics.share_of_all_segments,
                    metrics.share_of_templated_segments,
                    metrics.delivered_messages,
                    metrics.unique_recipients,
                    metrics.triggered_messages,
                    metrics.trigger_rate,
                    metrics.off_operator_messages,
                    float(metrics.actual_cost.rounded().amount),
                    float(metrics.baseline_cost.rounded().amount),
                    float(metrics.monthly_actual_cost.rounded().amount),
                    float(metrics.monthly_baseline_cost.rounded().amount),
                    float(metrics.template_fee.rounded().amount),
                    float(metrics.monthly_net_benefit.rounded().amount),
                ]
            )
        self._style_table(
            sheet,
            percent_columns=(8, 9, 13),
            money_columns=(15, 16, 17, 18, 19, 20),
        )
        if sheet.max_row == 1:
            sheet.append(["Нет данных: сначала импортируйте шаблоны и выполните анализ"])

    def _write_operators(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        headers = [
            "Шаблон",
            "Отправитель",
            "Оператор получателя",
            "Оператор в списке шаблона",
            "Сообщений",
            "Срабатываний",
            "Срабатывание",
            "Сегментов подпало",
            "Доля подпавших сегментов",
        ]
        sheet.append(headers)
        analysis = bundle.analysis
        for item in analysis.operator_triggers if analysis else ():
            sheet.append(
                [
                    item.template_name,
                    item.sender,
                    item.operator,
                    "да" if item.listed else "нет",
                    item.matched_messages,
                    item.triggered_messages,
                    item.trigger_rate,
                    item.matched_segments,
                    item.share,
                ]
            )
        self._style_table(sheet, percent_columns=(7, 9), money_columns=())
        if sheet.max_row == 1:
            sheet.append(["Нет данных: сначала выполните анализ"])

    def _write_candidates(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        headers = [
            "ID",
            "Текст шаблона",
            "Сообщений",
            "Сегментов",
            "Стоимость, ₽",
            "Если шаблон, ₽",
            "Стоимость/мес, ₽",
            "Если шаблон/мес, ₽",
            "Экономия в месяц, ₽",
            "Стоимость шаблона, ₽",
            "Выгода в месяц, ₽",
            "Окупаемость, мес",
            "Уверенность",
            "Покрытие",
            "Отправители",
            "Операторы",
            "Неполный период",
            "Примеры",
            "Статус",
            "Предупреждения",
            "Чужих совпадений",
        ]
        sheet.append(headers)
        analysis = bundle.analysis
        for candidate in analysis.candidates if analysis else ():
            sheet.append(
                [
                    candidate.candidate_id,
                    candidate.template_text,
                    candidate.messages,
                    candidate.segments,
                    float(candidate.actual_cost.rounded().amount),
                    float(candidate.templated_cost.rounded().amount),
                    float(candidate.monthly_actual_cost.rounded().amount),
                    float(candidate.monthly_templated_cost.rounded().amount),
                    float(candidate.monthly_saving.rounded().amount),
                    float(candidate.template_fee.rounded().amount),
                    float(candidate.net_monthly.rounded().amount),
                    candidate.payback_months,
                    candidate.confidence,
                    candidate.coverage,
                    ", ".join(candidate.senders),
                    ", ".join(candidate.operators),
                    "да" if candidate.is_partial_period else "нет",
                    " | ".join(candidate.examples),
                    CANDIDATE_STATUS_TITLES.get(candidate.status, candidate.status),
                    " | ".join(candidate.warnings),
                    candidate.foreign_matches,
                ]
            )
        self._style_table(
            sheet,
            percent_columns=(13, 14),
            money_columns=(5, 6, 7, 8, 9, 10, 11),
        )
        if sheet.max_row == 1:
            sheet.append(["Нет данных: кандидаты не найдены или анализ не выполнялся"])

    def _write_charts(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        """Добавить диаграммы дашборда, шаблонов и кандидатов."""
        statistics = bundle.statistics
        days = self._period_days(bundle)

        classes = self._write_block(
            sheet,
            1,
            1,
            ("Класс", "Сегменты", "Стоимость, ₽"),
            (
                (
                    "Обычные",
                    statistics.ordinary_segments,
                    float(statistics.ordinary_cost.rounded().amount),
                ),
                (
                    "Шаблонированные",
                    statistics.templated_segments,
                    float(statistics.templated_cost.rounded().amount),
                ),
            ),
        )
        row = classes.last + 3

        operator_rows, operator_colors = _operator_chart_rows(bundle.operators)
        operators = self._write_block(
            sheet,
            row,
            1,
            ("Оператор", "Сегменты", "Стоимость, ₽"),
            operator_rows,
        )
        for cell_row in range(operators.first, operators.last + 1):
            sheet.cell(row=cell_row, column=3).number_format = MONEY_FORMAT
        row = operators.last + 3

        daily_headers, daily_values = _daily_operator_rows(bundle, days)
        daily = self._write_block(
            sheet,
            row,
            1,
            ("Дата", *daily_headers),
            tuple((day.isoformat(), *values) for day, values in daily_values),
        )
        row = daily.last + 3

        subscribers = self._write_block(
            sheet,
            row,
            1,
            ("Число сегментов", "Абонентов", "Доля"),
            _distribution_rows(
                bundle.segmentation.subscribers_by_segments if bundle.segmentation else ()
            ),
        )
        row = subscribers.last + 3

        messages = self._write_block(
            sheet,
            row,
            1,
            ("Число сегментов", "Сообщений", "Доля"),
            _distribution_rows(
                bundle.segmentation.messages_by_segments if bundle.segmentation else ()
            ),
        )
        for block in (subscribers, messages):
            for cell_row in range(block.first, block.last + 1):
                sheet.cell(row=cell_row, column=3).number_format = PERCENT_FORMAT
        row = messages.last + 3

        subscriber_operators, subscriber_colors = _subscriber_operator_rows(bundle)
        subscriber_shares = self._write_block(
            sheet,
            row,
            1,
            ("Оператор", "Абонентов", "Доля"),
            subscriber_operators,
        )
        for cell_row in range(subscriber_shares.first, subscriber_shares.last + 1):
            sheet.cell(row=cell_row, column=3).number_format = PERCENT_FORMAT
        row = subscriber_shares.last + 3

        series = self._write_block(
            sheet,
            row,
            1,
            ("Дата", "Все сегменты", "Шаблонированные", "Кандидаты"),
            _daily_series_rows(bundle.analysis, days),
        )

        for column in "ABCDEFGH":
            sheet.column_dimensions[column].width = 18

        class_labels = _block_labels(sheet, classes)
        _add_doughnut(
            sheet,
            classes,
            2,
            "Доли SMS-сегментов",
            "L2",
            tuple(CLASS_COLORS.get(str(label), "9ca3af") for label in class_labels),
        )
        _add_doughnut(
            sheet,
            classes,
            3,
            "Доли расходов",
            "L20",
            tuple(CLASS_COLORS.get(str(label), "9ca3af") for label in class_labels),
            show_percent=False,
        )
        _add_doughnut(
            sheet,
            operators,
            2,
            "Сегменты по операторам",
            "L38",
            operator_colors,
        )
        _add_doughnut(
            sheet,
            operators,
            3,
            "Счёт по операторам",
            "L56",
            operator_colors,
            show_percent=False,
        )
        _add_bar(
            sheet,
            daily,
            tuple(range(2, 2 + len(daily_headers))),
            "SMS-сегменты по дням и операторам получателя",
            "T2",
            stacked=True,
            y_title="SMS-сегментов",
        )
        _add_bar(
            sheet,
            subscribers,
            (2,),
            "Абоненты по числу сегментов",
            "T20",
            y_title="Абонентов",
        )
        _add_bar(
            sheet,
            messages,
            (2,),
            "Сообщения по числу сегментов",
            "T38",
            y_title="Сообщений",
        )
        _add_doughnut(
            sheet,
            subscriber_shares,
            2,
            "Абоненты по операторам",
            "T56",
            subscriber_colors,
        )
        _add_bar(
            sheet,
            series,
            (2, 3),
            "Шаблоны: сегменты по дням",
            "AB2",
            y_title="SMS-сегментов",
        )
        _add_bar(
            sheet,
            series,
            (3, 4),
            "Кандидаты: сегменты по дням",
            "AB20",
            y_title="SMS-сегментов",
        )

    @staticmethod
    def _period_days(bundle: ReportBundle) -> list[date]:
        """Дни периода загрузки, как на оси дневных диаграмм приложения."""
        actual = sorted({item.day for item in bundle.daily_segments})
        start = bundle.batch.period_from.date() if bundle.batch.period_from else None
        end = bundle.batch.period_to.date() if bundle.batch.period_to else None
        if start is None or end is None or end < start or (end - start).days > MAX_CHART_DAYS:
            return actual
        days: list[date] = []
        current = start
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days or actual

    @staticmethod
    def _write_block(
        sheet: Worksheet,
        row: int,
        column: int,
        headers: tuple[str, ...],
        rows: tuple[tuple[object, ...], ...],
    ) -> _ChartBlock:
        for offset, title in enumerate(headers):
            cell = sheet.cell(row=row, column=column + offset, value=title)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
        for offset, values in enumerate(rows, start=1):
            for value_offset, value in enumerate(values):
                sheet.cell(row=row + offset, column=column + value_offset, value=value)
        return _ChartBlock(row, row + 1, row + len(rows), column, len(headers))

    def _write_warnings(self, sheet: Worksheet, bundle: ReportBundle) -> None:
        sheet.append(["Источник", "Предупреждение"])
        for warning in bundle.batch.warnings:
            sheet.append(["Импорт", warning])
        if bundle.analysis is not None:
            for warning in bundle.analysis.warnings:
                sheet.append(["Анализ", warning])
        self._style_table(sheet)
        if sheet.max_row == 1:
            sheet.append(["Предупреждений нет", ""])

    def _style_table(
        self,
        sheet: Worksheet,
        *,
        percent_columns: tuple[int, ...] = (),
        money_columns: tuple[int, ...] = (),
    ) -> None:
        for cell in sheet[1]:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.freeze_panes = "A2"

        for row in sheet.iter_rows(min_row=2):
            for index, cell in enumerate(row, start=1):
                if index in percent_columns:
                    cell.number_format = PERCENT_FORMAT
                elif index in money_columns:
                    cell.number_format = MONEY_FORMAT

        for column in sheet.columns:
            width = max((len(str(cell.value or "")) for cell in column), default=10)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 12), 60)


def _operator_label(name: str) -> str:
    return name or UNKNOWN_OPERATOR


def _block_labels(sheet: Worksheet, block: _ChartBlock) -> tuple[object, ...]:
    return tuple(
        sheet.cell(row=row, column=block.column).value for row in range(block.first, block.last + 1)
    )


def _top_operators(
    operators: tuple[OperatorStatistics, ...],
) -> list[tuple[str, int]]:
    totals: dict[str, int] = defaultdict(int)
    for item in operators:
        totals[_operator_label(item.operator)] += item.segments
    return sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))[:TOP_OPERATORS]


def _operator_chart_rows(
    operators: tuple[OperatorStatistics, ...],
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    top = _top_operators(operators)
    rows: list[tuple[object, ...]] = []
    top_segments = 0.0
    top_cost = 0.0
    for name, segments in top:
        item = next(
            operator for operator in operators if _operator_label(operator.operator) == name
        )
        cost = float(item.cost.rounded().amount)
        rows.append((name, segments, cost))
        top_segments += segments
        top_cost += cost
    rest_segments = sum(item.segments for item in operators) - top_segments
    rest_cost = sum(float(item.cost.rounded().amount) for item in operators) - top_cost
    if rest_segments or rest_cost:
        rows.append((OTHER_OPERATOR, int(rest_segments), rest_cost))
    if not rows:
        rows.append((OTHER_OPERATOR, 0, 0))
    labels = tuple(row[0] for row in rows)
    return tuple(rows), tuple(
        "9ca3af" if label == OTHER_OPERATOR else OPERATOR_COLORS[index % len(OPERATOR_COLORS)]
        for index, label in enumerate(labels)
    )


def _subscriber_operator_rows(
    bundle: ReportBundle,
) -> tuple[tuple[tuple[object, ...], ...], tuple[str, ...]]:
    shares = bundle.segmentation.subscribers_by_operator if bundle.segmentation else ()
    ordered = sorted(shares, key=lambda item: (-item.subscribers, item.operator))
    top = ordered[:TOP_OPERATORS]
    rows: list[tuple[object, ...]] = [
        (item.operator or UNKNOWN_OPERATOR, item.subscribers, item.share) for item in top
    ]
    if len(ordered) > TOP_OPERATORS:
        rest = ordered[TOP_OPERATORS:]
        rows.append(
            (
                OTHER_OPERATOR,
                sum(item.subscribers for item in rest),
                sum(item.share for item in rest),
            )
        )
    if not rows:
        rows.append((OTHER_OPERATOR, 0, 0))
    labels = tuple(row[0] for row in rows)
    return tuple(rows), tuple(
        "9ca3af" if label == OTHER_OPERATOR else OPERATOR_COLORS[index % len(OPERATOR_COLORS)]
        for index, label in enumerate(labels)
    )


def _daily_operator_rows(
    bundle: ReportBundle,
    days: list[date],
) -> tuple[tuple[str, ...], tuple[tuple[date, tuple[int, ...]], ...]]:
    totals: dict[str, int] = defaultdict(int)
    by_day: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in bundle.daily_segments:
        for part in item.operators:
            label = _operator_label(part.operator)
            totals[label] += part.segments
            by_day[item.day][label] += part.segments
    top = sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))[:TOP_OPERATORS]
    labels = [name for name, _ in top]
    top_set = set(labels)
    has_other = any(name not in top_set for name in totals)
    if has_other:
        labels.append(OTHER_OPERATOR)
    if not labels:
        labels.append(OTHER_OPERATOR)

    rows: list[tuple[date, tuple[int, ...]]] = []
    for day in days:
        per_day = by_day.get(day, {})
        values = [per_day.get(label, 0) for label in labels[:TOP_OPERATORS]]
        if has_other:
            values.append(sum(value for name, value in per_day.items() if name not in top_set))
        rows.append((day, tuple(values)))
    if not rows:
        rows.append((date(1970, 1, 1), tuple(0 for _ in labels)))
    return tuple(labels), tuple(rows)


def _daily_series_rows(
    analysis: AnalysisView | None,
    days: list[date],
) -> tuple[tuple[object, ...], ...]:
    totals = {item.day: item.segments for item in analysis.daily_total_segments} if analysis else {}
    templated = (
        {item.day: item.segments for item in analysis.daily_templated_segments} if analysis else {}
    )
    candidates: dict[date, int] = defaultdict(int)
    if analysis:
        for candidate in analysis.candidates:
            for day in candidate.daily_segments:
                candidates[day.day] += day.segments
    rows = tuple(
        (day, totals.get(day, 0), templated.get(day, 0), candidates.get(day, 0)) for day in days
    )
    return rows or ((date(1970, 1, 1), 0, 0, 0),)


def _distribution_rows(buckets: tuple[SegmentCountBucket, ...]) -> tuple[tuple[object, ...], ...]:
    present = {item.segments: item for item in buckets if item.count > 0}
    largest = max(present, default=0)
    rows: list[tuple[object, ...]] = []
    for segments in range(1, min(EXACT_SEGMENT_LIMIT, largest) + 1):
        item = present.get(segments)
        rows.append((str(segments), item.count if item else 0, item.share if item else 0.0))
    for low, high in TAIL_RANGES:
        members = [
            item
            for segments, item in present.items()
            if segments >= low and (high is None or segments <= high)
        ]
        if members:
            label = f"{low}–{high}" if high is not None else f"{low}+"
            rows.append(
                (label, sum(item.count for item in members), sum(item.share for item in members))
            )
    return tuple(rows) or (("Нет данных", 0, 0),)


def _add_doughnut(
    sheet: Worksheet,
    block: _ChartBlock,
    value_column: int,
    title: str,
    anchor: str,
    colors: tuple[str, ...],
    *,
    show_percent: bool = True,
) -> None:
    chart = DoughnutChart()
    chart.title = title
    chart.holeSize = 60
    chart.width = 16
    chart.height = 9
    chart.add_data(
        Reference(sheet, min_col=value_column, min_row=block.row, max_row=block.last),
        titles_from_data=True,
    )
    chart.set_categories(
        Reference(
            sheet,
            min_col=block.column,
            min_row=block.first,
            max_row=block.last,
        )
    )
    chart.series[0].data_points = [
        DataPoint(idx=index, spPr=GraphicalProperties(solidFill=color))
        for index, color in enumerate(colors)
    ]
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showPercent = show_percent
    if not show_percent:
        chart.dataLabels.showVal = True
    sheet.add_chart(chart, anchor)


def _add_bar(
    sheet: Worksheet,
    block: _ChartBlock,
    value_columns: tuple[int, ...],
    title: str,
    anchor: str,
    *,
    stacked: bool = False,
    y_title: str = "",
) -> None:
    chart = BarChart()
    chart.type = "col"
    chart.grouping = "stacked" if stacked else "clustered"
    chart.overlap = 100 if stacked else 0
    chart.title = title
    chart.width = 16
    chart.height = 9
    if y_title:
        chart.y_axis.title = y_title
    for column in value_columns:
        chart.add_data(
            Reference(sheet, min_col=column, min_row=block.row, max_row=block.last),
            titles_from_data=True,
        )
    chart.set_categories(
        Reference(
            sheet,
            min_col=block.column,
            min_row=block.first,
            max_row=block.last,
        )
    )
    sheet.add_chart(chart, anchor)


def _money_or_dash(money: Money | None) -> str:
    return "—" if money is None else f"{money.rounded().amount:.2f}"


def _naive(moment: object) -> object:
    """Excel не принимает timezone-aware datetime."""
    if isinstance(moment, datetime) and moment.tzinfo is not None:
        return moment.replace(tzinfo=None)
    return moment
