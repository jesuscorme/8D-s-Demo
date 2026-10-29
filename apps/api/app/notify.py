"""Notificaciones por correo con bandeja de salida (email_outbox).

Los correos se registran dentro de la transacción del cambio que los origina y se envían DESPUÉS del
commit (BackgroundTasks): un fallo de correo nunca revierte la contención ni la alerta, y queda
registrado con su error para reintentarlo.

Transporte (variable EMAIL_TRANSPORT): «smtp» (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
SMTP_STARTTLS, EMAIL_FROM) o «file» (archivos .eml en storage/outbox, para pruebas y demostraciones).
Por defecto: smtp si hay SMTP_HOST, si no file.
"""
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app import storage
from app.db import setting

log = logging.getLogger("d8.notify")
EVENTS = {"containment_started": "Inicio de contención (logística)", "alert_issued": "Alerta de calidad emitida"}


def transport() -> str:
    mode = (setting("EMAIL_TRANSPORT") or "").lower()
    if mode in ("smtp", "file"):
        return mode
    return "smtp" if setting("SMTP_HOST") else "file"


def settings_summary() -> dict:
    mode = transport()
    return {"transport": mode, "from": setting("EMAIL_FROM", "8D PRO <no-reply@8dpro.local>"),
            "smtp_host": setting("SMTP_HOST") if mode == "smtp" else None,
            "smtp_port": int(setting("SMTP_PORT", "587")) if mode == "smtp" else None,
            "smtp_user": setting("SMTP_USER") if mode == "smtp" else None,
            "file_dir": str(storage.root() / "outbox") if mode == "file" else None}


def recipients(conn: psycopg.Connection, organization_id: UUID, plant_id: UUID | None, event: str) -> list[str]:
    rows = conn.execute(
        """select email from notification_recipients where organization_id = %s and event = %s
             and (plant_id is null or plant_id = %s) order by email""", (organization_id, event, plant_id)).fetchall()
    return [r["email"] for r in rows]


def queue(conn: psycopg.Connection, organization_id: UUID, actor_id: UUID | None, case_id: UUID | None, event: str,
          to: list[str], subject: str, text: str, html_body: str | None = None,
          attachments: list[dict] | None = None) -> UUID:
    to = sorted({t.strip().lower() for t in to if t and "@" in t})
    if not to:
        raise ValueError("Sin destinatarios")
    row = conn.execute(
        """insert into email_outbox (organization_id, case_id, event, to_addresses, subject, body_text, body_html,
                                     attachments, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (organization_id, case_id, event, to, subject, text, html_body, Jsonb(attachments or []), actor_id)).fetchone()
    return row["id"]


def render(title: str, intro: str, rows: list[tuple[str, str]], action: str | None, link: str | None) -> tuple[str, str]:
    """Cuerpo en texto plano y HTML con el estilo de 8D PRO."""
    text = "\n".join([title, "", intro, "", *[f"{k}: {v}" for k, v in rows], *([f"", f"ACCIÓN REQUERIDA: {action}"] if action else []),
                      *([f"", f"Expediente: {link}"] if link else []), "", "— 8D PRO (mensaje automático)"])
    cells = "".join(f'<tr><td style="padding:6px 12px;color:#5d6a7c;font-weight:600;white-space:nowrap">{html.escape(k)}</td>'
                    f'<td style="padding:6px 12px">{html.escape(str(v))}</td></tr>' for k, v in rows)
    action_html = (f'<p style="background:#fdecec;border:1px solid #f3c6c6;color:#8e1c1c;padding:12px 14px;border-radius:8px;'
                   f'font-weight:600">ACCIÓN REQUERIDA: {html.escape(action)}</p>') if action else ""
    link_html = (f'<p><a href="{html.escape(link)}" style="background:#1d6fe0;color:#fff;padding:10px 16px;border-radius:8px;'
                 f'text-decoration:none;font-weight:600">Abrir el expediente</a></p>') if link else ""
    body = (f'<div style="font-family:Segoe UI,Arial,sans-serif;color:#15202e;max-width:640px">'
            f'<div style="background:#0b1f3a;color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;font-weight:700">8D PRO</div>'
            f'<div style="border:1px solid #e1e6ee;border-top:none;padding:18px;border-radius:0 0 10px 10px">'
            f'<h2 style="margin:0 0 8px;font-size:18px">{html.escape(title)}</h2><p>{html.escape(intro)}</p>'
            f'<table style="border-collapse:collapse;font-size:14px;margin:8px 0">{cells}</table>{action_html}{link_html}'
            f'<p style="color:#5d6a7c;font-size:12px;margin-top:18px">Mensaje automático de 8D PRO. La alerta de calidad '
            f'vigente va adjunta en PDF.</p></div></div>')
    return text, body


def _message(row: dict, conn: psycopg.Connection) -> EmailMessage:
    msg = EmailMessage()
    sender = setting("EMAIL_FROM", "8D PRO <no-reply@8dpro.local>")
    msg["From"] = sender if "<" in sender else formataddr(("8D PRO", sender))
    msg["To"] = ", ".join(row["to_addresses"])
    msg["Subject"] = row["subject"]
    msg["Message-ID"] = make_msgid(domain="8dpro.local")
    msg.set_content(row["body_text"])
    if row["body_html"]:
        msg.add_alternative(row["body_html"], subtype="html")
    for att in row["attachments"]:
        doc = conn.execute("select storage_key, file_name, mime_type from documents where id = %s and organization_id = %s",
                           (att["document_id"], row["organization_id"])).fetchone()
        if not doc:
            raise RuntimeError(f"Documento adjunto no encontrado: {att.get('file_name')}")
        maintype, subtype = doc["mime_type"].split("/", 1)
        msg.add_attachment(storage.read(doc["storage_key"]), maintype=maintype, subtype=subtype, filename=doc["file_name"])
    return msg


def _deliver(msg: EmailMessage, row: dict, mode: str) -> None:
    if mode == "file":
        folder = storage.root() / "outbox"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{row['id']}.eml").write_bytes(bytes(msg))
        return
    host, port = setting("SMTP_HOST"), int(setting("SMTP_PORT", "587"))
    user, password = setting("SMTP_USER"), setting("SMTP_PASSWORD")
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(host, port, timeout=30)
    with server:
        if port != 465 and setting("SMTP_STARTTLS", "true") != "false":
            server.starttls(context=ssl.create_default_context())
        if user:
            server.login(user, password or "")
        server.send_message(msg)


def send_pending(db, ids: list[UUID] | None = None) -> None:
    """Envía los correos en cola (o los indicados). Se ejecuta después del commit."""
    mode = transport()
    with db.pool.connection() as conn:
        rows = conn.execute(
            "select * from email_outbox where status = 'queued' and (%s::uuid[] is null or id = any(%s::uuid[])) order by created_at limit 50",
            (ids, ids)).fetchall()
    for row in rows:
        error = None
        try:
            with db.pool.connection() as conn:
                msg = _message(row, conn)
            _deliver(msg, row, mode)
        except Exception as exc:  # el error queda en la bandeja; la operación de negocio ya está guardada
            error = f"{exc.__class__.__name__}: {exc}"[:500]
            log.warning("Fallo al enviar correo %s: %s", row["id"], error)
        with db.pool.connection() as conn:
            conn.execute("""update email_outbox set status = %s, attempts = attempts + 1, last_error = %s, transport = %s,
                            sent_at = case when %s then now() else sent_at end where id = %s""",
                         ("failed" if error else "sent", error, mode, error is None, row["id"]))
