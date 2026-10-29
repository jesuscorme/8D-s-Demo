"""D3: acciones de contención y archivos adjuntos (evidencias y fotos)."""
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import audit, notify, storage, workflow
from app.db import setting
from app.auth import Principal, get_conn, require
from app.cases import ensure_section_editable, load_case, refresh_case_status, rule, same_org_user, snapshot, touch
from app.errors import ApiError, invalid, not_found

router = APIRouter(tags=["containment"])

Status = Literal["open", "in_progress", "implemented", "verified", "cancelled"]
# Transiciones permitidas; «verified» es final y solo se sale reabriendo D3 y cancelando.
TRANSITIONS = {
    "open": {"in_progress", "implemented", "cancelled"},
    "in_progress": {"open", "implemented", "cancelled"},
    "implemented": {"in_progress", "verified", "cancelled"},
    "verified": {"cancelled"},
    "cancelled": set(),
}


class ContainmentIn(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    location: str | None = Field(None, max_length=200)
    responsible_user_id: UUID | None = None
    due_date: date | None = None
    quantity_checked: int | None = Field(None, ge=0)
    quantity_rejected: int | None = Field(None, ge=0)


class ContainmentPatch(BaseModel):
    description: str | None = Field(None, min_length=3, max_length=2000)
    location: str | None = Field(None, max_length=200)
    responsible_user_id: UUID | None = None
    due_date: date | None = None
    quantity_checked: int | None = Field(None, ge=0)
    quantity_rejected: int | None = Field(None, ge=0)
    evidence_notes: str | None = Field(None, max_length=4000)
    status: Status | None = None


def _quantities_ok(checked, rejected) -> None:
    if checked is not None and rejected is not None and rejected > checked:
        raise invalid("Las piezas rechazadas no pueden superar las revisadas.")


def _list(conn, case_id: UUID) -> list[dict]:
    return conn.execute(
        """select a.*, u.display_name as responsible_name, v.display_name as verified_by_name,
                  (a.due_date < current_date and a.status not in ('verified','cancelled')) as overdue,
                  (select count(*)::int from attachments f where f.containment_id = a.id) as attachment_count
           from containment_actions a left join users u on u.id = a.responsible_user_id
           left join users v on v.id = a.verified_by where a.case_id = %s order by a.created_at""",
        (case_id,)).fetchall()


@router.get("/cases/{case_id}/containment")
def list_containment(case_id: UUID, p: Principal = Depends(require("case.read")),
                     conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _list(conn, case_id)


@router.post("/cases/{case_id}/containment", status_code=201)
def create_containment(case_id: UUID, body: ContainmentIn, p: Principal = Depends(require("containment.edit")),
                       conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D3", "La contención")
    same_org_user(conn, p, body.responsible_user_id)
    _quantities_ok(body.quantity_checked, body.quantity_rejected)
    data = body.model_dump()
    row = conn.execute(
        f"""insert into containment_actions (organization_id, case_id, created_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case_id, p.user_id, *data.values()]).fetchone()
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = 'D3' and status = 'not_started'""", (case_id,))
    touch(conn, case_id)
    audit.record(conn, p, "containment.created", "containment_action", row["id"], case_id, new=data)
    refresh_case_status(conn, case_id)
    return _list(conn, case_id)


@router.patch("/containment/{action_id}")
def update_containment(action_id: UUID, body: ContainmentPatch, p: Principal = Depends(require("containment.edit")),
                       conn: psycopg.Connection = Depends(get_conn)):
    action = conn.execute("select * from containment_actions where id = %s and organization_id = %s for update",
                          (action_id, p.organization_id)).fetchone()
    if not action:
        raise not_found("Acción de contención")
    case = load_case(conn, p, action["case_id"], for_update=True)
    ensure_section_editable(conn, case, "D3", "La contención")
    changes = body.model_dump(exclude_unset=True)
    if action["status"] in ("verified", "cancelled") and set(changes) - {"status"}:
        raise ApiError(409, "action_closed", "La acción está verificada o cancelada; ya no se edita.")
    target = changes.get("status")
    if target and target != action["status"]:
        if target not in TRANSITIONS[action["status"]]:
            raise ApiError(409, "invalid_transition", f"No se puede pasar de «{action['status']}» a «{target}».")
        evidence = changes.get("evidence_notes", action["evidence_notes"])
        if target in ("implemented", "verified") and not (evidence and evidence.strip()):
            raise ApiError(409, "evidence_required", "Describe la evidencia antes de marcarla implementada o verificada.")
    if "responsible_user_id" in changes:
        same_org_user(conn, p, changes["responsible_user_id"])
    _quantities_ok(changes.get("quantity_checked", action["quantity_checked"]),
                   changes.get("quantity_rejected", action["quantity_rejected"]))
    old, new = audit.diff(action, changes)
    if new:
        sets = [f"{k} = %s" for k in new]
        values = list(new.values())
        if new.get("status") == "implemented":
            sets.append("implemented_at = now()")
        if new.get("status") == "verified":
            sets += ["verified_at = now()", "verified_by = %s"]
            values.append(p.user_id)
        conn.execute(f"update containment_actions set {', '.join(sets)}, updated_at = now() where id = %s",
                     [*values, action_id])
        touch(conn, action["case_id"])
        audit.record(conn, p, "containment.updated", "containment_action", action_id, action["case_id"], old=old, new=new)
    return _list(conn, action["case_id"])


# ---- Registro de contención (inicio, lotes, fin y resultado) ------------------------------------

class StartIn(BaseModel):
    started_at: datetime | None = None


class LotIn(BaseModel):
    lot_number: str = Field(min_length=1, max_length=100)
    location: str | None = Field(None, max_length=200)
    quantity_inspected: int = Field(ge=0, le=100_000_000)
    quantity_rejected: int = Field(0, ge=0, le=100_000_000)
    disposition: Literal["released", "rework", "scrap", "returned", "on_hold"] | None = None
    notes: str | None = Field(None, max_length=1000)


class EndIn(BaseModel):
    result: Literal["effective", "not_effective"]
    result_notes: str = Field(min_length=5, max_length=2000)
    ended_at: datetime | None = None


def _record(conn, case_id: UUID) -> dict:
    record = conn.execute(
        """select r.*, s.display_name as started_by_name, e.display_name as ended_by_name from case_containment r
           join users s on s.id = r.started_by left join users e on e.id = r.ended_by where r.case_id = %s""",
        (case_id,)).fetchone()
    lots = conn.execute(
        """select l.*, u.display_name as created_by_name from containment_lots l join users u on u.id = l.created_by
           where l.case_id = %s order by l.created_at""", (case_id,)).fetchall()
    inspected = sum(x["quantity_inspected"] for x in lots)
    rejected = sum(x["quantity_rejected"] for x in lots)
    emails = conn.execute(
        """select id, event, to_addresses, subject, status, last_error, created_at, sent_at, transport from email_outbox
           where case_id = %s order by created_at desc""", (case_id,)).fetchall()
    return {"record": record, "lots": lots, "emails": emails,
            "totals": {"lots": len(lots), "inspected": inspected, "rejected": rejected, "ok": inspected - rejected}}


def _issued_alert_documents(conn, case_id: UUID) -> list[dict]:
    return conn.execute(
        """select d.id as document_id, d.file_name from quality_alerts a join documents d on d.alert_id = a.id
           where a.case_id = %s and a.status = 'issued' and d.status = 'issued' order by a.alert_number""",
        (case_id,)).fetchall()


def queue_logistics_email(conn, p: Principal, case: dict, record: dict) -> UUID:
    """Aviso a logística: detener el material para re-inspección, con la alerta de calidad vigente en PDF."""
    docs = _issued_alert_documents(conn, case["id"])
    if not docs:
        raise ApiError(409, "alert_required", "Emite primero la alerta de calidad: se adjunta en PDF al aviso a logística.")
    to = notify.recipients(conn, p.organization_id, case["plant_id"], "containment_started")
    if not to:
        raise ApiError(409, "no_recipients", "No hay correos de logística configurados. Agrégalos en Administración › Notificaciones.")
    owner = conn.execute("select email from users where id = %s", (case["owner_user_id"],)).fetchone()
    plant = conn.execute("select code, name from plants where id = %s", (case["plant_id"],)).fetchone()
    kind = "Externo (reclamación del cliente)" if case["case_type"] == "external" else "Interno"
    link = f"{setting('APP_BASE_URL', 'http://localhost:3010').rstrip('/')}/casos/{case['id']}"
    text, body = notify.render(
        f"Detener material para re-inspección — {case['folio']}",
        f"Se inició la contención del 8D {case['folio']}. Detengan el material indicado en almacén, tránsito y embarques "
        "hasta su re-inspección y liberación por calidad.",
        [("Folio", case["folio"]), ("Tipo de 8D", kind), ("Problema", case["title"]),
         ("Cliente", case["customer_name"] or "—"), ("Número de parte", case["part_number"] or "—"),
         ("Producto", case["product_name"] or "—"), ("Lote", case["lot_number"] or "—"),
         ("Cantidad afectada", f"{case['affected_quantity']:,}" if case["affected_quantity"] is not None else "—"),
         ("Planta", f"{plant['code']} — {plant['name']}"),
         ("Inicio de contención", record["started_at"].strftime("%Y-%m-%d %H:%M")), ("Inició", p.display_name)],
        "Detener el material y no embarcarlo hasta que calidad lo libere.", link)
    return notify.queue(conn, p.organization_id, p.user_id, case["id"], "containment_started",
                        to + ([owner["email"]] if owner else []),
                        f"[8D PRO] Detener material — {case['folio']} · {case['part_number'] or case['title']}", text, body,
                        [{"document_id": str(d["document_id"]), "file_name": d["file_name"]} for d in docs])


@router.get("/cases/{case_id}/containment-record")
def get_record(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _record(conn, case_id)


@router.post("/cases/{case_id}/containment-record/start")
def start_containment(case_id: UUID, body: StartIn, background: BackgroundTasks, request: Request,
                      p: Principal = Depends(require("containment.edit")), conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D3", "La contención")
    if conn.execute("select 1 from case_containment where case_id = %s", (case_id,)).fetchone():
        raise ApiError(409, "already_started", "La contención ya se inició.")
    started = body.started_at or datetime.now(timezone.utc)
    if started > datetime.now(timezone.utc):
        raise invalid("El inicio de la contención no puede ser futuro.")
    record = conn.execute("""insert into case_containment (organization_id, case_id, started_at, started_by)
                             values (%s, %s, %s, %s) returning *""", (p.organization_id, case_id, started, p.user_id)).fetchone()
    email_id = queue_logistics_email(conn, p, case, record)
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = 'D3' and status = 'not_started'""", (case_id,))
    touch(conn, case_id)
    audit.record(conn, p, "containment.started", "case_containment", case_id, case_id,
                 new={"started_at": started, "email_id": str(email_id)})
    refresh_case_status(conn, case_id)
    background.add_task(notify.send_pending, request.app.state.db, [email_id])
    return _record(conn, case_id)


@router.post("/cases/{case_id}/containment-record/notify")
def resend_logistics(case_id: UUID, background: BackgroundTasks, request: Request,
                     p: Principal = Depends(require("containment.edit")), conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    record = conn.execute("select * from case_containment where case_id = %s", (case_id,)).fetchone()
    if not record:
        raise ApiError(409, "not_started", "Inicia la contención primero.")
    email_id = queue_logistics_email(conn, p, case, record)
    audit.record(conn, p, "containment.notified", "case_containment", case_id, case_id, new={"email_id": str(email_id)})
    background.add_task(notify.send_pending, request.app.state.db, [email_id])
    return _record(conn, case_id)


def _open_record(conn, p: Principal, case_id: UUID) -> tuple[dict, dict]:
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D3", "La contención")
    record = conn.execute("select * from case_containment where case_id = %s", (case_id,)).fetchone()
    if not record:
        raise ApiError(409, "not_started", "Inicia la contención primero (se avisa a logística).")
    if record["ended_at"]:
        raise ApiError(409, "already_ended", "La contención ya se finalizó.")
    return case, record


@router.post("/cases/{case_id}/containment-lots", status_code=201)
def add_lot(case_id: UUID, body: LotIn, p: Principal = Depends(require("containment.edit")),
            conn: psycopg.Connection = Depends(get_conn)):
    _open_record(conn, p, case_id)
    if body.quantity_rejected > body.quantity_inspected:
        raise invalid("Las piezas rechazadas no pueden superar las revisadas.")
    data = body.model_dump()
    row = conn.execute(
        f"""insert into containment_lots (organization_id, case_id, created_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))}) returning id""",
        [p.organization_id, case_id, p.user_id, *data.values()]).fetchone()
    touch(conn, case_id)
    audit.record(conn, p, "containment.lot_added", "containment_lot", row["id"], case_id, new=data)
    return _record(conn, case_id)


@router.delete("/containment-lots/{lot_id}")
def delete_lot(lot_id: UUID, p: Principal = Depends(require("containment.edit")), conn: psycopg.Connection = Depends(get_conn)):
    lot = conn.execute("select * from containment_lots where id = %s and organization_id = %s", (lot_id, p.organization_id)).fetchone()
    if not lot:
        raise not_found("Lote")
    _open_record(conn, p, lot["case_id"])
    conn.execute("delete from containment_lots where id = %s", (lot_id,))
    audit.record(conn, p, "containment.lot_deleted", "containment_lot", lot_id, lot["case_id"],
                 old={"lot_number": lot["lot_number"], "quantity_inspected": lot["quantity_inspected"]})
    return _record(conn, lot["case_id"])


@router.post("/cases/{case_id}/containment-record/end")
def end_containment(case_id: UUID, body: EndIn, p: Principal = Depends(require("containment.edit")),
                    conn: psycopg.Connection = Depends(get_conn)):
    _, record = _open_record(conn, p, case_id)
    if not conn.execute("select 1 from containment_lots where case_id = %s", (case_id,)).fetchone():
        raise ApiError(409, "lots_required", "Registra al menos un lote revisado antes de finalizar.")
    ended = body.ended_at or datetime.now(timezone.utc)
    if ended < record["started_at"] or ended > datetime.now(timezone.utc):
        raise invalid("El fin de la contención debe estar entre su inicio y ahora.")
    conn.execute("""update case_containment set ended_at = %s, ended_by = %s, result = %s, result_notes = %s, updated_at = now()
                    where case_id = %s""", (ended, p.user_id, body.result, body.result_notes.strip(), case_id))
    touch(conn, case_id)
    audit.record(conn, p, "containment.ended", "case_containment", case_id, case_id,
                 new={"ended_at": ended, "result": body.result, "result_notes": body.result_notes.strip()})
    refresh_case_status(conn, case_id)
    return _record(conn, case_id)


# ---- Archivos ---------------------------------------------------------------------------------

def _attachments(conn, case_id: UUID) -> list[dict]:
    return conn.execute(
        """select f.id, f.file_name, f.mime_type, f.file_size_bytes, f.sha256_hex, f.purpose, f.description,
                  f.containment_id, f.cause_id, f.action_id, f.effectiveness_check_id, f.system_update_id,
                  f.uploaded_at, u.display_name as uploaded_by_name
           from attachments f join users u on u.id = f.uploaded_by where f.case_id = %s order by f.uploaded_at desc""",
        (case_id,)).fetchall()


@router.get("/cases/{case_id}/attachments")
def list_attachments(case_id: UUID, p: Principal = Depends(require("case.read")),
                     conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _attachments(conn, case_id)


@router.post("/cases/{case_id}/attachments", status_code=201)
async def upload(case_id: UUID, file: UploadFile = File(...),
                 purpose: Literal["evidence", "photo", "general"] = Form("evidence"),
                 description: str | None = Form(None, max_length=500),
                 containment_id: UUID | None = Form(None), cause_id: UUID | None = Form(None),
                 action_id: UUID | None = Form(None), effectiveness_check_id: UUID | None = Form(None),
                 system_update_id: UUID | None = Form(None),
                 p: Principal = Depends(require("attachment.upload")), conn: psycopg.Connection = Depends(get_conn)):
    content = await file.read(storage.MAX_BYTES + 1)
    mime = storage.sniff(content)
    case = load_case(conn, p, case_id, for_update=True)
    rule(workflow.check_case_open, snapshot(conn, case))
    if sum(x is not None for x in (containment_id, cause_id, action_id, effectiveness_check_id, system_update_id)) > 1:
        raise invalid("Un archivo se vincula a un solo registro.")
    if action_id:
        action = conn.execute("select action_type from corrective_actions where id = %s and case_id = %s",
                              (action_id, case_id)).fetchone()
        if not action:
            raise invalid("La acción no pertenece al caso.")
        ensure_section_editable(conn, case, "D6" if action["action_type"] == "corrective" else "D7", "La acción")
    if effectiveness_check_id:
        if not conn.execute("select 1 from effectiveness_checks where id = %s and case_id = %s",
                            (effectiveness_check_id, case_id)).fetchone():
            raise invalid("La verificación no pertenece al caso.")
        ensure_section_editable(conn, case, "D6", "La verificación de eficacia")
    if system_update_id:
        if not conn.execute("select 1 from system_updates where id = %s and case_id = %s",
                            (system_update_id, case_id)).fetchone():
            raise invalid("La actualización no pertenece al caso.")
        ensure_section_editable(conn, case, "D7", "Las actualizaciones del sistema")
    if containment_id:
        if not conn.execute("select 1 from containment_actions where id = %s and case_id = %s",
                            (containment_id, case_id)).fetchone():
            raise invalid("La acción de contención no pertenece al caso.")
        ensure_section_editable(conn, case, "D3", "La contención")
    if cause_id:
        if not conn.execute("select 1 from ishikawa_causes where id = %s and case_id = %s", (cause_id, case_id)).fetchone():
            raise invalid("La causa no pertenece al caso.")
        ensure_section_editable(conn, case, "D4", "La investigación de causas")
    key, digest = storage.save(p.organization_id, content, mime)
    row = conn.execute(
        """insert into attachments (organization_id, case_id, containment_id, cause_id, action_id, effectiveness_check_id,
                                    system_update_id, purpose, storage_key, file_name, mime_type, file_size_bytes,
                                    sha256_hex, description, uploaded_by)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, case_id, containment_id, cause_id, action_id, effectiveness_check_id, system_update_id,
         purpose, key, storage.safe_name(file.filename, mime), mime, len(content), digest, description,
         p.user_id)).fetchone()
    audit.record(conn, p, "attachment.uploaded", "attachment", row["id"], case_id,
                 new={"file_name": file.filename, "sha256": digest, "size": len(content), "purpose": purpose})
    return next(a for a in _attachments(conn, case_id) if a["id"] == row["id"])


@router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: UUID, p: Principal = Depends(require("case.read")),
                       conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("select * from attachments where id = %s and organization_id = %s",
                       (attachment_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Archivo")
    load_case(conn, p, row["case_id"])  # verifica acceso a la planta
    return Response(storage.read(row["storage_key"]), media_type=row["mime_type"], headers={
        "Content-Disposition": f'inline; filename="{row["file_name"]}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
