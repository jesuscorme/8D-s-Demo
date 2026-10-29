"""Alertas de calidad (D3) con revisiones inmutables y documentos PDF emitidos."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import audit, notify, pdf_alert, storage, workflow
from app.auth import Principal, get_conn, require
from app.cases import load_case, rule, same_org_user, snapshot, touch
from app.db import setting
from app.errors import ApiError, invalid, not_found
from app.routers.cases_routes import _next_number

router = APIRouter(tags=["alerts"])

EDITABLE = ["failure_type", "title", "what_happened", "when_happened", "where_happened", "who_is_affected",
            "how_detected", "affected_areas", "affected_quantity", "containment_summary", "responsible_user_id"]
REQUIRED_TO_ISSUE = {
    "title": "Título", "what_happened": "¿Qué pasó?", "when_happened": "¿Cuándo?", "where_happened": "¿Dónde?",
    "who_is_affected": "¿Quién / a quién afecta?", "how_detected": "¿Cómo se detectó?",
    "affected_quantity": "Cantidad afectada", "containment_summary": "Contención", "responsible_user_id": "Responsable",
}


class AlertIn(BaseModel):
    # Sin indicar: la del caso (8D interno → falla interna; externo → falla externa).
    failure_type: Literal["internal", "external"] | None = None
    title: str | None = Field(None, max_length=200)


class AlertPatch(BaseModel):
    failure_type: Literal["internal", "external"] | None = None
    title: str | None = Field(None, min_length=1, max_length=200)
    what_happened: str | None = Field(None, max_length=1500)
    when_happened: str | None = Field(None, max_length=300)
    where_happened: str | None = Field(None, max_length=300)
    who_is_affected: str | None = Field(None, max_length=500)
    how_detected: str | None = Field(None, max_length=800)
    affected_areas: str | None = Field(None, max_length=500)
    affected_quantity: int | None = Field(None, ge=0)
    containment_summary: str | None = Field(None, max_length=1500)
    responsible_user_id: UUID | None = None


class Photo(BaseModel):
    attachment_id: UUID
    kind: Literal["nok", "ok"]


class PhotosIn(BaseModel):
    photos: list[Photo] = Field(max_length=4)


class ReviseIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _load(conn, p: Principal, alert_id: UUID, for_update=False) -> dict:
    row = conn.execute("select * from quality_alerts where id = %s and organization_id = %s"
                       + (" for update" if for_update else ""), (alert_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Alerta")
    load_case(conn, p, row["case_id"])
    return row


def _detail(conn, p: Principal, alert_id: UUID) -> dict:
    alert = _load(conn, p, alert_id)
    extra = conn.execute(
        """select c.folio as case_folio, c.title as case_title, r.display_name as responsible_name,
                  i.display_name as issued_by_name
           from quality_alerts a join cases_8d c on c.id = a.case_id left join users r on r.id = a.responsible_user_id
           left join users i on i.id = a.issued_by where a.id = %s""", (alert_id,)).fetchone()
    photos = conn.execute(
        """select ap.attachment_id, ap.kind, f.file_name from alert_photos ap join attachments f on f.id = ap.attachment_id
           where ap.alert_id = %s order by ap.kind, ap.sort_order""", (alert_id,)).fetchall()
    revisions = conn.execute(
        """select a.id, a.revision, a.status, a.issued_at, a.revision_reason, d.id as document_id, d.sha256_hex
           from quality_alerts a left join documents d on d.alert_id = a.id
           where a.organization_id = %s and a.alert_number = %s order by a.revision desc""",
        (p.organization_id, alert["alert_number"])).fetchall()
    missing = [label for key, label in REQUIRED_TO_ISSUE.items()
               if alert.get(key) is None or (isinstance(alert.get(key), str) and not alert[key].strip())]
    return {**alert, **extra, "folio": f"QA-{alert['alert_number']:04d}", "photos": photos, "revisions": revisions,
            "missing_to_issue": missing if alert["status"] == "draft" else []}


def _list_sql(where: str) -> str:
    return f"""select a.id, a.alert_number, a.revision, a.status, a.failure_type, a.title, a.issued_at, a.created_at,
                      c.id as case_id, c.folio as case_folio, d.id as document_id
               from quality_alerts a join cases_8d c on c.id = a.case_id
               left join documents d on d.alert_id = a.id
               where {where} order by a.alert_number desc, a.revision desc"""


@router.get("/alerts")
def list_alerts(p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    where = "a.organization_id = %(org)s" + ("" if p.plant_ids is None else " and c.plant_id = any(%(plants)s)")
    rows = conn.execute(_list_sql(where), {"org": p.organization_id, "plants": list(p.plant_ids or [])}).fetchall()
    return [{**r, "folio": f"QA-{r['alert_number']:04d}"} for r in rows]


@router.get("/cases/{case_id}/alerts")
def case_alerts(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    rows = conn.execute(_list_sql("a.organization_id = %(org)s and a.case_id = %(case)s"),
                        {"org": p.organization_id, "case": case_id}).fetchall()
    return [{**r, "folio": f"QA-{r['alert_number']:04d}"} for r in rows]


@router.post("/cases/{case_id}/alerts", status_code=201)
def create_alert(case_id: UUID, body: AlertIn, p: Principal = Depends(require("alert.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    rule(workflow.check_case_open, snapshot(conn, case))
    actions = conn.execute("""select description from containment_actions where case_id = %s and status <> 'cancelled'
                              order by created_at""", (case_id,)).fetchall()
    # Prellenado desde el expediente; el usuario lo revisa antes de emitir.
    prefill = {
        "title": body.title or case["title"],
        "what_happened": case["problem_description"] or None,
        "when_happened": case["defect_date"].isoformat() if case["defect_date"] else None,
        "affected_quantity": case["affected_quantity"],
        "containment_summary": "\n".join(f"• {a['description']}" for a in actions) or None,
        "responsible_user_id": case["owner_user_id"],
    }
    failure_type = body.failure_type or case["case_type"]
    number = _next_number(conn, p.organization_id, "alert")
    row = conn.execute(
        """insert into quality_alerts (organization_id, case_id, alert_number, failure_type, created_by, title,
                                       what_happened, when_happened, affected_quantity, containment_summary,
                                       responsible_user_id)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, case_id, number, failure_type, p.user_id, *prefill.values())).fetchone()
    touch(conn, case_id)
    audit.record(conn, p, "alert.created", "quality_alert", row["id"], case_id,
                 new={"alert_number": number, "revision": 1, "failure_type": failure_type})
    return _detail(conn, p, row["id"])


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    return _detail(conn, p, alert_id)


def _draft(conn, p, alert_id) -> dict:
    alert = _load(conn, p, alert_id, for_update=True)
    if alert["status"] != "draft":
        raise ApiError(409, "alert_issued", "Esta revisión ya fue emitida. Crea una nueva revisión para cambiarla.")
    case = load_case(conn, p, alert["case_id"])
    rule(workflow.check_case_open, snapshot(conn, case))
    return alert


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: UUID, body: AlertPatch, p: Principal = Depends(require("alert.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    alert = _draft(conn, p, alert_id)
    changes = body.model_dump(exclude_unset=True)
    if "title" in changes and not changes["title"]:
        raise invalid("El título es obligatorio.")
    if "responsible_user_id" in changes:
        same_org_user(conn, p, changes["responsible_user_id"])
    old, new = audit.diff(alert, changes)
    if new:
        conn.execute(f"update quality_alerts set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), alert_id])
        audit.record(conn, p, "alert.updated", "quality_alert", alert_id, alert["case_id"], old=old, new=new)
    return _detail(conn, p, alert_id)


@router.put("/alerts/{alert_id}/photos")
def set_photos(alert_id: UUID, body: PhotosIn, p: Principal = Depends(require("alert.edit")),
               conn: psycopg.Connection = Depends(get_conn)):
    alert = _draft(conn, p, alert_id)
    for photo in body.photos:
        ok = conn.execute("""select 1 from attachments where id = %s and case_id = %s
                             and mime_type in ('image/png', 'image/jpeg')""",
                          (photo.attachment_id, alert["case_id"])).fetchone()
        if not ok:
            raise invalid("Las fotos deben ser imágenes PNG/JPEG adjuntas al mismo caso.")
    conn.execute("delete from alert_photos where alert_id = %s", (alert_id,))
    for i, photo in enumerate(body.photos):
        conn.execute("""insert into alert_photos (organization_id, alert_id, attachment_id, kind, sort_order)
                        values (%s, %s, %s, %s, %s)""", (p.organization_id, alert_id, photo.attachment_id, photo.kind, i))
    audit.record(conn, p, "alert.photos_changed", "quality_alert", alert_id, alert["case_id"],
                 new={"photos": [ph.model_dump() for ph in body.photos]})
    return _detail(conn, p, alert_id)


def queue_alert_email(conn, p: Principal, alert: dict, case: dict, document_id: UUID, file_name: str,
                      responsible: str | None) -> UUID | None:
    """Alerta emitida → equipo del 8D y lista de distribución, con el PDF adjunto."""
    team = [r["email"] for r in conn.execute(
        "select u.email from case_team t join users u on u.id = t.user_id where t.case_id = %s and u.is_active", (case["id"],))]
    to = team + notify.recipients(conn, p.organization_id, case["plant_id"], "alert_issued")
    if not to:
        return None
    folio = f"QA-{alert['alert_number']:04d}"
    link = f"{setting('APP_BASE_URL', 'http://localhost:3010').rstrip('/')}/alertas/{alert['id']}"
    text, body = notify.render(
        f"Alerta de calidad {folio} rev. {alert['revision']} — {alert['title']}",
        f"Se emitió la alerta de calidad {folio} (falla {'externa' if alert['failure_type'] == 'external' else 'interna'}) "
        f"del 8D {case['folio']}. Difúndela con el personal involucrado; el PDF va adjunto.",
        [("Caso 8D", case["folio"]), ("Número de parte", case["part_number"] or "—"),
         ("¿Qué pasó?", alert["what_happened"] or "—"), ("¿Cuándo?", alert["when_happened"] or "—"),
         ("¿Dónde?", alert["where_happened"] or "—"), ("¿A quién afecta?", alert["who_is_affected"] or "—"),
         ("¿Cómo se detectó?", alert["how_detected"] or "—"),
         ("Cantidad afectada", f"{alert['affected_quantity']:,}" if alert["affected_quantity"] is not None else "—"),
         ("Contención", alert["containment_summary"] or "—"), ("Responsable", responsible or "—"), ("Emitió", p.display_name)],
        None, link)
    return notify.queue(conn, p.organization_id, p.user_id, case["id"], "alert_issued", to,
                        f"[8D PRO] Alerta de calidad {folio} rev. {alert['revision']} — {case['folio']}", text, body,
                        [{"document_id": str(document_id), "file_name": file_name}])


@router.post("/alerts/{alert_id}/issue")
def issue(alert_id: UUID, background: BackgroundTasks, request: Request, p: Principal = Depends(require("alert.issue")),
          conn: psycopg.Connection = Depends(get_conn)):
    alert = _draft(conn, p, alert_id)
    detail = _detail(conn, p, alert_id)
    if detail["missing_to_issue"]:
        raise ApiError(409, "requirements_pending", "Faltan datos para emitir la alerta.", detail["missing_to_issue"])
    case = load_case(conn, p, alert["case_id"])
    plant = conn.execute("select code, name, timezone from plants where id = %s", (case["plant_id"],)).fetchone()
    photos = [(ph["kind"], storage.read(ph["storage_key"])) for ph in conn.execute(
        """select ap.kind, f.storage_key from alert_photos ap join attachments f on f.id = ap.attachment_id
           where ap.alert_id = %s order by ap.sort_order""", (alert_id,)).fetchall()]
    issued_at = datetime.now(timezone.utc).astimezone(ZoneInfo(plant["timezone"]))
    url = f"{setting('APP_BASE_URL', 'http://localhost:3000').rstrip('/')}/alertas/{alert_id}"
    from app.routers.reports import org_logo  # import diferido (reports importa routers de casos)
    pdf = pdf_alert.render(alert, case, p.organization_name, f"{plant['code']} — {plant['name']}", photos,
                           p.display_name, detail["responsible_name"], issued_at, url, org_logo(conn, p.organization_id))
    key, digest = storage.save(p.organization_id, pdf, "application/pdf")
    previous = conn.execute("""select a.id, d.id as document_id from quality_alerts a
                               left join documents d on d.alert_id = a.id
                               where a.organization_id = %s and a.alert_number = %s and a.status = 'issued' for update of a""",
                            (p.organization_id, alert["alert_number"])).fetchone()
    if previous:
        conn.execute("update quality_alerts set status = 'superseded', updated_at = now() where id = %s", (previous["id"],))
    conn.execute("update quality_alerts set status = 'issued', issued_by = %s, issued_at = %s, updated_at = now() where id = %s",
                 (p.user_id, issued_at, alert_id))
    folio = f"QA-{alert['alert_number']:04d}"
    doc = conn.execute(
        """insert into documents (organization_id, case_id, alert_id, document_type, revision, storage_key, file_name,
                                  mime_type, file_size_bytes, sha256_hex, template_version, generated_by, metadata)
           values (%s, %s, %s, 'quality_alert', %s, %s, %s, 'application/pdf', %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, alert["case_id"], alert_id, alert["revision"], key, f"{folio}_rev{alert['revision']}.pdf",
         len(pdf), digest, pdf_alert.TEMPLATE_VERSION, p.user_id,
         Jsonb({"folio": folio, "case_folio": case["folio"], "qr_url": url}))).fetchone()
    if previous and previous["document_id"]:
        conn.execute("update documents set status = 'superseded', superseded_by = %s where id = %s",
                     (doc["id"], previous["document_id"]))
    touch(conn, alert["case_id"])
    email_id = queue_alert_email(conn, p, alert, case, doc["id"], f"{folio}_rev{alert['revision']}.pdf", detail["responsible_name"])
    audit.record(conn, p, "alert.issued", "quality_alert", alert_id, alert["case_id"],
                 new={"folio": folio, "revision": alert["revision"], "document_id": doc["id"], "sha256": digest,
                      "email_id": str(email_id) if email_id else None},
                 metadata={"superseded_alert_id": previous["id"] if previous else None})
    if email_id:
        background.add_task(notify.send_pending, request.app.state.db, [email_id])
    return _detail(conn, p, alert_id)


@router.post("/alerts/{alert_id}/revise", status_code=201)
def revise(alert_id: UUID, body: ReviseIn, p: Principal = Depends(require("alert.edit")),
           conn: psycopg.Connection = Depends(get_conn)):
    alert = _load(conn, p, alert_id, for_update=True)
    if alert["status"] != "issued":
        raise ApiError(409, "invalid_transition", "Solo se revisa la revisión vigente (emitida).")
    case = load_case(conn, p, alert["case_id"])
    rule(workflow.check_case_open, snapshot(conn, case))
    if conn.execute("select 1 from quality_alerts where organization_id = %s and alert_number = %s and status = 'draft'",
                    (p.organization_id, alert["alert_number"])).fetchone():
        raise ApiError(409, "draft_exists", "Ya existe un borrador de nueva revisión para esta alerta.")
    cols = ", ".join(EDITABLE)
    row = conn.execute(
        f"""insert into quality_alerts (organization_id, case_id, alert_number, revision, revision_reason, created_by, {cols})
            select organization_id, case_id, alert_number, revision + 1, %s, %s, {cols} from quality_alerts where id = %s
            returning id""", (body.reason.strip(), p.user_id, alert_id)).fetchone()
    conn.execute("""insert into alert_photos (organization_id, alert_id, attachment_id, kind, sort_order)
                    select organization_id, %s, attachment_id, kind, sort_order from alert_photos where alert_id = %s""",
                 (row["id"], alert_id))
    audit.record(conn, p, "alert.revision_started", "quality_alert", row["id"], alert["case_id"],
                 new={"revision": alert["revision"] + 1, "reason": body.reason.strip()},
                 metadata={"from_alert_id": alert_id})
    return _detail(conn, p, row["id"])


@router.get("/cases/{case_id}/documents")
def case_documents(case_id: UUID, p: Principal = Depends(require("case.read")),
                   conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return conn.execute(
        """select d.id, d.document_type, d.revision, d.file_name, d.file_size_bytes, d.sha256_hex, d.status,
                  d.template_version, d.generated_at, d.alert_id, u.display_name as generated_by_name
           from documents d join users u on u.id = d.generated_by where d.case_id = %s order by d.generated_at desc""",
        (case_id,)).fetchall()


@router.get("/documents/{document_id}/content")
def document_content(document_id: UUID, p: Principal = Depends(require("case.read")),
                     conn: psycopg.Connection = Depends(get_conn)):
    from app.routers.reports import can_download  # import diferido (reports importa routers de casos)
    doc = conn.execute("""select d.*, c.plant_id from documents d left join cases_8d c on c.id = d.case_id
                          where d.id = %s and d.organization_id = %s""", (document_id, p.organization_id)).fetchone()
    if not doc or not can_download(p, doc):
        raise not_found("Documento")
    if doc["lesson_id"] and not p.can("lesson.edit") and not conn.execute(
            "select 1 from lessons_learned where id = %s and status = 'published'", (doc["lesson_id"],)).fetchone():
        raise not_found("Documento")
    audit.record(conn, p, "document.downloaded", "document", document_id, doc["case_id"],
                 metadata={"file_name": doc["file_name"], "revision": doc["revision"]})
    return Response(storage.read(doc["storage_key"]), media_type=doc["mime_type"], headers={
        "Content-Disposition": f'inline; filename="{doc["file_name"]}"', "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store", "X-Content-SHA256": doc["sha256_hex"]})
