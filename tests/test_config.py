"""Тесты настроек приложения."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from mts_templates.application.settings import (
    THEME_DARK_ART_DECO,
    THEME_SYSTEM,
    BenefitThresholds,
)
from mts_templates.domain.value_objects import Money
from mts_templates.infrastructure.config import (
    BASELINE_CATALOG,
    default_settings,
    dump_settings,
    load_settings,
    save_settings,
)


def test_defaults_are_loaded(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path)

    assert settings.template_fee.amount == Decimal("2000.00")
    assert settings.baseline_mode == "observed"
    assert settings.delivered_only is True
    assert settings.min_cluster_segments == 5
    assert settings.benefit_thresholds.level_1 == Money.from_rub("1")


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    thresholds = BenefitThresholds(
        level_1=Money.from_rub("2"),
        level_2=Money.from_rub("5000"),
        level_3=Money.from_rub("15000"),
        level_4=Money.from_rub("40000"),
        level_5=Money.from_rub("120000"),
    )
    settings = default_settings().with_overrides(
        data_dir=tmp_path,
        baseline_mode=BASELINE_CATALOG,
        min_cluster_segments=7,
        benefit_thresholds=thresholds,
        last_export_dir=tmp_path / "exports",
    )
    save_settings(settings)

    loaded = load_settings(data_dir=tmp_path)

    assert loaded.baseline_mode == BASELINE_CATALOG
    assert loaded.min_cluster_segments == 7
    assert loaded.benefit_thresholds == thresholds
    assert loaded.last_export_dir == tmp_path / "exports"


def test_legacy_min_cluster_messages_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text("min_cluster_messages = 9\n", encoding="utf-8")

    settings = load_settings(data_dir=tmp_path)

    assert settings.min_cluster_segments == 9


def test_broken_benefit_thresholds_fall_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text(
        '[benefit]\nthresholds = ["5", "1"]\n',
        encoding="utf-8",
    )

    settings = load_settings(data_dir=tmp_path)

    assert settings.benefit_thresholds == BenefitThresholds()


def test_dump_contains_no_float_money(tmp_path: Path) -> None:
    text = dump_settings(default_settings().with_overrides(data_dir=tmp_path))

    assert 'template_fee = "2000.00"' in text
    assert "data_dir" in text
    assert "[benefit]" in text
    assert 'thresholds = ["1", "3000", "10000", "30000", "100000"]' in text


def test_broken_file_falls_back_to_defaults(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text("this is not toml", encoding="utf-8")

    settings = load_settings(data_dir=tmp_path)

    assert settings.template_fee.amount == Decimal("2000.00")


def test_default_theme_is_system(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path)

    assert settings.theme == THEME_SYSTEM


def test_theme_roundtrip(tmp_path: Path) -> None:
    settings = default_settings().with_overrides(
        data_dir=tmp_path,
        theme=THEME_DARK_ART_DECO,
    )
    save_settings(settings)

    loaded = load_settings(data_dir=tmp_path)

    assert loaded.theme == THEME_DARK_ART_DECO


def test_unknown_theme_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text('theme = "unknown"\n', encoding="utf-8")

    settings = load_settings(data_dir=tmp_path)

    assert settings.theme == THEME_SYSTEM


def test_dump_contains_theme(tmp_path: Path) -> None:
    text = dump_settings(default_settings().with_overrides(data_dir=tmp_path))

    assert 'theme = "system"' in text
