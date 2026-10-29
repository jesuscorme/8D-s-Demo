"""Reglas del flujo D0-D8 (módulo puro: sin base de datos ni HTTP).

Recibe una «instantánea» del expediente y devuelve requisitos por disciplina y si una transición
es válida. El backend la aplica antes de cada cambio de estado; el frontend solo la muestra.
"""
from dataclasses import dataclass, field

DISCIPLINES: list[tuple[str, str]] = [
    ("D0", "Preparación y respuesta de emergencia"),
    ("D1", "Formación del equipo"),
    ("D2", "Descripción del problema"),
    ("D3", "Acciones de contención"),
    ("D4", "Causa raíz y punto de escape"),
    ("D5", "Acciones correctivas permanentes"),
    ("D6", "Implementación y validación"),
    ("D7", "Prevención de recurrencia"),
    ("D8", "Cierre y reconocimiento"),
]
CODES = [c for c, _ in DISCIPLINES]
NAMES = dict(DISCIPLINES)

# Disciplinas cuyo módulo aún no existe (vacío: D0-D8 disponibles).
PENDING_MODULE: dict[str, str] = {}

# Campos narrativos (content JSONB) que acepta cada disciplina.
CONTENT_FIELDS: dict[str, set[str]] = {
    "D0": {"emergency_response", "justification"},
    "D1": {"notes"},
    "D2": {"what", "where", "when", "who", "how_detected", "is_not", "notes"},
    "D3": {"effectiveness_notes"},
    "D4": {"occurrence_cause", "escape_point", "five_whys", "notes"},
    "D5": {"verification_plan", "notes"},
    "D6": {"validation_summary", "notes"},
    "D7": {"horizontal_deployment", "no_update_justification", "no_preventive_justification", "notes"},
    "D8": {"closure_summary", "team_recognition", "notes"},
}

# Campos del caso que quedan bloqueados cuando la disciplina dueña está enviada o aprobada.
LOCKED_CASE_FIELDS: dict[str, set[str]] = {
    "D0": {"title", "severity", "source_type", "case_type", "report_date"},
    "D2": {"problem_description", "customer_name", "product_name", "part_number", "process_name",
           "lot_number", "defect_date", "detected_quantity", "affected_quantity", "market_segment", "main_defect"},
}
LOCKING_STATUSES = {"pending_review", "approved"}
ACTION_DONE = {"approved", "verified"}
ACTION_CLOSED = {"verified", "cancelled"}


@dataclass
class Snapshot:
    case: dict
    team: list[dict] = field(default_factory=list)
    content: dict[str, dict] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    containment: list[dict] = field(default_factory=list)
    causes: list[dict] = field(default_factory=list)
    issued_alerts: int = 0
    # Fases 7-9
    actions: list[dict] = field(default_factory=list)        # id, action_type, status, cause_id, responsible_user_id, due_date
    latest_checks: dict = field(default_factory=dict)       # action_id -> resultado de la última verificación decidida
    approved_criteria: int = 0
    system_updates: list[dict] = field(default_factory=list)  # status
    lessons: list[str] = field(default_factory=list)          # estados de lecciones con origen en el caso
    containment_record: dict | None = None                    # inicio/fin/resultado de la contención (D3)
    containment_lots: int = 0


class RuleError(Exception):
    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


def _text(value, minimum: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def _req(key: str, label: str, met) -> dict:
    return {"key": key, "label": label, "met": bool(met)}


def _active(s: Snapshot, *types: str) -> list[dict]:
    return [a for a in s.actions if a["action_type"] in types and a["status"] != "cancelled"]


def requirements(code: str, s: Snapshot) -> list[dict]:
    c, content = s.case, s.content.get(code, {})
    if code == "D0":
        return [
            _req("title", "Título del caso", _text(c.get("title"))),
            _req("source_type", "Origen del problema", c.get("source_type")),
            _req("severity", "Severidad", c.get("severity")),
            _req("emergency_response", "Acciones de respuesta de emergencia (ERA) o «no aplica» justificado",
                 _text(content.get("emergency_response"))),
            _req("justification", "Justificación de por qué se requiere un 8D", _text(content.get("justification"))),
        ]
    if code == "D1":
        members = {m["user_id"] for m in s.team}
        return [
            _req("owner", "Responsable del caso asignado", c.get("owner_user_id")),
            _req("leader", "Líder del equipo definido", any(m["team_role"] == "leader" for m in s.team)),
            _req("team_size", "Equipo multidisciplinario de al menos 3 integrantes", len(members) >= 3),
            _req("owner_in_team", "El responsable forma parte del equipo", c.get("owner_user_id") in members),
        ]
    if code == "D2":
        reqs = [
            _req("problem_description", "Descripción del problema (mínimo 20 caracteres)",
                 _text(c.get("problem_description"), 20)),
            _req("part_number", "Número de parte", _text(c.get("part_number"))),
            _req("defect_date", "Fecha de detección", c.get("defect_date")),
            _req("detected_quantity", "Cantidad detectada", c.get("detected_quantity") is not None),
            _req("what", "¿Qué? — defecto observado", _text(content.get("what"))),
            _req("where", "¿Dónde? — lugar de detección", _text(content.get("where"))),
            _req("when", "¿Cuándo? — momento de detección", _text(content.get("when"))),
            _req("how_detected", "¿Cómo se detectó?", _text(content.get("how_detected"))),
        ]
        if c.get("case_type") == "external":
            reqs.append(_req("customer_name", "Cliente (8D externo)", _text(c.get("customer_name"))))
        return reqs
    if code == "D3":
        active = [a for a in s.containment if a["status"] != "cancelled"]
        record = s.containment_record or {}
        return [
            _req("started", "Contención iniciada (aviso a logística con la alerta)", record.get("started_at")),
            _req("lots", "Lotes revisados registrados", s.containment_lots > 0),
            _req("ended", "Contención finalizada con resultado", record.get("ended_at") and record.get("result")),
            _req("has_actions", "Al menos una acción de contención", active),
            _req("all_verified", "Todas las acciones activas verificadas con evidencia",
                 active and all(a["status"] == "verified" and _text(a.get("evidence_notes")) for a in active)),
            _req("alert_issued", "Alerta de calidad emitida", s.issued_alerts > 0),
        ]
    if code == "D4":
        decided = {"root_cause", "not_root_cause"}
        return [
            _req("has_causes", "Causas potenciales registradas en el Ishikawa", s.causes),
            _req("root_cause", "Al menos una causa raíz validada con evidencia",
                 any(x["investigation_status"] == "root_cause" for x in s.causes)),
            _req("all_decided", "Todas las causas evaluadas (causa raíz o descartada con evidencia)",
                 s.causes and all(x["investigation_status"] in decided for x in s.causes)),
            _req("occurrence_cause", "Causa de ocurrencia descrita", _text(content.get("occurrence_cause"))),
            _req("escape_point", "Punto de escape / causa de no detección", _text(content.get("escape_point"))),
        ]
    if code == "D5":
        corrective = _active(s, "corrective")
        roots = {x["id"] for x in s.causes if x["investigation_status"] == "root_cause"}
        covered = {a["cause_id"] for a in corrective}
        return [
            _req("has_corrective", "Al menos una acción correctiva", corrective),
            _req("roots_covered", "Cada causa raíz tiene al menos una acción correctiva", roots and roots <= covered),
            _req("assigned", "Todas las acciones con responsable y fecha compromiso",
                 corrective and all(a.get("responsible_user_id") and a.get("due_date") for a in corrective)),
            _req("criteria", "Criterio de eficacia aprobado", s.approved_criteria > 0),
            _req("verification_plan", "Plan para verificar que la acción elimina la causa",
                 _text(content.get("verification_plan"))),
        ]
    if code == "D6":
        corrective = _active(s, "corrective")
        return [
            _req("implemented", "Acciones correctivas implementadas y aprobadas",
                 corrective and all(a["status"] in ACTION_DONE for a in corrective)),
            _req("effective", "Eficacia verificada («eficaz») en cada acción correctiva",
                 corrective and all(s.latest_checks.get(a["id"]) == "effective" for a in corrective)),
            _req("no_ineffective", "Ninguna acción con resultado «no eficaz» sin atender",
                 not any(a["status"] == "ineffective" for a in corrective)),
            _req("validation_summary", "Resumen de la validación", _text(content.get("validation_summary"))),
        ]
    if code == "D7":
        prevent = _active(s, "preventive", "systemic")
        updates = [u for u in s.system_updates if u["status"] != "cancelled"]
        return [
            _req("updates", "Documentos del sistema actualizados (AMEF, plan de control, instrucciones…) o justificación",
                 any(u["status"] == "completed" for u in updates) or _text(content.get("no_update_justification"))),
            _req("updates_done", "Sin actualizaciones planificadas pendientes", all(u["status"] == "completed" for u in updates)),
            _req("preventive", "Acción preventiva o sistémica aprobada, o justificación",
                 any(a["status"] in ACTION_DONE for a in prevent) or _text(content.get("no_preventive_justification"))),
            _req("preventive_done", "Acciones preventivas/sistémicas aprobadas", all(a["status"] in ACTION_DONE for a in prevent)),
            _req("horizontal_deployment", "Despliegue horizontal (otras líneas, productos o plantas)",
                 _text(content.get("horizontal_deployment"))),
        ]
    if code == "D8":
        return [
            _req("lesson", "Lección aprendida aprobada o publicada", any(x in ("approved", "published") for x in s.lessons)),
            _req("actions_closed", "Acciones correctivas verificadas o canceladas",
                 all(a["status"] in ACTION_CLOSED for a in _active(s, "corrective"))),
            _req("closure_summary", "Resumen de cierre", _text(content.get("closure_summary"))),
            _req("team_recognition", "Reconocimiento al equipo", _text(content.get("team_recognition"))),
        ]
    return [_req("module", f"Módulo no disponible en esta versión ({PENDING_MODULE.get(code, '')})", False)]


def evaluate(s: Snapshot) -> list[dict]:
    result = []
    for i, code in enumerate(CODES):
        reqs = requirements(code, s)
        status = s.status.get(code, "not_started")
        previous_ok = i == 0 or s.status.get(CODES[i - 1]) == "approved"
        blockers = []
        if not previous_ok:
            blockers.append(f"Requiere {CODES[i - 1]} aprobada")
        blockers += [r["label"] for r in reqs if not r["met"]]
        result.append({
            "code": code, "name": NAMES[code], "status": status, "available": code not in PENDING_MODULE,
            "requirements": reqs, "pending_count": sum(1 for r in reqs if not r["met"]),
            "can_submit": status in ("not_started", "in_progress") and not blockers,
            "blockers": blockers,
        })
    return result


def check_edit(code: str, s: Snapshot) -> None:
    """Se puede editar una disciplina solo en borrador/en curso."""
    check_case_open(s)
    if code in PENDING_MODULE:
        raise RuleError("module_unavailable", f"{code} aún no está disponible ({PENDING_MODULE[code]}).")
    if s.status.get(code, "not_started") in LOCKING_STATUSES:
        raise RuleError("discipline_locked", f"{code} está enviada o aprobada; reábrela para editar.")


def check_submit(code: str, s: Snapshot) -> None:
    check_case_open(s)
    item = next(d for d in evaluate(s) if d["code"] == code)
    if item["status"] not in ("not_started", "in_progress"):
        raise RuleError("invalid_transition", f"{code} no está en curso.")
    if item["blockers"]:
        raise RuleError("requirements_pending", f"{code} tiene requisitos pendientes.", item["blockers"])


def check_review(code: str, s: Snapshot) -> None:
    check_case_open(s)
    if s.status.get(code) != "pending_review":
        raise RuleError("invalid_transition", f"{code} no está pendiente de revisión.")


def check_approve(code: str, s: Snapshot) -> None:
    check_review(code, s)
    # Los requisitos pueden haber cambiado mientras estaba en revisión (p. ej. una acción cancelada).
    pending = [r["label"] for r in requirements(code, s) if not r["met"]]
    if pending:
        raise RuleError("requirements_pending", f"{code} ya no cumple sus requisitos.", pending)


def check_reopen(code: str, s: Snapshot) -> None:
    # Un caso cerrado solo se reabre reabriendo D8.
    if not (code == "D8" and s.case.get("status") == "closed"):
        check_case_open(s)
    if s.status.get(code) != "approved":
        raise RuleError("invalid_transition", f"{code} no está aprobada.")
    i = CODES.index(code)
    later = [c for c in CODES[i + 1:] if s.status.get(c) in LOCKING_STATUSES]
    if later:
        raise RuleError("later_disciplines", f"Reabre primero {later[-1]}: las disciplinas posteriores dependen de {code}.")


def locked_fields(s: Snapshot) -> set[str]:
    fields: set[str] = set()
    for code, names in LOCKED_CASE_FIELDS.items():
        if s.status.get(code) in LOCKING_STATUSES:
            fields |= names
    return fields


def section_locked(code: str, s: Snapshot) -> bool:
    """Las secciones de trabajo se congelan al enviar/aprobar su disciplina."""
    return s.status.get(code) in LOCKING_STATUSES


def case_status_after(s: Snapshot) -> str:
    if s.case.get("status") == "cancelled":
        return "cancelled"
    if s.status.get("D8") == "approved":
        return "closed"
    if any(s.status.get(c) == "pending_review" for c in CODES):
        return "pending_review"
    if s.status.get("D0") == "approved":
        return "in_progress"
    if any(s.status.get(c, "not_started") != "not_started" for c in CODES):
        return "open"
    return "draft"


# Hitos del concentrado de 8D: plazo en días naturales desde la fecha de reporte y la disciplina que lo cumple.
MILESTONES: list[tuple[str, str, str, int]] = [
    ("containment", "D3 · Contención (24 h)", "D3", 1),
    ("root_cause", "D4 · Causa raíz (48 h)", "D4", 2),
    ("actions", "D5–D7 · Acciones (7 días)", "D7", 7),
    ("close", "D8 · Validación y cierre (14 días)", "D8", 14),
]


def milestone_status(report_date, approved_on, today, days: int) -> dict:
    """on_time / late (cumplido tarde) / pending (en plazo) / overdue (vencido sin cumplir)."""
    from datetime import timedelta
    due = report_date + timedelta(days=days)
    if approved_on:
        status = "on_time" if approved_on <= due else "late"
    else:
        status = "overdue" if today > due else "pending"
    return {"due": due, "done": approved_on, "status": status}


def milestones(report_date, approved: dict, today) -> list[dict]:
    """approved: código de disciplina → fecha de aprobación (date) o None."""
    return [{"key": key, "label": label, **milestone_status(report_date, approved.get(code), today, days)}
            for key, label, code, days in MILESTONES]


def check_case_open(s: Snapshot) -> None:
    if s.case.get("status") in ("cancelled", "closed"):
        raise RuleError("case_closed", "El caso está cerrado o cancelado.")
