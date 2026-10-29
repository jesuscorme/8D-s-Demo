"""Destinatarios de notificaciones, correo de prueba y bandeja de salida."""
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field

from app import audit, notify
from app.auth import Principal, get_conn, require
from app.cases import load_case
from app.errors import ApiError, invalid, not_found

router = APIRouter(tags=["notifications"])
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"


class RecipientIn(BaseModel):
    event: Literal["containment_started", "alert_issued"]
    email: str = Field(min_length=5, max_length=254, pattern=EMAIL)
    name: str | None = Field(None, max_length=120)
    plant_id: UUID | None = None


class TestIn(BaseModel):
    to: str = Field(min_length=5, max_length=254, pattern=EMAIL)


@router.get("/admin/notifications")
def list_recipients(p: Principal = Depends(require("admin.users")), conn: psycopg.Connection = Depends(get_conn)):
    rows = conn.execute(
        """select n.id, n.event, n.email, n.name, n.plant_id, pl.code as plant_code from notification_recipients n
           left join plants pl on pl.id = n.plant_id where n.organization_id = %s order by n.event, n.email""",
        (p.organization_id,)).fetchall()
    return {"recipients": rows, "events": notify.EVENTS, "settings": notify.settings_summary()}


@router.post("/admin/notifications", status_code=201)
def add_recipient(body: RecipientIn, p: Principal = Depends(require("admin.users")), conn: psycopg.Connection = Depends(get_conn)):
    if body.plant_id and not conn.execute("select 1 from plants where id = %s and organization_id = %s",
                                          (body.plant_id, p.organization_id)).fetchone():
        raise invalid("La planta no existe en tu organización.")
    row = conn.execute(
        """insert into notification_recipients (organization_id, plant_id, event, email, name) values (%s, %s, %s, %s, %s)
           returning id""", (p.organization_id, body.plant_id, body.event, body.email.strip().lower(), body.name)).fetchone()
    audit.record(conn, p, "notification.recipient_added", "notification_recipient", row["id"],
                 new={"event": body.event, "email": body.email.strip().lower()})
    return list_recipients(p, conn)


@router.delete("/admin/notifications/{recipient_id}")
def delete_recipient(recipient_id: UUID, p: Principal = Depends(require("admin.users")), conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("delete from notification_recipients where id = %s and organization_id = %s returning event, email",
                       (recipient_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Destinatario")
    audit.record(conn, p, "notification.recipient_removed", "notification_recipient", recipient_id, old=dict(row))
    return list_recipients(p, conn)


@router.post("/admin/email/test", status_code=201)
def send_test(body: TestIn, background: BackgroundTasks, request: Request, p: Principal = Depends(require("admin.users")),
              conn: psycopg.Connection = Depends(get_conn)):
    settings = notify.settings_summary()
    text, html = notify.render("Correo de prueba de 8D PRO",
                               f"Si recibes este mensaje, la configuración de correo funciona (transporte: {settings['transport']}).",
                               [("Enviado por", p.display_name), ("Organización", p.organization_name)], None, None)
    email_id = notify.queue(conn, p.organization_id, p.user_id, None, "test", [body.to], "[8D PRO] Correo de prueba", text, html)
    audit.record(conn, p, "notification.test", "email", email_id, new={"to": body.to})
    background.add_task(notify.send_pending, request.app.state.db, [email_id])
    return {"id": email_id, "settings": settings}


@router.get("/admin/email/outbox")
def outbox(status: Literal["queued", "sent", "failed"] | None = None, p: Principal = Depends(require("admin.users")),
           conn: psycopg.Connection = Depends(get_conn)):
    return conn.execute(
        """select e.id, e.event, e.to_addresses, e.subject, e.status, e.attempts, e.last_error, e.transport, e.created_at,
                  e.sent_at, e.attachments, c.folio as case_folio, e.case_id
           from email_outbox e left join cases_8d c on c.id = e.case_id
           where e.organization_id = %s and (%s::text is null or e.status = %s) order by e.created_at desc limit 200""",
        (p.organization_id, status, status)).fetchall()


@router.post("/admin/email/outbox/{email_id}/retry")
def retry(email_id: UUID, background: BackgroundTasks, request: Request, p: Principal = Depends(require("admin.users")),
          conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("""update email_outbox set status = 'queued' where id = %s and organization_id = %s and status = 'failed'
                          returning id""", (email_id, p.organization_id)).fetchone()
    if not row:
        raise ApiError(409, "not_failed", "Solo se reintenta un correo fallido.")
    audit.record(conn, p, "notification.retry", "email", email_id)
    background.add_task(notify.send_pending, request.app.state.db, [email_id])
    return {"ok": True}


@router.get("/cases/{case_id}/emails")
def case_emails(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return conn.execute(
        """select id, event, to_addresses, subject, status, last_error, transport, created_at, sent_at, attachments
           from email_outbox where case_id = %s order by created_at desc""", (case_id,)).fetchall()
