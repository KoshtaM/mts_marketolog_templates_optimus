"""Пакет инфраструктуры тарифов."""

from mts_templates.infrastructure.tariffs.toml_catalog import (
    default_catalog_path,
    load_tariff_catalog,
)

__all__ = ["default_catalog_path", "load_tariff_catalog"]
