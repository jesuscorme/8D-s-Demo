"""D3: acciones de contención y archivos adjuntos (evidencias y fotos)."""
from datetime import date
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import audit, storage, workflow
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
