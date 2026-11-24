"""Интеграционный сценарий: статистика + шаблоны → анализ → отчёт."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from mts_templates.application.dto import (
    AnalyzeRequest,
    ExportReportRequest,
    ImportStatisticsRequest,
    ImportTemplatesRequest,
)
from mts_templates.composition import build_container
from mts_templates.domain.errors import OperationCancelled
from mts_templates.domain.value_objects import Operator
from mts_templates.infrastructure.config import load_settings
from tests.fixtures import TEMPLATE_HEADERS, write_statistics_xlsx, write_templates_xlsx

TEMPLATED_PACKAGE = "Подписка. Все операторы (шаблонированный)"
ORDINARY_PACKAGE = "Подписка. Все операторы"
CANDIDATE_DAYS = (1, 6, 11, 16, 21, 30)


def statistics_rows() -> list[dict[str, object]]:
    base = {
        "Имя отправителя": "TEST",
        "Номер получателя": "79000000000",
        "Оператор получателя": "MTS",
        "Статус отправки": "Отправлено",
        "Статус доставки СМС или ММС": "Успешная доставка",
        "Канал": "SMS",
        "Количество sms в пакете при покупке": 999999999,
    }
    rows: list[dict[str, object]] = []
    for index, code in enumerate(("1111", "2222")):
        rows.append(
            {
                **base,
                "ID сообщения": f"T{index}",
                "Дата попытки отправки": "2026-11-01T10:00:00+03:00",
                "Текст сообщения": f"Ваш код {code}",
                "Цена за один сегмент": 4,
                "Стоимость": 4,
                "Количество сегментов в sms": 1,
                "Тип пакета": TEMPLATED_PACKAGE,
            }
        )
    for index, day in enumerate(CANDIDATE_DAYS):
        rows.append(
            {
                **base,
                "ID сообщения": f"O{index}",
                "Дата попытки отправки": f"2026-11-{day:02d}T10:00:00+03:00",
                "Текст сообщения": f"Заказ {1001 + index} готов к выдаче",
                "Цена за один сегмент": 9.6,
                "Стоимость": 9.6,
                "Количество сегментов в sms": 1,
                "Тип пакета": ORDINARY_PACKAGE,
            }
        )
    rows.append(
        {
            **base,
            "ID сообщения": "S1",
            "Дата попытки отправки": "2026-11-02T10:00:00+03:00",
            "Текст сообщения": "Добрый день",
            "Цена за один сегмент": 9.6,
            "Стоимость": 9.6,
            "Количество сегментов в sms": 1,
            "Тип пакета": ORDINARY_PACKAGE,
        }
    )
    return rows


def template_rows() -> list[dict[str, object]]:
    return [
        {
            "Название": "Код подтверждения",
            "Текст шаблона": "Ваш код %d",
            "Имя отправителя": "TEST",
            "Статус": "Активен",
            "Стоимость": 2000,
        }
    ]


def partial_statistics_rows() -> list[dict[str, object]]:
    """Те же строки, но период обрывается 16 ноября: неполный месяц."""
    return [
        row for row in statistics_rows() if str(row["Дата попытки отправки"])[:10] <= "2026-11-16"
    ]


@pytest.fixture
def container(tmp_path: Path):
    settings = load_settings(data_dir=tmp_path / "data")
    built = build_container(tmp_path / "app.db", settings=settings)
    yield built
    built.database.close()


def test_full_analysis_scenario(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    templates = write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())

    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    templates_report = container.import_templates.execute(ImportTemplatesRequest(path=templates))

    assert import_report.batch.message_count == 9
    assert import_report.batch.segment_count == 9
    assert templates_report.imported == 1
    assert templates_report.updated == 0

    view = container.analyze_templates.execute(AnalyzeRequest(batch_id=import_report.batch.id))

    assert len(view.metrics) == 1
    metrics = view.metrics[0]
    assert metrics.template_id
    assert metrics.matched_messages == 2
    assert metrics.triggered_messages == 2
    assert metrics.actual_cost.rounded().amount == Decimal("8.00")
    assert metrics.baseline_cost.rounded().amount == Decimal("19.20")
    assert metrics.template_fee.rounded().amount == Decimal("2000.00")
    assert metrics.net_benefit.rounded().amount == Decimal("-1988.80")
    assert metrics.trigger_rate == pytest.approx(1.0)
    assert view.total_segments == 9
    assert view.templated_segments == 2
    assert metrics.share_of_all_segments == pytest.approx(2 / 9)
    assert metrics.share_of_templated_segments == pytest.approx(1.0)
    assert [(item.day, item.segments) for item in metrics.daily_segments] == [
        (date(2026, 11, 1), 2)
    ]
    assert [(item.day, item.segments) for item in view.daily_total_segments] == [
        (date(2026, 11, 1), 3),
        (date(2026, 11, 2), 1),
        (date(2026, 11, 6), 1),
        (date(2026, 11, 11), 1),
        (date(2026, 11, 16), 1),
        (date(2026, 11, 21), 1),
        (date(2026, 11, 30), 1),
    ]
    assert [(item.day, item.segments) for item in view.daily_templated_segments] == [
        (date(2026, 11, 1), 2)
    ]

    assert len(view.candidates) == 1
    candidate = view.candidates[0]
    assert candidate.template_text == "Заказ %d готов к выдаче"
    assert candidate.messages == 6
    assert candidate.actual_cost.rounded().amount == Decimal("57.60")
    assert candidate.templated_cost.rounded().amount == Decimal("24.00")
    assert candidate.monthly_saving.rounded().amount == Decimal("33.60")
    assert candidate.net_monthly.rounded().amount == Decimal("-1966.40")
    assert candidate.is_partial_period is False
    assert candidate.confidence == pytest.approx(1.0)
    assert candidate.share_of_all_segments == pytest.approx(6 / 9)
    assert [(item.day, item.segments) for item in candidate.daily_segments] == [
        (date(2026, 11, 1), 1),
        (date(2026, 11, 6), 1),
        (date(2026, 11, 11), 1),
        (date(2026, 11, 16), 1),
        (date(2026, 11, 21), 1),
        (date(2026, 11, 30), 1),
    ]

    assert view.total_net_benefit.rounded().amount == Decimal("-1988.80")

    operator = view.operator_triggers[0]
    assert operator.operator == Operator.MTS.value
    assert operator.matched_segments == 2
    assert operator.share == pytest.approx(1.0)


def test_analysis_is_cached(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    container.import_templates.execute(ImportTemplatesRequest(path=tmp_path / "templates.xlsx"))
    batch_id = container.dashboard.execute().batch.id

    first = container.analyze_templates.execute(AnalyzeRequest(batch_id=batch_id))
    second = container.analyze_templates.execute(AnalyzeRequest(batch_id=batch_id))

    assert first.run_id == second.run_id
    assert first.daily_total_segments == second.daily_total_segments
    assert first.daily_templated_segments == second.daily_templated_segments
    assert first.metrics[0].daily_segments == second.metrics[0].daily_segments
    assert first.candidates[0].daily_segments == second.candidates[0].daily_segments
    assert container.database.fetchone("SELECT COUNT(*) AS c FROM analysis_runs")["c"] == 1


def test_dashboard_benefit_matches_monthly_template_model(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", partial_statistics_rows())
    write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    container.import_templates.execute(ImportTemplatesRequest(path=tmp_path / "templates.xlsx"))
    view = container.analyze_templates.execute(AnalyzeRequest(batch_id=import_report.batch.id))

    summary = container.dashboard.execute(import_report.batch.id)

    assert view.is_partial_period is True
    assert summary.total_monthly_net_benefit == view.total_monthly_net_benefit
    assert summary.total_monthly_net_benefit != view.total_net_benefit


def test_dashboard_counts_potential_benefit(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    container.import_templates.execute(ImportTemplatesRequest(path=tmp_path / "templates.xlsx"))
    container.analyze_templates.execute(AnalyzeRequest(batch_id=import_report.batch.id))

    summary = container.dashboard.execute(import_report.batch.id)

    assert summary.total_monthly_net_benefit.rounded().amount == Decimal("-1988.80")
    # Кандидат в сценарии убыточен, прибыльных кандидатов нет.
    assert summary.profitable_candidates == 0
    assert summary.candidates == 1
    assert summary.profitable_candidates_benefit.rounded().amount == Decimal("0.00")
    # Убыточный шаблон: его удаление вернуло бы 1 988,80 ₽ в месяц.
    assert summary.loss_templates_benefit.rounded().amount == Decimal("-1988.80")
    assert summary.potential_benefit.rounded().amount == Decimal("1988.80")


def test_analysis_can_be_cancelled(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))

    with pytest.raises(OperationCancelled):
        container.analyze_templates.execute(
            AnalyzeRequest(batch_id=import_report.batch.id, force=True),
            should_cancel=lambda: True,
        )

    assert container.database.fetchone("SELECT COUNT(*) AS c FROM analysis_runs")["c"] == 0


def test_template_matches_but_does_not_trigger_for_operator_outside_its_list(
    tmp_path: Path, container
) -> None:
    rows_source = [
        {**row, "Тип пакета": ORDINARY_PACKAGE, "Цена за один сегмент": 9.6, "Стоимость": 9.6}
        if row["ID сообщения"].startswith("T")
        else row
        for row in statistics_rows()
    ]
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", rows_source)
    template = [{**template_rows()[0], "Операторы": "Мегафон"}]
    templates = write_templates_xlsx(
        tmp_path / "templates.xlsx", template, headers=(*TEMPLATE_HEADERS, "Операторы")
    )
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    container.import_templates.execute(ImportTemplatesRequest(path=templates))

    view = container.analyze_templates.execute(AnalyzeRequest(batch_id=import_report.batch.id))

    metrics = view.metrics[0]
    assert metrics.matched_messages == 2
    assert metrics.triggered_messages == 0
    assert metrics.off_operator_messages == 2
    assert metrics.trigger_rate == pytest.approx(0)
    assert metrics.actual_cost.rounded().amount == Decimal("0.00")
    assert any("оплачены как обычные" in warning for warning in view.warnings)
    assert view.trigger_rate == pytest.approx(0)

    operator = next(item for item in view.operator_triggers if item.operator == Operator.MTS.value)
    assert operator.listed is False
    assert operator.matched_messages == 2
    assert operator.triggered_messages == 0
    assert operator.trigger_rate == pytest.approx(0)


def test_export_report_contains_all_sheets(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))
    container.import_templates.execute(ImportTemplatesRequest(path=tmp_path / "templates.xlsx"))
    container.analyze_templates.execute(AnalyzeRequest(batch_id=import_report.batch.id))

    target = tmp_path / "report.xlsx"
    result = container.export_report.execute(
        ExportReportRequest(path=target, batch_id=import_report.batch.id)
    )

    assert result.path == target
    assert result.templates == 1
    assert result.candidates == 1
    workbook = load_workbook(target)
    assert workbook.sheetnames == [
        "Сводка",
        "Шаблоны",
        "Операторы",
        "Кандидаты",
        "Предупреждения",
    ]
    summary = workbook["Сводка"]
    labels = [row[0].value for row in summary.iter_rows(min_row=2)]
    assert "Методика baseline" in labels
    assert "Выгода шаблонов/мес, ₽" in labels

    headers = [cell.value for cell in workbook["Шаблоны"][1]]
    assert "Сообщений" in headers
    assert "Операторы" in headers
    assert "% от всех сегментов" in headers
    assert "% от шаблонированных" in headers
    assert "Без шаблона/мес, ₽" in headers
    assert "Выгода/мес, ₽" in headers
    assert "Baseline, ₽" not in headers
    workbook.close()


def test_template_import_replaces_previous_set(tmp_path: Path, container) -> None:
    base = template_rows()[0]
    first = write_templates_xlsx(
        tmp_path / "first.xlsx",
        [base, {**base, "Название": "Второй", "Текст шаблона": "Код %d"}],
    )
    container.import_templates.execute(ImportTemplatesRequest(path=first))
    assert container.database.fetchone("SELECT COUNT(*) AS c FROM templates")["c"] == 2

    second = write_templates_xlsx(tmp_path / "second.xlsx", [base])
    report = container.import_templates.execute(ImportTemplatesRequest(path=second))

    assert report.removed == 1
    assert container.database.fetchone("SELECT COUNT(*) AS c FROM templates")["c"] == 1


def test_template_import_invalidates_analysis_cache(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    templates = write_templates_xlsx(tmp_path / "templates.xlsx", template_rows())
    batch = container.import_statistics.execute(ImportStatisticsRequest(path=statistics)).batch
    container.import_templates.execute(ImportTemplatesRequest(path=templates))
    first = container.analyze_templates.execute(AnalyzeRequest(batch_id=batch.id))

    container.import_templates.execute(ImportTemplatesRequest(path=templates))
    assert container.database.fetchone("SELECT COUNT(*) AS c FROM analysis_runs")["c"] == 0

    second = container.analyze_templates.execute(AnalyzeRequest(batch_id=batch.id))
    assert second.run_id != first.run_id


def test_templates_preview_and_dedupe(tmp_path: Path, container) -> None:
    rows = template_rows() + template_rows()
    path = write_templates_xlsx(tmp_path / "templates.xlsx", rows)

    preview = container.preview_templates.execute(path)
    assert "Текст шаблона" in preview.columns

    first = container.import_templates.execute(ImportTemplatesRequest(path=path))
    second = container.import_templates.execute(ImportTemplatesRequest(path=path))

    assert first.imported == 1
    assert first.duplicates == 0
    assert any("Объединены записи" in warning for warning in first.warnings)
    assert second.imported == 0
    assert second.updated == 1


def test_dashboard_summary(tmp_path: Path, container) -> None:
    statistics = write_statistics_xlsx(tmp_path / "statistics.xlsx", statistics_rows())
    import_report = container.import_statistics.execute(ImportStatisticsRequest(path=statistics))

    summary = container.dashboard.execute()

    assert summary.batch is not None
    assert summary.batch.id == import_report.batch.id
    assert summary.statistics is not None
    assert summary.statistics.message_count == 9
    assert summary.statistics.ordinary_messages == 7
    assert summary.statistics.templated_messages == 2
    assert summary.statistics.ordinary_rate is not None
    assert summary.statistics.ordinary_rate.rounded().amount == Decimal("9.60")
    assert len(summary.operators) == 1
    assert summary.operators[0].operator == Operator.MTS.value
    assert summary.operators[0].messages == 9
    assert summary.operators[0].segments == 9
    assert summary.operators[0].average_segment_cost is not None
    assert summary.operators[0].average_segment_cost.rounded().amount == Decimal("8.36")

    assert summary.segmentation is not None
    assert summary.segmentation.subscribers == 1
    assert summary.segmentation.subscriber_segments == 9
    assert summary.segmentation.subscriber_messages == 9
    assert [
        (item.segments, item.count) for item in summary.segmentation.subscribers_by_segments
    ] == [(9, 1)]
    assert [(item.segments, item.count) for item in summary.segmentation.messages_by_segments] == [
        (1, 9)
    ]
    assert summary.segmentation.subscribers_by_operator[0].operator == Operator.MTS.value
