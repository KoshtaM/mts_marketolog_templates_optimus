"""Фиксированные цвета операторов для круговых диаграмм. Без Qt."""

from __future__ import annotations

from mts_templates.domain.value_objects import Operator

OTHER_COLOR = "#98a2b3"

# Крупные операторы — корпоративные цвета брендов, чтобы сектора диаграмм
# читались как «МТС», «МегаФон» и «Билайн» без обращения к легенде.
OPERATOR_COLORS: dict[str, str] = {
    Operator.MTS.value: "#e30611",
    Operator.T2.value: "#1d1d1f",
    Operator.MEGAFON.value: "#00b956",
    Operator.BEELINE.value: "#ffcc00",
    Operator.OTHER_RF.value: "#1f6feb",
    Operator.ROSTELECOM.value: "#7c3aed",
    Operator.SBERTELECOM.value: "#0e9aa7",
    Operator.SMARTS_MOTIV.value: "#f97316",
    Operator.INTERNATIONAL.value: "#db2777",
    Operator.UNKNOWN.value: "#8d6e63",
}


def operator_color(operator: str) -> str:
    """Цвет сектора оператора; неизвестное имя получает нейтральный серый."""
    return OPERATOR_COLORS.get(operator, OTHER_COLOR)
