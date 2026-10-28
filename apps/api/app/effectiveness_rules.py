"""Regla pura de verificación de eficacia.

- Un dato faltante (None) nunca equivale a cero: el resultado es «datos insuficientes».
- Los días sin producción no cuentan para el periodo mínimo.
- El denominador es explícito (unidades producidas, inspeccionadas, lotes, embarques u otro).
"""
from dataclasses import dataclass
from datetime import date

DENOMINATORS = {
    "units_produced": "unidades producidas",
    "units_inspected": "unidades inspeccionadas",
    "lots_received": "lotes recibidos",
    "shipments": "embarques",
    "other": "otro",
}
# Con estos denominadores los defectos no pueden superar al denominador (son unidades del mismo universo).
UNIT_DENOMINATORS = {"units_produced", "units_inspected"}


@dataclass
class Evaluation:
    result: str  # effective | ineffective | insufficient_data
    value: float | None
    reasons: list[str]


class InvalidData(ValueError):
    pass


def evaluate(criterion: dict, period_start: date, period_end: date, denominator: int | None, defects: int | None,
             days_without_production: int = 0) -> Evaluation:
    reasons: list[str] = []
    period_days = (period_end - period_start).days + 1
    if period_days <= 0:
        raise InvalidData("El fin del periodo debe ser igual o posterior al inicio.")
    if days_without_production < 0 or days_without_production > period_days:
        raise InvalidData("Los días sin producción no pueden superar la duración del periodo.")
    if (denominator is not None and defects is not None and criterion["denominator_type"] in UNIT_DENOMINATORS
            and defects > denominator):
        raise InvalidData("Los defectos no pueden superar las unidades del denominador.")

    if denominator is None:
        reasons.append("Falta la cantidad del denominador")
    if defects is None:
        reasons.append("Falta la cantidad de defectos (un dato faltante no es cero)")
    effective_days = period_days - days_without_production
    if effective_days < criterion["min_period_days"]:
        reasons.append(f"Periodo con producción de {effective_days} día(s); se requieren {criterion['min_period_days']}")
    if denominator is not None and denominator < criterion["min_denominator"]:
        reasons.append(f"Denominador {denominator} menor que el mínimo {criterion['min_denominator']}")
    if reasons:
        return Evaluation("insufficient_data", None, reasons)

    threshold = float(criterion["threshold_value"])
    kind = criterion["threshold_type"]
    if kind == "max_defects":
        value = float(defects)
    elif denominator == 0:
        return Evaluation("insufficient_data", None, ["Denominador cero: no se puede calcular una tasa"])
    elif kind == "max_rate_ppm":
        value = defects / denominator * 1_000_000
    else:
        value = defects / denominator * 100
    result = "effective" if value <= threshold else "ineffective"
    unit = {"max_defects": "defectos", "max_rate_ppm": "ppm", "max_rate_percent": "%"}[kind]
    reasons.append(f"Resultado {value:.4g} {unit} frente a límite {threshold:.4g} {unit}")
    return Evaluation(result, value, reasons)


def allowed_decisions(computed: str) -> set[str]:
    """«Eficaz» solo si la regla lo respalda; siempre se puede ser más conservador (con justificación)."""
    if computed == "effective":
        return {"effective", "ineffective", "insufficient_data"}
    if computed == "ineffective":
        return {"ineffective", "insufficient_data"}
    return {"insufficient_data"}
