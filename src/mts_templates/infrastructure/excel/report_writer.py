"""Excel-отчёт по результатам анализа (openpyxl)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from mts_templates.application.dto import ExportReportResult, ReportBundle
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
            percent_columns=(11,),
            money_columns=(13, 14, 15, 16, 17, 18),
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


def _money_or_dash(money: Money | None) -> str:
    return "—" if money is None else f"{money.rounded().amount:.2f}"


def _naive(moment: object) -> object:
    """Excel не принимает timezone-aware datetime."""
    if isinstance(moment, datetime) and moment.tzinfo is not None:
        return moment.replace(tzinfo=None)
    return moment
