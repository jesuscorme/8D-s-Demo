"""D5-D7: acciones correctivas/preventivas/sistémicas, actualizaciones del sistema y eficacia (D6)."""
from datetime import date
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, effectiveness_rules
from app.auth import Principal, get_conn, require
from app.cases import ensure_section_editable, load_case, refresh_case_status, same_org_user, touch
from app.errors import ApiError, invalid, not_found

router = APIRouter(tags=["actions"])

ActionType = Literal["corrective", "preventive", "systemic"]
# Disciplina que congela la definición y la ejecución de cada tipo de acción.
DEFINE_LOCK = {"corrective": ("D5", "Las acciones correctivas"), "preventive": ("D7", "Las acciones preventivas"),
               "systemic": ("D7", "Las acciones sistémicas")}
EXECUTE_LOCK = {"corrective": ("D6", "La implementación"), "preventive": ("D7", "Las acciones preventivas"),
                "systemic": ("D7", "Las acciones sistémicas")}


class ActionIn(BaseModel):
    action_type: ActionType
    cause_id: UUID | None = None
    description: str = Field(min_length=3, max_length=2000)
    responsible_user_id: UUID | None = None
    due_date: date | None = None


class ActionPatch(BaseModel):
    cause_id: UUID | None = None
    description: str | None = Field(None, min_length=3, max_length=2000)
    responsible_user_id: UUID | None = None
    due_date: date | None = None


class SubmitIn(BaseModel):
    implementation_evidence: str | None = Field(None, max_length=4000)
    evidence_exception: str | None = Field(None, max_length=2000)


class CommentIn(BaseModel):
    comment: str | None = Field(None, max_length=2000)


class CancelIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class UpdateIn(BaseModel):
    update_type: Literal["pfmea", "dfmea", "control_plan", "work_instruction", "visual_aid", "training", "other"]
    document_reference: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    responsible_user_id: UUID | None = None
    action_id: UUID | None = None


class UpdatePatch(BaseModel):
    status: Literal["planned", "completed", "cancelled"] | None = None
    completed_on: date | None = None
    evidence_notes: str | None = Field(None, max_length=4000)
    description: str | None = Field(None, max_length=2000)
    responsible_user_id: UUID | None = None


class CriterionIn(BaseModel):
    description: str = Field(min_length=3, max_length=1000)
    metric_name: str = Field(min_length=1, max_length=200)
    defect_unit: str = Field(min_length=1, max_length=100)
    denominator_type: Literal["units_produced", "units_inspected", "lots_received", "shipments", "other"]
    denominator_label: str | None = Field(None, max_length=100)
    threshold_type: Literal["max_defects", "max_rate_ppm", "max_rate_percent"]
    threshold_value: float = Field(ge=0, le=1_000_000)
    min_period_days: int = Field(ge=1, le=730)
    min_denominator: int = Field(1, ge=1)


class CheckIn(BaseModel):
    criterion_id: UUID
    period_start: date
    period_end: date
    denominator_quantity: int | None = Field(None, ge=0)
    defect_quantity: int | None = Field(None, ge=0)
    days_without_production: int = Field(0, ge=0)
    data_notes: str | None = Field(None, max_length=2000)
    responsible_user_id: UUID | None = None


class DecideIn(BaseModel):
    result: Literal["effective", "ineffective", "insufficient_data"]
    rationale: str = Field(min_length=5, max_length=2000)


# ---- Acciones -------------------------------------------------------------------------------

def _actions(conn, case_id: UUID) -> list[dict]:
    return conn.execute(
        """select a.*, c.potential_cause as cause_text, c.investigation_status as cause_status,
                  u.display_name as responsible_name, ap.display_name as approved_by_name,
                  sb.display_name as submitted_by_name,
                  (a.due_date < current_date and a.status in ('open','in_progress')) as overdue,
                  (select count(*)::int from attachments f where f.action_id = a.id) as attachment_count,
                  (select e.result from effectiveness_checks e where e.action_id = a.id and e.result <> 'pending'
                    order by e.decided_at desc limit 1) as latest_effectiveness
           from corrective_actions a left join ishikawa_causes c on c.id = a.cause_id
           left join users u on u.id = a.responsible_user_id left join users ap on ap.id = a.approved_by
           left join users sb on sb.id = a.submitted_by
           where a.case_id = %s order by a.action_type, a.created_at""", (case_id,)).fetchall()


def _load_action(conn, p: Principal, action_id: UUID) -> tuple[dict, dict]:
    action = conn.execute("select * from corrective_actions where id = %s and organization_id = %s for update",
                          (action_id, p.organization_id)).fetchone()
    if not action:
        raise not_found("Acción")
    return action, load_case(conn, p, action["case_id"], for_update=True)


def _check_cause(conn, case_id: UUID, action_type: str, cause_id: UUID | None) -> None:
    if cause_id is None:
        if action_type == "corrective":
            raise invalid("Una acción correctiva debe vincularse a una causa raíz.")
        return
    cause = conn.execute("select investigation_status from ishikawa_causes where id = %s and case_id = %s",
                         (cause_id, case_id)).fetchone()
    if not cause:
        raise invalid("La causa no pertenece al caso.")
    if action_type == "corrective" and cause["investigation_status"] != "root_cause":
        raise ApiError(409, "cause_not_root", "Las acciones correctivas solo se vinculan a causas raíz confirmadas.")


@router.get("/cases/{case_id}/actions")
def list_actions(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _actions(conn, case_id)


@router.post("/cases/{case_id}/actions", status_code=201)
def create_action(case_id: UUID, body: ActionIn, p: Principal = Depends(require("action.edit")),
                  conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    code, label = DEFINE_LOCK[body.action_type]
    ensure_section_editable(conn, case, code, label)
    _check_cause(conn, case_id, body.action_type, body.cause_id)
    same_org_user(conn, p, body.responsible_user_id)
    data = body.model_dump()
    row = conn.execute(
        f"""insert into corrective_actions (organization_id, case_id, created_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case_id, p.user_id, *data.values()]).fetchone()
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = %s and status = 'not_started'""", (case_id, code))
    touch(conn, case_id)
    audit.record(conn, p, "action.created", "corrective_action", row["id"], case_id, new=data)
    refresh_case_status(conn, case_id)
    return _actions(conn, case_id)


@router.patch("/actions/{action_id}")
def update_action(action_id: UUID, body: ActionPatch, p: Principal = Depends(require("action.edit")),
                  conn: psycopg.Connection = Depends(get_conn)):
    action, case = _load_action(conn, p, action_id)
    ensure_section_editable(conn, case, *DEFINE_LOCK[action["action_type"]])
    if action["status"] not in ("open", "in_progress"):
        raise ApiError(409, "action_locked", "Solo se edita una acción abierta o en curso.")
    changes = body.model_dump(exclude_unset=True)
    if "cause_id" in changes:
        _check_cause(conn, case["id"], action["action_type"], changes["cause_id"])
    if "responsible_user_id" in changes:
        same_org_user(conn, p, changes["responsible_user_id"])
    if "description" in changes and not changes["description"]:
        raise invalid("La descripción es obligatoria.")
    old, new = audit.diff(action, changes)
    if new:
        conn.execute(f"update corrective_actions set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), action_id])
        touch(conn, case["id"])
        audit.record(conn, p, "action.updated", "corrective_action", action_id, case["id"], old=old, new=new)
    return _actions(conn, case["id"])


def _transition(conn, p: Principal, action_id: UUID, allowed_from: set[str], to: str, event: str,
                sets: str = "", args: list | None = None) -> list[dict]:
    action, case = _load_action(conn, p, action_id)
    ensure_section_editable(conn, case, *EXECUTE_LOCK[action["action_type"]])
    if action["status"] not in allowed_from:
        raise ApiError(409, "invalid_transition", f"No se puede pasar de «{action['status']}» a «{to}».")
    conn.execute(f"update corrective_actions set status = %s{sets}, updated_at = now() where id = %s",
                 [to, *(args or []), action_id])
    touch(conn, case["id"])
    audit.record(conn, p, event, "corrective_action", action_id, case["id"], old={"status": action["status"]},
                 new={"status": to, **({"args": [str(a) for a in args]} if args else {})})
    refresh_case_status(conn, case["id"])
    return _actions(conn, case["id"])


@router.post("/actions/{action_id}/start")
def start(action_id: UUID, p: Principal = Depends(require("action.edit")), conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, action_id, {"open"}, "in_progress", "action.started")


@router.post("/actions/{action_id}/submit")
def submit(action_id: UUID, body: SubmitIn, p: Principal = Depends(require("action.edit")),
           conn: psycopg.Connection = Depends(get_conn)):
    evidence = (body.implementation_evidence or "").strip() or None
    exception = (body.evidence_exception or "").strip() or None
    if not evidence and not exception:
        raise ApiError(409, "evidence_required", "La implementación requiere evidencia o una excepción justificada.")
    return _transition(conn, p, action_id, {"open", "in_progress"}, "pending_approval", "action.submitted",
                       ", implementation_evidence = %s, evidence_exception = %s, implemented_at = now(), submitted_by = %s,"
                       " review_comment = null", [evidence, exception, p.user_id])


@router.post("/actions/{action_id}/approve")
def approve(action_id: UUID, body: CommentIn, p: Principal = Depends(require("action.approve")),
            conn: psycopg.Connection = Depends(get_conn)):
    action = conn.execute("select submitted_by from corrective_actions where id = %s and organization_id = %s",
                          (action_id, p.organization_id)).fetchone()
    if action and action["submitted_by"] == p.user_id:
        # Segregación de funciones: quien declara implementada la acción no la aprueba.
        raise ApiError(409, "same_person", "La aprobación debe hacerla una persona distinta a quien envió la acción.")
    return _transition(conn, p, action_id, {"pending_approval"}, "approved", "action.approved",
                       ", approved_by = %s, approved_at = now(), review_comment = %s", [p.user_id, body.comment])


@router.post("/actions/{action_id}/reject")
def reject(action_id: UUID, body: CommentIn, p: Principal = Depends(require("action.approve")),
           conn: psycopg.Connection = Depends(get_conn)):
    if not (body.comment and body.comment.strip()):
        raise invalid("Indica el motivo del rechazo.")
    return _transition(conn, p, action_id, {"pending_approval"}, "in_progress", "action.rejected",
                       ", review_comment = %s", [body.comment.strip()])


@router.post("/actions/{action_id}/reopen")
def reopen(action_id: UUID, body: CommentIn, p: Principal = Depends(require("action.approve")),
           conn: psycopg.Connection = Depends(get_conn)):
    if not (body.comment and body.comment.strip()):
        raise invalid("Indica el motivo de la reapertura.")
    return _transition(conn, p, action_id, {"approved", "ineffective"}, "in_progress", "action.reopened",
                       ", approved_by = null, approved_at = null, review_comment = %s", [body.comment.strip()])


@router.post("/actions/{action_id}/cancel")
def cancel(action_id: UUID, body: CancelIn, p: Principal = Depends(require("action.approve")),
           conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, action_id, {"open", "in_progress", "pending_approval", "ineffective"}, "cancelled",
                       "action.cancelled", ", cancel_reason = %s", [body.reason.strip()])


# ---- Actualizaciones del sistema (D7) ---------------------------------------------------------

def _updates(conn, case_id: UUID) -> list[dict]:
    return conn.execute(
        """select s.*, u.display_name as responsible_name,
                  (select count(*)::int from attachments f where f.system_update_id = s.id) as attachment_count
           from system_updates s left join users u on u.id = s.responsible_user_id
           where s.case_id = %s order by s.created_at""", (case_id,)).fetchall()


@router.get("/cases/{case_id}/system-updates")
def list_updates(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _updates(conn, case_id)


@router.post("/cases/{case_id}/system-updates", status_code=201)
def create_update(case_id: UUID, body: UpdateIn, p: Principal = Depends(require("action.edit")),
                  conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D7", "Las actualizaciones del sistema")
    same_org_user(conn, p, body.responsible_user_id)
    if body.action_id and not conn.execute("select 1 from corrective_actions where id = %s and case_id = %s",
                                           (body.action_id, case_id)).fetchone():
        raise invalid("La acción no pertenece al caso.")
    data = body.model_dump()
    row = conn.execute(
        f"""insert into system_updates (organization_id, case_id, created_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case_id, p.user_id, *data.values()]).fetchone()
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = 'D7' and status = 'not_started'""", (case_id,))
    touch(conn, case_id)
    audit.record(conn, p, "system_update.created", "system_update", row["id"], case_id, new=data)
    refresh_case_status(conn, case_id)
    return _updates(conn, case_id)


@router.patch("/system-updates/{update_id}")
def patch_update(update_id: UUID, body: UpdatePatch, p: Principal = Depends(require("action.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("select * from system_updates where id = %s and organization_id = %s for update",
                       (update_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Actualización")
    case = load_case(conn, p, row["case_id"], for_update=True)
    ensure_section_editable(conn, case, "D7", "Las actualizaciones del sistema")
    if row["status"] != "planned":
        raise ApiError(409, "update_closed", "La actualización ya está completada o cancelada.")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") == "completed":
        if not changes.get("completed_on", row["completed_on"]) or not (changes.get("evidence_notes") or row["evidence_notes"] or "").strip():
            raise ApiError(409, "evidence_required", "Completar exige fecha y evidencia (referencia a la nueva revisión).")
    if "responsible_user_id" in changes:
        same_org_user(conn, p, changes["responsible_user_id"])
    old, new = audit.diff(row, changes)
    if new:
        conn.execute(f"update system_updates set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), update_id])
        touch(conn, row["case_id"])
        audit.record(conn, p, "system_update.updated", "system_update", update_id, row["case_id"], old=old, new=new)
    return _updates(conn, row["case_id"])


# ---- Eficacia (D6) ----------------------------------------------------------------------------

def _effectiveness(conn, case_id: UUID) -> dict:
    criteria = conn.execute(
        """select k.*, u.display_name as approved_by_name from effectiveness_criteria k
           left join users u on u.id = k.approved_by where k.case_id = %s order by k.created_at""", (case_id,)).fetchall()
    by_id = {k["id"]: k for k in criteria}
    checks = conn.execute(
        """select e.*, a.description as action_description, a.action_type, d.display_name as decided_by_name,
                  r.display_name as responsible_name,
                  (select count(*)::int from attachments f where f.effectiveness_check_id = e.id) as attachment_count
           from effectiveness_checks e join corrective_actions a on a.id = e.action_id
           left join users d on d.id = e.decided_by left join users r on r.id = e.responsible_user_id
           where e.case_id = %s order by e.created_at desc""", (case_id,)).fetchall()
    for c in checks:
        ev = effectiveness_rules.evaluate(by_id[c["criterion_id"]], c["period_start"], c["period_end"],
                                          c["denominator_quantity"], c["defect_quantity"], c["days_without_production"])
        c["evaluation"] = {"result": ev.result, "value": ev.value, "reasons": ev.reasons}
        c["allowed_decisions"] = sorted(effectiveness_rules.allowed_decisions(c["computed_result"]))
    return {"criteria": criteria, "checks": checks, "denominators": effectiveness_rules.DENOMINATORS}


@router.get("/cases/{case_id}/effectiveness")
def effectiveness(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _effectiveness(conn, case_id)


@router.post("/cases/{case_id}/criteria", status_code=201)
def create_criterion(case_id: UUID, body: CriterionIn, p: Principal = Depends(require("effectiveness.edit")),
                     conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D6", "La verificación de eficacia")
    if body.denominator_type == "other" and not (body.denominator_label or "").strip():
        raise invalid("Describe el denominador cuando eliges «otro».")
    if body.threshold_type == "max_rate_percent" and body.threshold_value > 100:
        raise invalid("Un porcentaje no puede superar 100.")
    data = body.model_dump()
    row = conn.execute(
        f"""insert into effectiveness_criteria (organization_id, case_id, created_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case_id, p.user_id, *data.values()]).fetchone()
    audit.record(conn, p, "criterion.created", "effectiveness_criterion", row["id"], case_id, new=data)
    return _effectiveness(conn, case_id)


def _criterion_status(conn, p: Principal, criterion_id: UUID, allowed_from: str, to: str, event: str) -> dict:
    row = conn.execute("select * from effectiveness_criteria where id = %s and organization_id = %s for update",
                       (criterion_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Criterio")
    case = load_case(conn, p, row["case_id"], for_update=True)
    ensure_section_editable(conn, case, "D6", "La verificación de eficacia")
    if row["status"] != allowed_from:
        raise ApiError(409, "invalid_transition", f"El criterio no está en «{allowed_from}».")
    extra = ", approved_by = %s, approved_at = now()" if to == "approved" else ""
    conn.execute(f"update effectiveness_criteria set status = %s{extra} where id = %s",
                 [to, *([p.user_id] if extra else []), criterion_id])
    audit.record(conn, p, event, "effectiveness_criterion", criterion_id, row["case_id"],
                 old={"status": row["status"]}, new={"status": to})
    refresh_case_status(conn, row["case_id"])
    return _effectiveness(conn, row["case_id"])


@router.post("/criteria/{criterion_id}/approve")
def approve_criterion(criterion_id: UUID, p: Principal = Depends(require("criteria.approve")),
                      conn: psycopg.Connection = Depends(get_conn)):
    return _criterion_status(conn, p, criterion_id, "draft", "approved", "criterion.approved")


@router.post("/criteria/{criterion_id}/retire")
def retire_criterion(criterion_id: UUID, p: Principal = Depends(require("criteria.approve")),
                     conn: psycopg.Connection = Depends(get_conn)):
    return _criterion_status(conn, p, criterion_id, "approved", "retired", "criterion.retired")


@router.post("/actions/{action_id}/checks", status_code=201)
def create_check(action_id: UUID, body: CheckIn, p: Principal = Depends(require("effectiveness.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    action, case = _load_action(conn, p, action_id)
    ensure_section_editable(conn, case, "D6", "La verificación de eficacia")
    if action["status"] not in ("approved", "verified", "ineffective"):
        raise ApiError(409, "not_implemented", "La eficacia se verifica sobre acciones implementadas y aprobadas.")
    criterion = conn.execute("select * from effectiveness_criteria where id = %s and case_id = %s",
                             (body.criterion_id, case["id"])).fetchone()
    if not criterion:
        raise invalid("El criterio no pertenece al caso.")
    if criterion["status"] != "approved":
        raise ApiError(409, "criterion_not_approved", "El criterio de aceptación debe estar aprobado.")
    if body.period_end > date.today():
        raise invalid("El periodo no puede terminar en el futuro.")
    same_org_user(conn, p, body.responsible_user_id)
    try:
        ev = effectiveness_rules.evaluate(criterion, body.period_start, body.period_end, body.denominator_quantity,
                                          body.defect_quantity, body.days_without_production)
    except effectiveness_rules.InvalidData as exc:
        raise invalid(str(exc)) from None
    data = body.model_dump()
    row = conn.execute(
        f"""insert into effectiveness_checks (organization_id, case_id, action_id, created_by, computed_result,
                                              {', '.join(data)})
            values (%s, %s, %s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case["id"], action_id, p.user_id, ev.result, *data.values()]).fetchone()
    touch(conn, case["id"])
    audit.record(conn, p, "effectiveness.recorded", "effectiveness_check", row["id"], case["id"],
                 new={**data, "computed_result": ev.result})
    return _effectiveness(conn, case["id"])


@router.post("/checks/{check_id}/decide")
def decide(check_id: UUID, body: DecideIn, p: Principal = Depends(require("effectiveness.edit")),
           conn: psycopg.Connection = Depends(get_conn)):
    check = conn.execute("select * from effectiveness_checks where id = %s and organization_id = %s for update",
                         (check_id, p.organization_id)).fetchone()
    if not check:
        raise not_found("Verificación")
    case = load_case(conn, p, check["case_id"], for_update=True)
    ensure_section_editable(conn, case, "D6", "La verificación de eficacia")
    if check["result"] != "pending":
        raise ApiError(409, "already_decided", "La verificación ya tiene resultado; registra una nueva.")
    allowed = effectiveness_rules.allowed_decisions(check["computed_result"])
    if body.result not in allowed:
        raise ApiError(409, "result_not_supported",
                       "Los datos no respaldan ese resultado (los datos faltantes nunca cuentan como cero defectos).",
                       sorted(allowed))
    conn.execute("""update effectiveness_checks set result = %s, rationale = %s, decided_by = %s, decided_at = now()
                    where id = %s""", (body.result, body.rationale.strip(), p.user_id, check_id))
    action_status = {"effective": "verified", "ineffective": "ineffective"}.get(body.result)
    if action_status:
        conn.execute("""update corrective_actions set status = %s, updated_at = now()
                        where id = %s and status in ('approved', 'verified', 'ineffective')""",
                     (action_status, check["action_id"]))
    touch(conn, case["id"])
    audit.record(conn, p, "effectiveness.decided", "effectiveness_check", check_id, case["id"],
                 old={"result": "pending"}, new={"result": body.result, "rationale": body.rationale.strip(),
                                                 "action_status": action_status})
    refresh_case_status(conn, case["id"])
    return _effectiveness(conn, case["id"])
