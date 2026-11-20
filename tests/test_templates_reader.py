"""Тесты чтения реальной выгрузки шаблонов МТС-Маркетолога."""

from __future__ import annotations

from pathlib import Path

from mts_templates.domain.value_objects import Operator
from mts_templates.infrastructure.excel.templates_reader import (
    ExcelTemplateReader,
    detect_mapping,
)
from tests.fixtures import write_templates_xlsx

REAL_HEADERS = (
    "ID шаблона",
    "Текст шаблона",
    "Текст (пример) шаблона",
    "Имя отправителя",
    "Статус",
    "Операторы",
)


def _row(
    template_id: str,
    text: str,
    *,
    operators: str = "МТС",
    status: str = "Подключен",
    sender: str = "DOCTORLIGHT",
    example: str = "",
) -> dict[str, object]:
    return {
        "ID шаблона": template_id,
        "Текст шаблона": text,
        "Текст (пример) шаблона": example,
        "Имя отправителя": sender,
        "Статус": status,
        "Операторы": operators,
    }


def _read(tmp_path: Path, rows: list[dict[str, object]]):
    path = write_templates_xlsx(tmp_path / "templates.xlsx", rows, headers=REAL_HEADERS)
    return ExcelTemplateReader().read(path)


def test_detect_mapping_for_real_headers() -> None:
    mapping = detect_mapping(REAL_HEADERS)

    assert mapping is not None
    assert mapping.template_id == "ID шаблона"
    assert mapping.text == "Текст шаблона"
    assert mapping.example == "Текст (пример) шаблона"
    assert mapping.sender == "Имя отправителя"
    assert mapping.active == "Статус"
    assert mapping.operators == "Операторы"
    assert mapping.monthly_fee is None


def test_same_text_with_different_ids_is_one_template(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("13549", "Запись на %w{1,2} по адресу %w{1,6} Возьмите паспорт", operators="МТС"),
            _row(
                "13559",
                "Запись на %w{1,2} по адресу %w{1,6} Возьмите паспорт",
                operators="билайн",
            ),
        ],
    )

    assert len(result.templates) == 1
    template = result.templates[0]
    assert template.template_id == "13549"
    assert template.operators == frozenset({Operator.MTS, Operator.BEELINE})
    assert template.active is True
    assert any("Объединены записи" in warning for warning in result.warnings)


def test_case_and_punctuation_differences_are_separate_templates(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("1", "Ваш код %d, никому не сообщайте", operators="МТС"),
            _row("2", "ВАШ КОД %d никому не сообщайте!", operators="билайн"),
        ],
    )

    assert len(result.templates) == 2
    assert [template.operators for template in result.templates] == [
        frozenset({Operator.MTS}),
        frozenset({Operator.BEELINE}),
    ]


def test_suffix_variant_is_separate_template(tmp_path: Path) -> None:
    base = "Запись на %w{1,2} по адресу %w{1,6} Возьмите паспорт"
    result = _read(
        tmp_path,
        [
            _row("13549", base, operators="МТС"),
            _row("13877", f"{base} — DOCTORLIGHT", operators="т2"),
        ],
    )

    assert len(result.templates) == 2
    by_id = {template.template_id: template for template in result.templates}
    assert by_id["13549"].text == base
    assert by_id["13877"].text == f"{base} — DOCTORLIGHT"
    assert by_id["13877"].operators == frozenset({Operator.T2})


def test_extra_spaces_difference_is_separate_templates(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("1", "Ваш код %d", operators="МТС"),
            _row("2", "Ваш  код %d", operators="билайн"),
        ],
    )

    assert len(result.templates) == 2


def test_compact_operator_cell_lists_all_operators(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [_row("12403", "%d код подтверждения", operators="МТС/билайн/МегаФон/Ростелеком")],
    )

    assert len(result.templates) == 1
    assert result.templates[0].operators == frozenset(
        {Operator.MTS, Operator.BEELINE, Operator.MEGAFON, Operator.ROSTELECOM}
    )


def test_disabled_registration_removes_operator_from_template(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("10", "Текст %d", operators="МТС", status="Подключен"),
            _row("11", "Текст %d", operators="билайн", status="Отключен"),
        ],
    )

    template = result.templates[0]
    assert template.active is True
    assert template.operators == frozenset({Operator.MTS})
    assert any("отключён у операторов" in warning for warning in result.warnings)


def test_template_disabled_for_all_operators_is_inactive(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("10", "Текст %d", operators="МТС", status="Отключен"),
            _row("11", "Текст %d", operators="билайн", status="Отключен"),
        ],
    )

    template = result.templates[0]
    assert template.active is False
    assert template.operators == frozenset({Operator.MTS, Operator.BEELINE})
    assert not any("отключён у операторов" in warning for warning in result.warnings)


def test_same_text_with_different_senders_is_two_templates(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("1", "Текст %d", sender="SHOP"),
            _row("2", "Текст %d", sender="BANK"),
        ],
    )

    assert len(result.templates) == 2
    assert {template.sender for template in result.templates} == {"SHOP", "BANK"}


def test_canonical_id_is_minimal_numeric(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("13559", "Текст %d", operators="билайн"),
            _row("13549", "Текст %d", operators="МТС"),
        ],
    )

    assert result.templates[0].template_id == "13549"


def test_status_otklyuchen_marks_template_inactive(tmp_path: Path) -> None:
    result = _read(tmp_path, [_row("1", "Текст %d", status="Отключен")])

    assert result.templates[0].active is False


def test_unknown_status_is_inactive_with_warning(tmp_path: Path) -> None:
    result = _read(tmp_path, [_row("1", "Текст %d", status="На модерации")])

    assert result.templates[0].active is False
    assert any("неизвестный статус" in warning for warning in result.warnings)


def test_example_matching_template_is_kept_without_warning(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [_row("1", "Ваш код %d", example="Ваш код 1234", operators="МТС")],
    )

    assert len(result.templates) == 1
    assert result.templates[0].example == "Ваш код 1234"
    assert not result.warnings


def test_example_that_does_not_match_is_reported(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [_row("1", "Ваш код %d", example="Ваш код abc", operators="МТС")],
    )

    assert result.templates[0].example == ""
    assert any("пример не соответствует шаблону" in warning for warning in result.warnings)


def test_duplicate_id_is_reported(tmp_path: Path) -> None:
    result = _read(
        tmp_path,
        [
            _row("1", "Текст %d", operators="МТС"),
            _row("1", "Текст %d", operators="билайн"),
        ],
    )

    assert len(result.templates) == 1
    assert any("уже встречался" in warning for warning in result.warnings)
