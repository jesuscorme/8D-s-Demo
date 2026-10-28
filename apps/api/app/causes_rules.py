"""Reglas puras de investigación de causas: sugerencias del catálogo y hallazgo de procedimiento.

Las sugerencias son hipótesis para el equipo, nunca conclusiones. La causa raíz solo se confirma
con una validación que incluya método, evidencia y justificación.
"""
import re
import unicodedata


def normalize(text: str | None) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def suggest(case_text: dict[str, str | None], ideas: list[dict], used_idea_ids: set, limit: int = 10) -> list[dict]:
    """Puntúa ideas por coincidencia de etiquetas de proceso/defecto con el texto del caso."""
    process = f" {normalize(case_text.get('process'))} "
    defect = f" {normalize(' '.join(v or '' for k, v in case_text.items() if k != 'process'))} "
    scored = []
    for idea in ideas:
        if idea["id"] in used_idea_ids:
            continue
        reasons = []
        for tag in idea.get("process_tags") or []:
            if f" {normalize(tag)} " in process or f" {normalize(tag)} " in defect:
                reasons.append(f"proceso: {tag}")
        for tag in idea.get("defect_tags") or []:
            if f" {normalize(tag.replace('_', ' '))} " in defect:
                reasons.append(f"defecto: {tag}")
        if reasons:
            scored.append({**idea, "score": len(reasons), "reasons": reasons})
    scored.sort(key=lambda x: (-x["score"], x["title_es"]))
    return scored[:limit]


def procedure_finding(documented: str, followed: str) -> dict | None:
    """Distingue procedimiento inexistente/inadecuado de incumplimiento de uno existente (principio 3)."""
    if documented == "no":
        return {"code": "procedure_missing",
                "label": "Procedimiento inexistente o inadecuado",
                "hint": "La acción debe corregir el sistema: documentar o estandarizar el método."}
    if documented == "yes" and followed == "no":
        return {"code": "procedure_not_followed",
                "label": "Incumplimiento de un procedimiento existente",
                "hint": "Investigar por qué no se siguió (capacitación, diseño del método, factores humanos)."}
    if documented == "yes" and followed == "yes":
        return {"code": "procedure_followed",
                "label": "Procedimiento existente y seguido",
                "hint": "Evaluar si el procedimiento es adecuado para prevenir el defecto."}
    return None
