"""Fase 10: documentos (8D completo, avance, auditoría, lección), Excel, integridad e indicadores."""
import logging
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app import audit, excel, pdf_reports, storage, workflow
from app.auth import Principal, get_conn, require
from app.cases import load_case, snapshot
from app.errors import ApiError, forbidden, invalid, not_found
from app.routers.cases_routes import _next_number
from app.routers.lessons import _detail as lesson_detail

router = APIRouter(tags=["reports"])
log = logging.getLogger("d8.reports")

CaseDoc = Literal["8d_full", "8d_progress", "audit_report"]
DOC_TITLES = {"8d_full": "Expediente 8D completo", "8d_progress": "Reporte de avance 8D",
              "audit_report": "Reporte de auditoría", "lesson_learned": "Lección aprendida", "excel_export": "Exportación Excel"}
SEVERITY = {"low": "Baja", "medium": "Media", "high": "Alta", "critical": "Crítica"}
TEAM_ROLE = {"leader": "Líder", "champion": "Patrocinador", "member": "Integrante"}
ACTION_TYPE = {"corrective": "Correctiva", "preventive": "Preventiva", "systemic": "Sistémica"}
UPDATE_TYPE = {"pfmea": "AMEF de proceso", "dfmea": "AMEF de diseño", "control_plan": "Plan de control",
               "work_instruction": "Instrucción de trabajo", "visual_aid": "Ayuda visual", "training": "Capacitación",
               "other": "Otro"}
ANSWER = {"yes": "Sí", "no": "No", "unknown": "Sin dato", "not_applicable": "N/A", None: "—"}
OUTCOME = {"applied": "Aplicada", "partially_applied": "Aplicada parcialmente", "not_applicable": "No aplica"}
CONTENT_LABELS = {
    "emergency_response": "Respuesta de emergencia", "justification": "Justificación del 8D", "notes": "Notas",
    "what": "¿Qué?", "where": "¿Dónde?", "when": "¿Cuándo?", "who": "¿Quién?", "how_detected": "¿Cómo se detectó?",
    "is_not": "Es / No es", "effectiveness_notes": "Eficacia de la contención", "occurrence_cause": "Causa de ocurrencia",
    "escape_point": "Punto de escape", "five_whys": "5 porqués", "verification_plan": "Plan de verificación",
    "validation_summary": "Resumen de la validación", "horizontal_deployment": "Despliegue horizontal",
    "no_update_justification": "Justificación sin actualización documental",
    "no_preventive_justification": "Justificación sin acción preventiva", "closure_summary": "Resumen de cierre",
    "team_recognition": "Reconocimiento al equipo",
}


def event_label(event: str) -> str:
    return event.replace(".", " · ").replace("_", " ")


def _now_local(conn, plant_id: UUID | None) -> datetime:
    tz = "America/Mexico_City"
    if plant_id:
        tz = conn.execute("select timezone from plants where id = %s", (plant_id,)).fetchone()["timezone"]
    return datetime.now(timezone.utc).astimezone(ZoneInfo(tz))


def _threshold(k: dict) -> str:
    v = float(k["threshold_value"])
    return {"max_defects": f"máx. {v:g} defectos", "max_rate_ppm": f"máx. {v:g} ppm",
            "max_rate_percent": f"máx. {v:g} %"}[k["threshold_type"]]


def case_bundle(conn, p: Principal, case_id: UUID, with_photos: bool = True) -> dict:
    case = load_case(conn, p, case_id)
    snap = snapshot(conn, case)
    meta = conn.execute("""select pl.code || ' — ' || pl.name as plant, o.display_name as owner_name, b.display_name as opened_by_name
                           from cases_8d c join plants pl on pl.id = c.plant_id left join users o on o.id = c.owner_user_id
                           join users b on b.id = c.opened_by where c.id = %s""", (case_id,)).fetchone()
    disciplines = {d["discipline_code"]: d for d in conn.execute(
        """select d.discipline_code, d.content, d.approved_at, a.display_name as approved_by_name
           from case_disciplines d left join users a on a.id = d.approved_by where d.case_id = %s""", (case_id,))}
    flow = [{**w, **{k: v for k, v in disciplines.get(w["code"], {}).items() if k != "discipline_code"},
             "labels": CONTENT_LABELS} for w in workflow.evaluate(snap)]
    team = conn.execute("""select u.display_name, u.email, t.team_role from case_team t join users u on u.id = t.user_id
                           where t.case_id = %s order by (t.team_role = 'leader') desc, u.display_name""", (case_id,)).fetchall()
    containment = conn.execute("""select a.*, u.display_name as responsible_name,
                                         (a.due_date < current_date and a.status not in ('verified','cancelled')) as overdue
                                  from containment_actions a left join users u on u.id = a.responsible_user_id
                                  where a.case_id = %s order by a.created_at""", (case_id,)).fetchall()
    alerts = conn.execute("""select a.id, 'QA-' || lpad(a.alert_number::text, 4, '0') as folio, a.revision, a.status, a.title,
                                    a.issued_at, d.sha256_hex from quality_alerts a left join documents d on d.alert_id = a.id
                             where a.case_id = %s order by a.alert_number, a.revision""", (case_id,)).fetchall()
    photos = []
    if with_photos:
        current = next((a for a in reversed(alerts) if a["status"] == "issued"), None)
        if current:
            for ph in conn.execute("""select ap.kind, f.storage_key from alert_photos ap join attachments f on f.id = ap.attachment_id
                                      where ap.alert_id = %s order by ap.kind, ap.sort_order""", (current["id"],)):
                try:
                    photos.append((ph["kind"], storage.read(ph["storage_key"])))
                except ApiError:
                    log.warning("Foto de alerta no encontrada en storage: %s", ph["storage_key"])
    causes = conn.execute(
        """select c.*, k.name_es as category_name, lv.documented_answer, lv.followed_process_answer,
                  lv.verification_method, lv.evidence_summary, lv.rationale
           from ishikawa_causes c join ishikawa_categories k on k.id = c.category_id
           left join lateral (select * from cause_validations v where v.cause_id = c.id order by v.validated_at desc limit 1) lv on true
           where c.case_id = %s order by k.display_order, c.created_at""", (case_id,)).fetchall()
    for x in causes:
        x["documented"], x["followed"] = ANSWER[x["documented_answer"]], ANSWER[x["followed_process_answer"]]
    actions = conn.execute(
        """select a.*, c.potential_cause as cause_text, u.display_name as responsible_name,
                  (a.due_date < current_date and a.status in ('open','in_progress')) as overdue
           from corrective_actions a left join ishikawa_causes c on c.id = a.cause_id
           left join users u on u.id = a.responsible_user_id where a.case_id = %s order by a.action_type, a.created_at""",
        (case_id,)).fetchall()
    for a in actions:
        a["type_label"] = ACTION_TYPE[a["action_type"]]
    criteria = conn.execute("select * from effectiveness_criteria where case_id = %s order by created_at", (case_id,)).fetchall()
    for k in criteria:
        k["threshold_label"] = _threshold(k)
        k["denominator"] = k["denominator_label"] or {
            "units_produced": "unidades producidas", "units_inspected": "unidades inspeccionadas",
            "lots_received": "lotes recibidos", "shipments": "embarques"}.get(k["denominator_type"], k["denominator_type"])
    checks = conn.execute("""select e.*, a.description as action_description from effectiveness_checks e
                             join corrective_actions a on a.id = e.action_id where e.case_id = %s order by e.created_at""",
                          (case_id,)).fetchall()
    updates = conn.execute("select * from system_updates where case_id = %s order by created_at", (case_id,)).fetchall()
    for u in updates:
        u["type_label"] = UPDATE_TYPE[u["update_type"]]
    lessons = conn.execute("""select 'LA-' || lpad(lesson_number::text, 4, '0') as folio, revision, title, status
                              from lessons_learned where source_case_id = %s order by lesson_number, revision""",
                           (case_id,)).fetchall()
    documents = conn.execute("""select file_name, revision, status, generated_at, sha256_hex, document_type
                                from documents where case_id = %s order by generated_at""", (case_id,)).fetchall()
    events = conn.execute(
        """select e.event_type, e.occurred_at, e.old_values, e.new_values, e.request_id, u.display_name as actor_name
           from audit_events e left join users u on u.id = e.actor_user_id
           where e.organization_id = %s and e.case_id = %s order by e.occurred_at desc, e.id desc""",
        (p.organization_id, case_id)).fetchall()
    audit_rows = [{**e, "label": event_label(e["event_type"]), "old": e["old_values"] or {}, "new": e["new_values"] or {},
                   "keys": list(dict.fromkeys([*(e["old_values"] or {}), *(e["new_values"] or {})]))} for e in events]
    open_items = ([{"kind": "Contención", "description": a["description"], "responsible_name": a["responsible_name"],
                    "due_date": a["due_date"], "status": a["status"], "overdue": a["overdue"]}
                   for a in containment if a["status"] not in ("verified", "cancelled")]
                  + [{"kind": a["type_label"], "description": a["description"], "responsible_name": a["responsible_name"],
                      "due_date": a["due_date"], "status": a["status"], "overdue": a["overdue"]}
                     for a in actions if a["status"] not in ("verified", "cancelled", "approved")])
    return {"case": {**case, **meta, "severity_label": SEVERITY[case["severity"]]}, "workflow": flow,
            "team": [{**t, "role_label": TEAM_ROLE[t["team_role"]]} for t in team], "containment": containment,
            "alerts": alerts, "photos": photos, "causes": causes, "actions": actions, "criteria": criteria,
            "checks": checks, "system_updates": updates, "lessons": lessons, "documents": documents, "audit": audit_rows,
            "open_items": open_items}


def org_logo(conn, organization_id: UUID) -> bytes | None:
    row = conn.execute("select logo_storage_key from organizations where id = %s", (organization_id,)).fetchone()
    if not row or not row["logo_storage_key"]:
        return None
    try:
        return storage.read(row["logo_storage_key"])
    except ApiError:
        log.warning("Logo de la organización no encontrado en storage")
        return None


def _meta(conn, p: Principal, kind: str, folio: str, revision: int, status_label: str, plant_id, watermark=None) -> dict:
    template = excel.TEMPLATE_VERSION if kind == "excel_export" else pdf_reports.TEMPLATES[kind]
    return {"title": DOC_TITLES[kind], "folio": folio, "revision": revision, "organization": p.organization_name,
            "issued_by": p.display_name, "issued_at": _now_local(conn, plant_id).strftime("%Y-%m-%d %H:%M %Z"),
            "status_label": status_label, "template_version": template, "watermark": watermark,
            "logo": None if kind == "excel_export" else org_logo(conn, p.organization_id)}


def _render(fn, *args) -> bytes:
    try:
        return fn(*args)
    except ApiError:
        raise
    except Exception as exc:  # el error se informa con claridad y no se registra ninguna emisión
        log.exception("Fallo al generar documento")
        raise ApiError(500, "document_failed", f"No se pudo generar el documento ({exc.__class__.__name__}). "
                       "No se registró ninguna emisión; inténtalo de nuevo o avisa al administrador.") from None


def issue_document(conn, p: Principal, kind: str, content: bytes, mime: str, file_name: str, scope: str,
                   case_id: UUID | None = None, lesson_id: UUID | None = None, metadata: dict | None = None,
                   revision: int | None = None) -> dict:
    """Registra una emisión: archivo nuevo + fila nueva; la emisión vigente anterior del mismo alcance queda sustituida."""
    revision = revision or _next_number(conn, p.organization_id, scope)
    key, digest = storage.save(p.organization_id, content, mime)
    template = excel.TEMPLATE_VERSION if kind == "excel_export" else pdf_reports.TEMPLATES[kind]
    doc = conn.execute(
        """insert into documents (organization_id, case_id, lesson_id, document_type, revision, storage_key, file_name,
                                  mime_type, file_size_bytes, sha256_hex, template_version, generated_by, metadata)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id, revision, sha256_hex""",
        (p.organization_id, case_id, lesson_id, kind, revision, key, file_name, mime, len(content), digest, template,
         p.user_id, Jsonb({**(metadata or {}), "scope": scope}))).fetchone()
    previous = conn.execute(
        """select id from documents where organization_id = %s and metadata->>'scope' = %s and status = 'issued'
             and id <> %s""", (p.organization_id, scope, doc["id"])).fetchall()
    for prev in previous:
        conn.execute("update documents set status = 'superseded', superseded_by = %s where id = %s", (doc["id"], prev["id"]))
    audit.record(conn, p, "document.issued", "document", doc["id"], case_id,
                 new={"type": kind, "revision": revision, "sha256": digest, "file_name": file_name},
                 metadata={"superseded": [str(x["id"]) for x in previous], "lesson_id": str(lesson_id) if lesson_id else None})
    return {"id": doc["id"], "revision": revision, "sha256_hex": digest, "file_name": file_name, "document_type": kind,
            "status": "issued"}


def _case_pdf(conn, p: Principal, case_id: UUID, kind: str, preview: bool) -> tuple[bytes, dict, int]:
    if kind == "audit_report":
        p.check("audit.read")
    b = case_bundle(conn, p, case_id, with_photos=kind == "8d_full")
    c = b["case"]
    scope = f"doc:{kind}:{case_id}"
    if preview:
        revision = (conn.execute("select last_value from counters where organization_id = %s and scope = %s",
                                 (p.organization_id, scope)).fetchone() or {"last_value": 0})["last_value"] + 1
    else:
        revision = _next_number(conn, p.organization_id, scope)
    meta = _meta(conn, p, kind, c["folio"], revision, f"Caso: {pdf_reports.st(c['status'])}", c["plant_id"],
                 "VISTA PREVIA — NO CONTROLADO" if preview else None)
    fn = pdf_reports.audit_report if kind == "audit_report" else pdf_reports.case_report
    args = (b, meta) if kind == "audit_report" else (b, meta, kind == "8d_full")
    return _render(fn, *args), c, revision


@router.get("/cases/{case_id}/documents/{kind}/preview")
def preview_case_document(case_id: UUID, kind: CaseDoc, p: Principal = Depends(require("document.generate")),
                          conn: psycopg.Connection = Depends(get_conn)):
    pdf, _, _ = _case_pdf(conn, p, case_id, kind, preview=True)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=vista_previa.pdf",
                                                                "Cache-Control": "private, no-store"})


@router.post("/cases/{case_id}/documents/{kind}", status_code=201)
def issue_case_document(case_id: UUID, kind: CaseDoc, p: Principal = Depends(require("document.generate")),
                        conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id, for_update=True)  # serializa emisiones del mismo caso
    pdf, c, revision = _case_pdf(conn, p, case_id, kind, preview=False)
    name = {"8d_full": "8D", "8d_progress": "Avance", "audit_report": "Auditoria"}[kind]
    return issue_document(conn, p, kind, pdf, "application/pdf", f"{c['folio']}_{name}_rev{revision}.pdf",
                          f"doc:{kind}:{case_id}", case_id=case_id, revision=revision,
                          metadata={"case_folio": c["folio"], "case_status": c["status"]})


def _lesson_pdf(conn, p: Principal, lesson_id: UUID, preview: bool) -> tuple[bytes, dict]:
    lesson = lesson_detail(conn, p, lesson_id)
    for a in lesson["applications"]:
        a["outcome_label"] = OUTCOME[a["outcome"]]
    lesson["photo_images"] = []
    for ph in conn.execute("""select lp.kind, lp.caption, f.storage_key from lesson_photos lp join attachments f on f.id = lp.attachment_id
                              where lp.lesson_id = %s order by lp.sort_order""", (lesson_id,)).fetchall():
        try:
            lesson["photo_images"].append((ph["kind"], ph["caption"], storage.read(ph["storage_key"])))
        except ApiError:
            log.warning("Foto de lección no encontrada en storage: %s", ph["storage_key"])
    source = conn.execute("select plant_id from cases_8d where id = %s", (lesson["source_case_id"],)).fetchone()
    meta = _meta(conn, p, "lesson_learned", lesson["folio"], lesson["revision"], f"Lección: {pdf_reports.st(lesson['status'])}",
                 source["plant_id"], "VISTA PREVIA — NO CONTROLADO" if preview or lesson["status"] == "draft" else None)
    return _render(pdf_reports.lesson_report, lesson, meta), lesson


@router.get("/lessons/{lesson_id}/document/preview")
def preview_lesson(lesson_id: UUID, p: Principal = Depends(require("document.generate")),
                   conn: psycopg.Connection = Depends(get_conn)):
    pdf, _ = _lesson_pdf(conn, p, lesson_id, preview=True)
    return Response(pdf, media_type="application/pdf", headers={"Cache-Control": "private, no-store"})


@router.post("/lessons/{lesson_id}/document", status_code=201)
def issue_lesson_document(lesson_id: UUID, p: Principal = Depends(require("document.generate")),
                          conn: psycopg.Connection = Depends(get_conn)):
    lesson = conn.execute("select status from lessons_learned where id = %s and organization_id = %s for update",
                          (lesson_id, p.organization_id)).fetchone()
    if not lesson:
        raise not_found("Lección")
    if lesson["status"] in ("draft", "in_review"):
        raise ApiError(409, "lesson_not_approved", "Solo se emite el PDF de una lección aprobada; usa la vista previa.")
    pdf, data = _lesson_pdf(conn, p, lesson_id, preview=False)
    # Una emisión por revisión de la lección; reemitir la misma revisión crea una nueva emisión documental.
    return issue_document(conn, p, "lesson_learned", pdf, "application/pdf",
                          f"{data['folio']}_rev{data['revision']}.pdf", f"doc:lesson:{lesson_id}",
                          case_id=data["source_case_id"], lesson_id=lesson_id,
                          metadata={"lesson_folio": data["folio"], "lesson_revision": data["revision"]})


# ---- Excel ---------------------------------------------------------------------------------

class CaseFilters(BaseModel):
    q: str | None = Field(None, max_length=100)
    status: str | None = Field(None, max_length=30)
    plant_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


def _case_rows(conn, p: Principal, f: CaseFilters) -> list[dict]:
    where, args = ["c.organization_id = %(org)s"], {"org": p.organization_id}
    if p.plant_ids is not None:
        where.append("c.plant_id = any(%(plants)s)")
        args["plants"] = list(p.plant_ids)
    for cond, key, value in (("c.status = %(status)s", "status", f.status), ("c.plant_id = %(plant)s", "plant", f.plant_id),
                             ("c.created_at::date >= %(from)s", "from", f.date_from),
                             ("c.created_at::date <= %(to)s", "to", f.date_to)):
        if value:
            where.append(cond)
            args[key] = value
    if f.q:
        where.append("(c.folio ilike %(q)s or c.title ilike %(q)s or coalesce(c.part_number,'') ilike %(q)s)")
        args["q"] = f"%{f.q.strip()}%"
    return conn.execute(
        f"""select c.folio, c.title, pl.code as plant, c.status, c.severity, c.source_type, c.customer_name, c.product_name,
                   c.part_number, c.process_name, c.lot_number, c.defect_date, c.detected_quantity, c.affected_quantity,
                   u.display_name as owner, c.target_close_date, c.created_at, c.closed_at,
                   (select min(d.discipline_code) from case_disciplines d where d.case_id = c.id and d.status <> 'approved') as current_discipline,
                   (select count(*) from corrective_actions a where a.case_id = c.id and a.status in ('open','in_progress','pending_approval')) as open_actions
            from cases_8d c join plants pl on pl.id = c.plant_id left join users u on u.id = c.owner_user_id
            where {' and '.join(where)} order by c.created_at desc""", args).fetchall()


@router.post("/exports/cases", status_code=201)
def export_cases(body: CaseFilters, p: Principal = Depends(require("report.export")),
                 conn: psycopg.Connection = Depends(get_conn)):
    rows = _case_rows(conn, p, body)
    header = ["Folio", "Título", "Planta", "Estado", "Severidad", "Origen", "Cliente", "Producto", "Parte", "Proceso", "Lote",
              "Detección", "Cant. detectada", "Cant. afectada", "Responsable", "Cierre objetivo", "Creado", "Cerrado",
              "Disciplina actual", "Acciones abiertas"]
    filters = ", ".join(f"{k}={v}" for k, v in body.model_dump(exclude_none=True).items()) or "sin filtros"
    revision = _next_number(conn, p.organization_id, f"doc:excel:cases:{p.user_id}")
    meta = _meta(conn, p, "excel_export", "Casos 8D", revision, "", None)
    meta["filters"] = filters + (f" · plantas visibles: {len(p.plant_ids)}" if p.plant_ids is not None else "")
    content = _render(excel.workbook, [("Casos", header, [list(r.values()) for r in rows])], meta)
    return issue_document(conn, p, "excel_export", content, storage.XLSX, f"Casos_8D_{date.today():%Y%m%d}_rev{revision}.xlsx",
                          f"doc:excel:cases:{p.user_id}", revision=revision,
                          metadata={"export": "cases", "filters": filters, "rows": len(rows)})


@router.post("/cases/{case_id}/export", status_code=201)
def export_case(case_id: UUID, p: Principal = Depends(require("report.export")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id, for_update=True)
    b = case_bundle(conn, p, case_id, with_photos=False)
    c = b["case"]
    sheets = [
        ("Caso", ["Campo", "Valor"], [[k, v] for k, v in c.items() if k not in ("organization_id", "id", "plant_id",
                                                                                 "opened_by", "owner_user_id", "version")]),
        ("Disciplinas", ["Código", "Disciplina", "Estado", "Pendientes", "Aprobada por", "Fecha"],
         [[d["code"], d["name"], d["status"], "; ".join(r["label"] for r in d["requirements"] if not r["met"]),
           d.get("approved_by_name"), d.get("approved_at")] for d in b["workflow"]]),
        ("Equipo", ["Nombre", "Correo", "Rol"], [[t["display_name"], t["email"], t["role_label"]] for t in b["team"]]),
        ("Contención", ["Acción", "Responsable", "Vence", "Estado", "Revisadas", "Rechazadas", "Evidencia"],
         [[a["description"], a["responsible_name"], a["due_date"], a["status"], a["quantity_checked"], a["quantity_rejected"],
           a["evidence_notes"]] for a in b["containment"]]),
        ("Causas", ["Categoría", "Causa", "Documentado", "Se siguió", "Método", "Evidencia", "Justificación", "Estado"],
         [[x["category_name"], x["potential_cause"], x["documented"], x["followed"], x["verification_method"],
           x["evidence_summary"], x["rationale"], x["investigation_status"]] for x in b["causes"]]),
        ("Acciones", ["Tipo", "Acción", "Causa", "Responsable", "Vence", "Estado", "Evidencia", "Excepción"],
         [[a["type_label"], a["description"], a["cause_text"], a["responsible_name"], a["due_date"], a["status"],
           a["implementation_evidence"], a["evidence_exception"]] for a in b["actions"]]),
        ("Eficacia", ["Acción", "Inicio", "Fin", "Denominador", "Defectos", "Días sin producción", "Regla", "Resultado",
                      "Justificación"],
         [[e["action_description"], e["period_start"], e["period_end"], e["denominator_quantity"], e["defect_quantity"],
           e["days_without_production"], e["computed_result"], e["result"], e["rationale"]] for e in b["checks"]]),
        ("Bitácora", ["Fecha", "Usuario", "Evento", "Antes", "Después", "Solicitud"],
         [[e["occurred_at"], e["actor_name"], e["event_type"], e["old"], e["new"], e.get("request_id")] for e in b["audit"]]),
    ]
    scope = f"doc:excel:case:{case_id}"
    revision = _next_number(conn, p.organization_id, scope)
    meta = _meta(conn, p, "excel_export", c["folio"], revision, pdf_reports.st(c["status"]), c["plant_id"])
    content = _render(excel.workbook, sheets, meta)
    return issue_document(conn, p, "excel_export", content, storage.XLSX, f"{c['folio']}_datos_rev{revision}.xlsx", scope,
                          case_id=case_id, revision=revision, metadata={"export": "case", "case_folio": c["folio"]})


class AuditFilters(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


@router.post("/exports/audit", status_code=201)
def export_audit(body: AuditFilters, p: Principal = Depends(require("audit.read")), conn: psycopg.Connection = Depends(get_conn)):
    if p.plant_ids is not None:
        raise forbidden("La bitácora de toda la organización requiere acceso a todas las plantas.")
    rows = conn.execute(
        """select e.occurred_at, u.display_name, e.event_type, e.entity_type, e.entity_id, c.folio, e.old_values, e.new_values,
                  e.request_id, host(e.ip_address) as ip
           from audit_events e left join users u on u.id = e.actor_user_id left join cases_8d c on c.id = e.case_id
           where e.organization_id = %s and (%s::date is null or e.occurred_at::date >= %s)
             and (%s::date is null or e.occurred_at::date <= %s) order by e.occurred_at desc limit 50000""",
        (p.organization_id, body.date_from, body.date_from, body.date_to, body.date_to)).fetchall()
    revision = _next_number(conn, p.organization_id, "doc:excel:audit")
    meta = _meta(conn, p, "excel_export", "Bitácora", revision, "", None)
    meta["filters"] = f"desde {body.date_from or '—'} hasta {body.date_to or '—'}"
    content = _render(excel.workbook, [("Bitácora", ["Fecha", "Usuario", "Evento", "Entidad", "Id", "Caso", "Antes", "Después",
                                                     "Solicitud", "IP"], [list(r.values()) for r in rows])], meta)
    return issue_document(conn, p, "excel_export", content, storage.XLSX, f"Bitacora_{date.today():%Y%m%d}_rev{revision}.xlsx",
                          "doc:excel:audit", revision=revision, metadata={"export": "audit", "rows": len(rows)})


@router.get("/documents")
def list_documents(kind: str | None = None, p: Principal = Depends(require("case.read")),
                   conn: psycopg.Connection = Depends(get_conn)):
    rows = conn.execute(
        """select d.id, d.document_type, d.revision, d.file_name, d.file_size_bytes, d.sha256_hex, d.status, d.generated_at,
                  d.case_id, d.lesson_id, d.generated_by, d.metadata, u.display_name as generated_by_name, c.folio as case_folio,
                  c.plant_id
           from documents d join users u on u.id = d.generated_by left join cases_8d c on c.id = d.case_id
           where d.organization_id = %s and (%s::text is null or d.document_type = %s)
           order by d.generated_at desc limit 300""", (p.organization_id, kind, kind)).fetchall()
    return [r for r in rows if can_download(p, r)]


def can_download(p: Principal, doc: dict) -> bool:
    if doc.get("case_id"):
        plant = doc.get("plant_id")
        return plant is None or p.sees_plant(plant)
    # Exportaciones de organización: solo quien las generó o quien ve todas las plantas con permiso de auditoría.
    return doc["generated_by"] == p.user_id or (p.plant_ids is None and p.can("audit.read"))


@router.get("/documents/{document_id}/verify")
def verify_document(document_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    doc = conn.execute("""select d.*, c.plant_id from documents d left join cases_8d c on c.id = d.case_id
                          where d.id = %s and d.organization_id = %s""", (document_id, p.organization_id)).fetchone()
    if not doc or not can_download(p, doc):
        raise not_found("Documento")
    result = storage.verify(doc["storage_key"], doc["sha256_hex"])
    audit.record(conn, p, "integrity.verified", "document", document_id, doc["case_id"], new={"ok": result["ok"]})
    return result


@router.get("/attachments/{attachment_id}/verify")
def verify_attachment(attachment_id: UUID, p: Principal = Depends(require("case.read")),
                      conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("select * from attachments where id = %s and organization_id = %s",
                       (attachment_id, p.organization_id)).fetchone()
    if not row:
        raise not_found("Archivo")
    load_case(conn, p, row["case_id"])
    result = storage.verify(row["storage_key"], row["sha256_hex"])
    audit.record(conn, p, "integrity.verified", "attachment", attachment_id, row["case_id"], new={"ok": result["ok"]})
    return result


# ---- Concentrado de 8D (registro con hitos) -----------------------------------------------------

CASE_STATUS = {"draft": "Borrador", "open": "Abierto", "in_progress": "En proceso", "pending_review": "En revisión",
               "approved": "Aprobado", "closed": "Cerrado", "cancelled": "Cancelado"}
MILESTONE_LABEL = {"on_time": "A tiempo", "late": "Tarde", "pending": "En plazo", "overdue": "Vencido"}


class RegisterFilters(BaseModel):
    q: str | None = Field(None, max_length=100)
    case_type: Literal["internal", "external"] | None = None
    status: str | None = Field(None, max_length=30)
    plant_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


def register_rows(conn, p: Principal, f: RegisterFilters) -> list[dict]:
    where, args = ["c.organization_id = %(org)s"], {"org": p.organization_id}
    if p.plant_ids is not None:
        where.append("c.plant_id = any(%(plants)s)")
        args["plants"] = list(p.plant_ids)
    for cond, key, value in (("c.case_type = %(case_type)s", "case_type", f.case_type), ("c.status = %(status)s", "status", f.status),
                             ("c.plant_id = %(plant)s", "plant", f.plant_id), ("c.report_date >= %(from)s", "from", f.date_from),
                             ("c.report_date <= %(to)s", "to", f.date_to)):
        if value:
            where.append(cond)
            args[key] = value
    if f.q:
        where.append("""(c.folio ilike %(q)s or c.title ilike %(q)s or coalesce(c.part_number,'') ilike %(q)s
                         or coalesce(c.customer_name,'') ilike %(q)s or coalesce(c.main_defect,'') ilike %(q)s)""")
        args["q"] = f"%{f.q.strip()}%"
    rows = conn.execute(
        f"""select c.id, c.folio, c.report_date, c.case_type, c.customer_name, c.title, c.market_segment, c.main_defect,
                   c.part_number, c.detected_quantity, c.affected_quantity, c.status, c.closed_at::date as closed_on,
                   c.target_close_date, c.is_demo, pl.code as plant_code,
                   (select u.display_name from case_team t join users u on u.id = t.user_id
                     where t.case_id = c.id and t.team_role = 'leader' limit 1) as leader,
                   (select string_agg(x.potential_cause, '; ' order by x.created_at) from ishikawa_causes x
                     where x.case_id = c.id and x.investigation_status = 'root_cause') as root_cause,
                   (select jsonb_object_agg(d.discipline_code, d.approved_at::date) from case_disciplines d
                     where d.case_id = c.id and d.status = 'approved') as approved,
                   (select min(d.discipline_code) from case_disciplines d where d.case_id = c.id and d.status <> 'approved') as current_discipline
            from cases_8d c join plants pl on pl.id = c.plant_id
            where {' and '.join(where)} order by c.report_date desc, c.folio desc limit 1000""", args).fetchall()
    today = date.today()
    out = []
    for r in rows:
        approved = {k: date.fromisoformat(v) for k, v in (r.pop("approved") or {}).items()}
        ms = workflow.milestones(r["report_date"], approved, today) if r["status"] != "cancelled" else []
        end = r["closed_on"] or today
        overdue = r["status"] not in ("closed", "cancelled") and (
            any(m["status"] == "overdue" for m in ms) or (r["target_close_date"] is not None and r["target_close_date"] < today))
        out.append({**r, "month": r["report_date"].strftime("%Y-%m"), "milestones": ms, "overdue": overdue,
                    "days_open": (end - r["report_date"]).days, "status_label": CASE_STATUS.get(r["status"], r["status"])})
    return out


@router.get("/reports/register")
def register(q: str | None = Query(None, max_length=100), case_type: Literal["internal", "external"] | None = None,
             status: str | None = None, plant_id: UUID | None = None, date_from: date | None = None, date_to: date | None = None,
             p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    rows = register_rows(conn, p, RegisterFilters(q=q, case_type=case_type, status=status, plant_id=plant_id,
                                                  date_from=date_from, date_to=date_to))
    return {"rows": rows, "milestones": [{"key": k, "label": l, "days": d} for k, l, _, d in workflow.MILESTONES]}


@router.post("/exports/register", status_code=201)
def export_register(body: RegisterFilters, p: Principal = Depends(require("report.export")),
                    conn: psycopg.Connection = Depends(get_conn)):
    rows = register_rows(conn, p, body)
    header = ["#", "Mes", "Fecha de reporte", "Tipo", "Cliente", "Descripción de la falla", "OEM | OES | AM", "Defecto principal",
              "Número de parte", "Cantidad", "Causa raíz", "Fecha de cierre", "Líder", "Estado 8D",
              *[f"{label} — real" for _, label, _, _ in workflow.MILESTONES], "Días para cerrar", "Folio", "Planta"]
    data = []
    for i, r in enumerate(rows, start=1):
        ms = {m["key"]: m for m in r["milestones"]}
        cells = [f"{ms[k]['done'] or '—'} ({MILESTONE_LABEL[ms[k]['status']]}, meta {ms[k]['due']})" if k in ms else "—"
                 for k, _, _, _ in workflow.MILESTONES]
        data.append([i, r["month"], r["report_date"], "Interno" if r["case_type"] == "internal" else "Externo",
                     r["customer_name"], r["title"], r["market_segment"], r["main_defect"], r["part_number"],
                     r["detected_quantity"], r["root_cause"], r["closed_on"], r["leader"], r["status_label"], *cells,
                     r["days_open"], r["folio"], r["plant_code"]])
    filters = ", ".join(f"{k}={v}" for k, v in body.model_dump(exclude_none=True).items()) or "sin filtros"
    scope = f"doc:excel:register:{p.user_id}"
    revision = _next_number(conn, p.organization_id, scope)
    meta = _meta(conn, p, "excel_export", "Concentrado 8D", revision, "", None)
    meta["filters"] = filters
    content = _render(excel.workbook, [("Concentrado", header, data)], meta)
    return issue_document(conn, p, "excel_export", content, storage.XLSX, f"Concentrado_8D_{date.today():%Y%m%d}_rev{revision}.xlsx",
                          scope, revision=revision, metadata={"export": "register", "filters": filters, "rows": len(rows)})


# ---- Indicadores -----------------------------------------------------------------------------

KPI_DEFINITIONS = [
    {"id": "open_cases", "name": "Casos abiertos", "definition": "Casos cuyo estado no es cerrado ni cancelado.",
     "source": "cases_8d.status", "rule": "count(status ∉ {closed, cancelled}); filtros de planta y fecha de alta"},
    {"id": "closed_cases", "name": "Casos cerrados", "definition": "Casos con D8 aprobada (estado cerrado) en el periodo.",
     "source": "cases_8d.closed_at", "rule": "count(status = closed y closed_at dentro del periodo)"},
    {"id": "by_status", "name": "Casos por estado", "definition": "Distribución de casos por estado.", "source": "cases_8d.status",
     "rule": "count agrupado por status"},
    {"id": "by_discipline", "name": "Casos abiertos por disciplina", "definition": "Primera disciplina no aprobada de cada caso abierto.",
     "source": "case_disciplines", "rule": "min(discipline_code) con status ≠ approved"},
    {"id": "overdue_cases", "name": "Casos vencidos", "definition": "Casos abiertos con fecha objetivo de cierre anterior a hoy.",
     "source": "cases_8d.target_close_date", "rule": "Los casos sin fecha objetivo se informan aparte y no cuentan como vencidos"},
    {"id": "open_actions", "name": "Acciones abiertas y vencidas",
     "definition": "Contenciones y acciones correctivas/preventivas/sistémicas sin cerrar; vencida = fecha compromiso < hoy.",
     "source": "containment_actions, corrective_actions", "rule": "Abiertas: contención ∉ {verified, cancelled}; acciones ∈ {open, in_progress, pending_approval}"},
    {"id": "resolution_days", "name": "Tiempo de resolución", "definition": "Días naturales entre el alta y el cierre del caso.",
     "source": "cases_8d.created_at, closed_at", "rule": "Mediana y media de casos cerrados en el periodo; se muestra con n ≥ 3", "min_n": 3},
    {"id": "effectiveness", "name": "Acciones eficaces y no eficaces",
     "definition": "Último resultado decidido de verificación de eficacia por acción.", "source": "effectiveness_checks.result",
     "rule": "Conteos siempre; porcentaje solo con n ≥ 5 decisiones (eficaz + no eficaz). «Datos insuficientes» no cuenta en el porcentaje", "min_n": 5},
    {"id": "distribution", "name": "Distribución de problemas", "definition": "Casos por cliente, producto, proceso y planta.",
     "source": "cases_8d", "rule": "Se muestra con n ≥ 3 casos; valores vacíos se agrupan como «Sin dato»", "min_n": 3},
]


@router.get("/reports/kpis")
def kpis(plant_id: UUID | None = None, date_from: date | None = None, date_to: date | None = None,
         p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    if date_from and date_to and date_from > date_to:
        raise invalid("La fecha inicial es posterior a la final.")
    if plant_id and not p.sees_plant(plant_id):
        raise not_found("Planta")
    where, args = ["c.organization_id = %(org)s"], {"org": p.organization_id, "from": date_from, "to": date_to}
    if p.plant_ids is not None:
        where.append("c.plant_id = any(%(plants)s)")
        args["plants"] = list(p.plant_ids)
    if plant_id:
        where.append("c.plant_id = %(plant)s")
        args["plant"] = plant_id
    base = " and ".join(where)
    created = base + " and (%(from)s::date is null or c.created_at::date >= %(from)s) and (%(to)s::date is null or c.created_at::date <= %(to)s)"

    def one(sql: str) -> dict:
        return conn.execute(sql, args).fetchone()

    def many(sql: str) -> list[dict]:
        return conn.execute(sql, args).fetchall()

    by_status = {r["status"]: r["n"] for r in many(f"select status, count(*)::int as n from cases_8d c where {created} group by status")}
    open_cases = sum(n for s, n in by_status.items() if s not in ("closed", "cancelled"))
    closed = one(f"""select count(*)::int as n from cases_8d c where {base} and c.status = 'closed'
                     and (%(from)s::date is null or c.closed_at::date >= %(from)s) and (%(to)s::date is null or c.closed_at::date <= %(to)s)""")["n"]
    by_discipline = {r["d"]: r["n"] for r in many(
        f"""select (select min(d.discipline_code) from case_disciplines d where d.case_id = c.id and d.status <> 'approved') as d,
                   count(*)::int as n from cases_8d c where {created} and c.status not in ('closed','cancelled') group by 1 order by 1""")}
    overdue = one(f"""select count(*) filter (where c.target_close_date < current_date)::int as overdue,
                             count(*) filter (where c.target_close_date is null)::int as without_target
                      from cases_8d c where {created} and c.status not in ('closed','cancelled')""")
    actions = one(f"""select
        (select count(*) from containment_actions a join cases_8d c on c.id = a.case_id where {created}
           and a.status not in ('verified','cancelled'))::int as containment_open,
        (select count(*) from containment_actions a join cases_8d c on c.id = a.case_id where {created}
           and a.status not in ('verified','cancelled') and a.due_date < current_date)::int as containment_overdue,
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where {created}
           and a.status in ('open','in_progress','pending_approval'))::int as actions_open,
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where {created}
           and a.status in ('open','in_progress') and a.due_date < current_date)::int as actions_overdue,
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where {created}
           and a.status = 'pending_approval')::int as actions_pending_approval""")
    durations = [r["days"] for r in many(
        f"""select extract(epoch from (c.closed_at - c.created_at)) / 86400.0 as days from cases_8d c where {base}
            and c.status = 'closed' and (%(from)s::date is null or c.closed_at::date >= %(from)s)
            and (%(to)s::date is null or c.closed_at::date <= %(to)s) order by 1""")]
    resolution = {"n": len(durations), "sufficient": len(durations) >= 3}
    if resolution["sufficient"]:
        mid = len(durations) // 2
        median = durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2
        resolution.update(median_days=round(float(median), 1), mean_days=round(float(sum(durations) / len(durations)), 1))
    eff = {r["result"]: r["n"] for r in many(
        f"""select result, count(*)::int as n from (
              select distinct on (e.action_id) e.result from effectiveness_checks e join cases_8d c on c.id = e.case_id
              where {created} and e.result <> 'pending' order by e.action_id, e.decided_at desc) x group by result""")}
    decided = eff.get("effective", 0) + eff.get("ineffective", 0)
    effectiveness = {"effective": eff.get("effective", 0), "ineffective": eff.get("ineffective", 0),
                     "insufficient_data": eff.get("insufficient_data", 0), "n": decided, "sufficient": decided >= 5,
                     "effective_pct": round(100 * eff.get("effective", 0) / decided, 1) if decided >= 5 else None}
    total_cases = sum(by_status.values())
    distribution = {"n": total_cases, "sufficient": total_cases >= 3}
    if distribution["sufficient"]:
        for key, expr in (("customer", "c.customer_name"), ("product", "coalesce(c.product_name, c.part_number)"),
                          ("process", "c.process_name"), ("plant", "pl.code")):
            distribution[key] = many(f"""select coalesce(nullif(trim({expr}), ''), 'Sin dato') as label, count(*)::int as n
                                         from cases_8d c join plants pl on pl.id = c.plant_id where {created}
                                         group by 1 order by 2 desc, 1 limit 10""")
    return {"filters": {"plant_id": plant_id, "date_from": date_from, "date_to": date_to},
            "definitions": KPI_DEFINITIONS, "open_cases": open_cases, "closed_cases": closed, "by_status": by_status,
            "by_discipline": by_discipline, "overdue_cases": overdue["overdue"], "cases_without_target": overdue["without_target"],
            "actions": actions, "resolution": resolution, "effectiveness": effectiveness, "distribution": distribution}
