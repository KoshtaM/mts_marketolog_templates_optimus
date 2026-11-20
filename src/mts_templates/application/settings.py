"""Настройки приложения как DTO слоя приложения.

Загрузка и сохранение TOML — в инфраструктуре, здесь только структура.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from mts_templates.domain.value_objects import Money

DATABASE_NAME = "mts_templates.db"
SETTINGS_NAME = "settings.toml"
BASELINE_OBSERVED = "observed"
BASELINE_CATALOG = "catalog"
BASELINE_MODES = (BASELINE_OBSERVED, BASELINE_CATALOG)
BENEFIT_LEVELS = 5

# Идентификаторы тем оформления. Сами стили живут в presentation: здесь только
# значения, которые сохраняются в TOML и проверяются при загрузке.
THEME_SYSTEM = "system"
THEME_NEO_BRUTALISM = "neo_brutalism"
THEME_BIOPHILIC_GLASSHOUSE = "biophilic_glasshouse"
THEME_CASSETTE_FUTURISM = "cassette_futurism"
THEME_SWISS_MINIMALISM = "swiss_minimalism"
THEME_DARK_ART_DECO = "dark_art_deco"
THEME_ETHEREAL_MESH = "ethereal_mesh"
THEME_LOFI_COZY = "lofi_cozy"
DEFAULT_THEME = THEME_SYSTEM
THEME_IDS = (
    THEME_SYSTEM,
    THEME_NEO_BRUTALISM,
    THEME_BIOPHILIC_GLASSHOUSE,
    THEME_CASSETTE_FUTURISM,
    THEME_SWISS_MINIMALISM,
    THEME_DARK_ART_DECO,
    THEME_ETHEREAL_MESH,
    THEME_LOFI_COZY,
)


@dataclass(frozen=True, slots=True)
class BenefitThresholds:
    """Пороги уровней выгоды шаблона, ₽.

    Уровень 1 — «еле выгоден», уровень 5 — «супер выгоден». Убыток (`< 0`)
    выделяется отдельным слабо-красным цветом и порогов не имеет.
    """

    level_1: Money = field(default_factory=lambda: Money.from_rub("1"))
    level_2: Money = field(default_factory=lambda: Money.from_rub("3000"))
    level_3: Money = field(default_factory=lambda: Money.from_rub("10000"))
    level_4: Money = field(default_factory=lambda: Money.from_rub("30000"))
    level_5: Money = field(default_factory=lambda: Money.from_rub("100000"))

    def __post_init__(self) -> None:
        levels = self.levels
        if any(level.amount < 0 for level in levels):
            raise ValueError("Пороги выгоды не могут быть отрицательными")
        if list(levels) != sorted(levels) or len(set(levels)) != len(levels):
            raise ValueError("Пороги выгоды должны строго возрастать")

    @property
    def levels(self) -> tuple[Money, Money, Money, Money, Money]:
        return (self.level_1, self.level_2, self.level_3, self.level_4, self.level_5)


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Настройки, влияющие на импорт, анализ и экспорт."""

    data_dir: Path
    template_fee: Money
    min_support: int
    min_cluster_segments: int
    min_text_length: int
    max_foreign_matches: int
    max_w_words: int
    max_d_words: int
    max_word_slots_per_merge: int
    max_literal_cardinality: int
    max_tail_depth: int
    punctuation_policy: str
    fold_yo: bool
    fold_homoglyphs: bool
    sender_case_sensitive: bool
    baseline_mode: str
    delivered_only: bool
    benefit_thresholds: BenefitThresholds = BenefitThresholds()
    theme: str = DEFAULT_THEME
    last_statistics_dir: Path | None = None
    last_templates_dir: Path | None = None
    last_export_dir: Path | None = None

    @property
    def database_path(self) -> Path:
        return self.data_dir / DATABASE_NAME

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def with_overrides(self, **changes: Any) -> AppSettings:
        return replace(self, **changes)
