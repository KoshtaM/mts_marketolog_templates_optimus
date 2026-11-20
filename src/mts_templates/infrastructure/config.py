"""Загрузка и сохранение настроек приложения (TOML)."""

from __future__ import annotations

import os
import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from mts_templates.application.settings import (
    BASELINE_CATALOG,
    BASELINE_MODES,
    BASELINE_OBSERVED,
    DATABASE_NAME,
    DEFAULT_THEME,
    SETTINGS_NAME,
    THEME_IDS,
    AppSettings,
    BenefitThresholds,
)
from mts_templates.domain.analytics.normalization import (
    PUNCTUATION_DELETE,
    PUNCTUATION_POLICIES,
)
from mts_templates.domain.value_objects import Money

__all__ = [
    "BASELINE_CATALOG",
    "BASELINE_MODES",
    "BASELINE_OBSERVED",
    "DATABASE_NAME",
    "SETTINGS_NAME",
    "AppSettings",
    "BenefitThresholds",
    "TomlSettingsStore",
    "config_dir",
    "default_data_dir",
    "default_settings",
    "dump_settings",
    "load_settings",
    "save_settings",
]

APP_DIR_NAME = "MtsTemplates"


def default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def config_dir() -> Path:
    """Каталог с TOML-конфигурацией: env → каталог проекта → пользовательский."""
    override = os.environ.get("MTS_TEMPLATES_CONFIG")
    if override:
        return Path(override)
    project_config = Path(__file__).resolve().parents[3] / "config"
    if project_config.is_dir():
        return project_config
    return default_data_dir() / "config"


def default_settings() -> AppSettings:
    return AppSettings(
        data_dir=default_data_dir(),
        template_fee=Money.from_rub("2000.00"),
        min_support=5,
        min_cluster_segments=5,
        min_text_length=8,
        max_foreign_matches=0,
        max_w_words=20,
        max_d_words=20,
        max_word_slots_per_merge=20,
        max_literal_cardinality=3,
        max_tail_depth=4,
        punctuation_policy=PUNCTUATION_DELETE,
        fold_yo=False,
        fold_homoglyphs=False,
        sender_case_sensitive=False,
        baseline_mode=BASELINE_OBSERVED,
        delivered_only=True,
        benefit_thresholds=BenefitThresholds(),
        theme=DEFAULT_THEME,
    )


def load_settings(data_dir: Path | None = None) -> AppSettings:
    """Прочитать настройки: встроенные → config/app.toml → settings.toml пользователя."""
    settings = default_settings()
    if data_dir is not None:
        settings = settings.with_overrides(data_dir=data_dir)

    project_file = config_dir() / "app.toml"
    settings = _apply_file(settings, project_file)

    user_file = settings.data_dir / SETTINGS_NAME
    settings = _apply_file(settings, user_file)
    return settings


def save_settings(settings: AppSettings) -> Path:
    """Сохранить пользовательские настройки в каталог данных."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.data_dir / SETTINGS_NAME
    path.write_text(dump_settings(settings), encoding="utf-8")
    return path


def dump_settings(settings: AppSettings) -> str:
    lines = [
        "# Настройки MTS Templates Optimus. Файл создаётся приложением.",
        f"data_dir = {_quote(settings.data_dir)}",
        f"template_fee = {_quote(settings.template_fee.amount)}",
        f"min_support = {settings.min_support}",
        f"min_cluster_segments = {settings.min_cluster_segments}",
        f"min_text_length = {settings.min_text_length}",
        f"max_foreign_matches = {settings.max_foreign_matches}",
        f"max_w_words = {settings.max_w_words}",
        f"max_d_words = {settings.max_d_words}",
        f"max_word_slots_per_merge = {settings.max_word_slots_per_merge}",
        f"max_literal_cardinality = {settings.max_literal_cardinality}",
        f"max_tail_depth = {settings.max_tail_depth}",
        f"punctuation_policy = {_quote(settings.punctuation_policy)}",
        f"fold_yo = {str(settings.fold_yo).lower()}",
        f"fold_homoglyphs = {str(settings.fold_homoglyphs).lower()}",
        f"sender_case_sensitive = {str(settings.sender_case_sensitive).lower()}",
        f"baseline_mode = {_quote(settings.baseline_mode)}",
        f"delivered_only = {str(settings.delivered_only).lower()}",
        f"theme = {_quote(settings.theme)}",
    ]
    if settings.last_statistics_dir is not None:
        lines.append(f"last_statistics_dir = {_quote(settings.last_statistics_dir)}")
    if settings.last_templates_dir is not None:
        lines.append(f"last_templates_dir = {_quote(settings.last_templates_dir)}")
    if settings.last_export_dir is not None:
        lines.append(f"last_export_dir = {_quote(settings.last_export_dir)}")
    thresholds = ", ".join(f'"{level.amount}"' for level in settings.benefit_thresholds.levels)
    lines.extend(["", "[benefit]", f"thresholds = [{thresholds}]"])
    return "\n".join(lines) + "\n"


class TomlSettingsStore:
    """Порт хранения настроек поверх TOML-файлов."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir

    def load(self) -> AppSettings:
        return load_settings(self._data_dir)

    def save(self, settings: AppSettings) -> None:
        save_settings(settings)


def _apply_file(settings: AppSettings, path: Path) -> AppSettings:
    if not path.is_file():
        return settings
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return settings
    return _apply_mapping(settings, raw)


def _apply_mapping(settings: AppSettings, raw: dict[str, Any]) -> AppSettings:
    changes: dict[str, Any] = {}

    if "data_dir" in raw:
        changes["data_dir"] = Path(str(raw["data_dir"])).expanduser()
    if "template_fee" in raw:
        changes["template_fee"] = _parse_money(raw["template_fee"])
    if "min_cluster_segments" in raw:
        changes["min_cluster_segments"] = max(1, int(raw["min_cluster_segments"]))
    elif "min_cluster_messages" in raw:
        # Устаревший ключ: раньше порог считался по сообщениям.
        changes["min_cluster_segments"] = max(1, int(raw["min_cluster_messages"]))
    if "min_support" in raw:
        changes["min_support"] = max(1, int(raw["min_support"]))
    if "min_text_length" in raw:
        changes["min_text_length"] = max(1, int(raw["min_text_length"]))
    if "max_foreign_matches" in raw:
        changes["max_foreign_matches"] = max(0, int(raw["max_foreign_matches"]))
    if "max_w_words" in raw:
        changes["max_w_words"] = max(1, int(raw["max_w_words"]))
    if "max_d_words" in raw:
        changes["max_d_words"] = max(1, int(raw["max_d_words"]))
    if "max_word_slots_per_merge" in raw:
        changes["max_word_slots_per_merge"] = max(1, int(raw["max_word_slots_per_merge"]))
    if "max_literal_cardinality" in raw:
        changes["max_literal_cardinality"] = max(1, int(raw["max_literal_cardinality"]))
    if "max_tail_depth" in raw:
        changes["max_tail_depth"] = max(0, int(raw["max_tail_depth"]))
    if "punctuation_policy" in raw:
        policy = str(raw["punctuation_policy"])
        if policy in PUNCTUATION_POLICIES:
            changes["punctuation_policy"] = policy
    for key in ("fold_yo", "fold_homoglyphs", "sender_case_sensitive"):
        if key in raw:
            changes[key] = bool(raw[key])
    if "baseline_mode" in raw:
        mode = str(raw["baseline_mode"])
        if mode in BASELINE_MODES:
            changes["baseline_mode"] = mode
    if "delivered_only" in raw:
        changes["delivered_only"] = bool(raw["delivered_only"])
    if "theme" in raw:
        theme = str(raw["theme"]).strip()
        if theme in THEME_IDS:
            changes["theme"] = theme
    thresholds = _parse_benefit_thresholds(raw.get("benefit"))
    if thresholds is not None:
        changes["benefit_thresholds"] = thresholds
    for key in ("last_statistics_dir", "last_templates_dir", "last_export_dir"):
        if key in raw and str(raw[key]).strip():
            changes[key] = Path(str(raw[key])).expanduser()

    return settings.with_overrides(**changes) if changes else settings


def _parse_money(value: object) -> Money:
    try:
        return Money(Decimal(str(value).replace(",", ".")))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Некорректная денежная сумма в настройках: {value!r}") from exc


def _parse_benefit_thresholds(value: object) -> BenefitThresholds | None:
    """Разобрать `[benefit] thresholds = [...]`; при ошибке — оставить умолчания."""
    if not isinstance(value, dict):
        return None
    raw = value.get("thresholds")
    if not isinstance(raw, list) or len(raw) != 5:
        return None
    try:
        levels = [Money(Decimal(str(item).replace(",", "."))) for item in raw]
        return BenefitThresholds(
            level_1=levels[0],
            level_2=levels[1],
            level_3=levels[2],
            level_4=levels[3],
            level_5=levels[4],
        )
    except (InvalidOperation, ValueError, TypeError):
        return None


def _quote(value: object) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'
