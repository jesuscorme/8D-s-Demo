"""Fase 9: biblioteca de lecciones aprendidas (revisiones inmutables, revisión/aprobación, publicación y reutilización)."""
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app import audit, storage, workflow
from app.auth import Principal, get_conn, require
from app.cases import load_case, refresh_case_status, rule, snapshot, touch
from app.errors import ApiError, invalid, not_found
from app.routers.cases_routes import _next_number

router = APIRouter(tags=["lessons"])

CONTENT = ["title", "problem_summary", "verified_root_cause", "actions_summary", "effectiveness_summary",
           "before_summary", "after_summary", "documents_updated", "training_summary", "products", "processes",
           "plant_codes", "situations", "language_code"]
REQUIRED = {"title": "Título", "problem_summary": "Problema original", "verified_root_cause": "Causa raíz verificada",
            "actions_summary": "Acciones implementadas", "effectiveness_summary": "Resultados de eficacia",
            "before_summary": "Situación antes", "after_summary": "Situación después"}

TextList = list[str]


class LessonPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    problem_summary: str | None = Field(None, max_length=4000)
    verified_root_cause: str | None = Field(None, max_length=4000)
    actions_summary: str | None = Field(None, max_length=4000)
    effectiveness_summary: str | None = Field(None, max_length=4000)
    before_summary: str | None = Field(None, max_length=4000)
    after_summary: str | None = Field(None, max_length=4000)
    documents_updated: TextList | None = Field(None, max_length=50)
    training_summary: str | None = Field(None, max_length=4000)
    products: TextList | None = Field(None, max_length=50)
    processes: TextList | None = Field(None, max_length=50)
    plant_codes: TextList | None = Field(None, max_length=50)
    situations: TextList | None = Field(None, max_length=50)
    language_code: Literal["es", "en"] | None = None


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(None, max_length=2000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


class ApplyIn(BaseModel):
    target_case_id: UUID
    evaluation: str = Field(min_length=5, max_length=4000)
    outcome: Literal["applied", "partially_applied", "not_applicable"]
    application_notes: str | None = Field(None, max_length=4000)


def _clean_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    seen: list[str] = []
    for v in values:
        v = v.strip()[:200]
        if v and v not in seen:
            seen.append(v)
    return seen


def _visible_statuses(p: Principal) -> list[str] | None:
    """Quien no edita lecciones solo consulta las publicadas."""
    return None if p.can("lesson.edit") else ["published"]


def _load(conn, p: Principal, lesson_id: UUID, for_update=False) -> dict:
    row = conn.execute("select * from lessons_learned where id = %s and organization_id = %s"
                       + (" for update" if for_update else ""), (lesson_id, p.organization_id)).fetchone()
    visible = _visible_statuses(p)
    if not row or (visible and row["status"] not in visible):
        raise not_found("Lección")
    return row


def _detail(conn, p: Principal, lesson_id: UUID) -> dict:
    row = _load(conn, p, lesson_id)
    names = conn.execute(
        """select c.folio as source_folio, c.title as source_title, a.display_name as created_by_name,
                  s.display_name as submitted_by_name, r.display_name as reviewed_by_name,
                  pb.display_name as published_by_name, rt.display_name as retired_by_name
           from lessons_learned l join cases_8d c on c.id = l.source_case_id join users a on a.id = l.created_by
           left join users s on s.id = l.submitted_by left join users r on r.id = l.reviewed_by
           left join users pb on pb.id = l.published_by left join users rt on rt.id = l.retired_by where l.id = %s""",
        (lesson_id,)).fetchone()
    visible = _visible_statuses(p)
    revisions = conn.execute(
        """select l.id, l.revision, l.status, l.revision_reason, l.published_at, l.created_at
           from lessons_learned l where l.organization_id = %s and l.lesson_number = %s
             and (%s::text[] is null or l.status = any(%s::text[])) order by l.revision desc""",
        (p.organization_id, row["lesson_number"], visible, visible)).fetchall()
    applications = conn.execute(
        """select ap.id, ap.lesson_id, ap.evaluation, ap.outcome, ap.application_notes, ap.applied_at, l.revision,
                  c.id as target_case_id, c.folio as target_folio, c.title as target_title, u.display_name as applied_by_name
           from lesson_applications ap join lessons_learned l on l.id = ap.lesson_id
           join cases_8d c on c.id = ap.target_case_id join users u on u.id = ap.applied_by
           where l.organization_id = %s and l.lesson_number = %s order by ap.applied_at desc""",
        (p.organization_id, row["lesson_number"])).fetchall()
    documents = conn.execute(
        """select id, revision, file_name, sha256_hex, status, generated_at from documents
           where lesson_id = %s order by generated_at desc""", (lesson_id,)).fetchall()
    photos = conn.execute(
        """select lp.attachment_id, lp.kind, lp.caption, lp.sort_order, f.file_name from lesson_photos lp
           join attachments f on f.id = lp.attachment_id where lp.lesson_id = %s order by lp.kind desc, lp.sort_order""",
        (lesson_id,)).fetchall()
    missing = [label for key, label in REQUIRED.items() if not (row.get(key) or "").strip()]
    if not (row["products"] or row["processes"] or row["plant_codes"] or row["situations"]):
        missing.append("Aplicabilidad (producto, proceso, planta o situación)")
    for kind, label in (("before", "Foto del antes"), ("after", "Foto del después")):
        if not any(ph["kind"] == kind for ph in photos):
            missing.append(label)
    return {**row, **names, "folio": f"LA-{row['lesson_number']:04d}", "revisions": revisions,
            "applications": applications, "documents": documents, "photos": photos,
            "missing_to_submit": missing if row["status"] == "draft" else []}


@router.get("/lessons")
def list_lessons(q: str | None = Query(None, max_length=100), status: str | None = None,
                 process: str | None = Query(None, max_length=100), product: str | None = Query(None, max_length=100),
                 plant: str | None = Query(None, max_length=50), language: Literal["es", "en"] | None = None,
                 p: Principal = Depends(require("lesson.read")), conn: psycopg.Connection = Depends(get_conn)):
    where, args = ["l.organization_id = %(org)s"], {"org": p.organization_id}
    visible = _visible_statuses(p)
    if visible:
        where.append("l.status = any(%(visible)s)")
        args["visible"] = visible
    if status:
        where.append("l.status = %(status)s")
        args["status"] = status
    if q:
        where.append("""(l.title ilike %(q)s or l.problem_summary ilike %(q)s or l.verified_root_cause ilike %(q)s
                         or l.actions_summary ilike %(q)s or array_to_string(l.situations, ' ') ilike %(q)s)""")
        args["q"] = f"%{q.strip()}%"
    for key, column, value in (("process", "processes", process), ("product", "products", product),
                               ("plant", "plant_codes", plant)):
        if value:
            where.append(f"exists (select 1 from unnest(l.{column}) x where x ilike %({key})s)")
            args[key] = f"%{value.strip()}%"
    if language:
        where.append("l.language_code = %(lang)s")
        args["lang"] = language
    rows = conn.execute(
        f"""select l.id, l.lesson_number, l.revision, l.title, l.status, l.language_code, l.products, l.processes,
                   l.plant_codes, l.situations, l.published_at, l.updated_at, c.folio as source_folio,
                   (select count(*)::int from lesson_applications ap join lessons_learned x on x.id = ap.lesson_id
                     where x.organization_id = l.organization_id and x.lesson_number = l.lesson_number) as application_count
            from lessons_learned l join cases_8d c on c.id = l.source_case_id
            where {' and '.join(where)} order by l.lesson_number desc, l.revision desc limit 300""", args).fetchall()
    return [{**r, "folio": f"LA-{r['lesson_number']:04d}"} for r in rows]


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: UUID, p: Principal = Depends(require("lesson.read")), conn: psycopg.Connection = Depends(get_conn)):
    return _detail(conn, p, lesson_id)


@router.post("/cases/{case_id}/lessons", status_code=201)
def create_from_case(case_id: UUID, p: Principal = Depends(require("lesson.edit")),
                     conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    snap = snapshot(conn, case)
    if snap.status.get("D4") != "approved":
        raise ApiError(409, "root_cause_not_verified", "La lección requiere la causa raíz verificada (D4 aprobada).")
    roots = conn.execute("""select potential_cause from ishikawa_causes where case_id = %s and investigation_status = 'root_cause'
                            order by created_at""", (case_id,)).fetchall()
    d4 = snap.content.get("D4", {})
    actions = conn.execute("""select action_type, description, status from corrective_actions
                              where case_id = %s and status <> 'cancelled' order by created_at""", (case_id,)).fetchall()
    checks = conn.execute("""select e.result, e.rationale, a.description from effectiveness_checks e
                             join corrective_actions a on a.id = e.action_id
                             where e.case_id = %s and e.result <> 'pending' order by e.decided_at""", (case_id,)).fetchall()
    updates = conn.execute("""select document_reference from system_updates where case_id = %s and status = 'completed'""",
                           (case_id,)).fetchall()
    plant = conn.execute("select code from plants where id = %s", (case["plant_id"],)).fetchone()
    labels = {"corrective": "Correctiva", "preventive": "Preventiva", "systemic": "Sistémica"}
    result = {"effective": "eficaz", "ineffective": "no eficaz", "insufficient_data": "datos insuficientes"}
    # Prellenado desde el expediente: el autor lo revisa; el expediente original no se modifica.
    prefill = {
        "title": f"Lección de {case['folio']}: {case['title']}"[:200],
        "problem_summary": case["problem_description"],
        "verified_root_cause": "\n".join([f"• {r['potential_cause']}" for r in roots]
                                         + [f"{label}: {d4[k]}" for k, label in (("occurrence_cause", "Ocurrencia"),
                                                                                 ("escape_point", "Punto de escape"))
                                            if d4.get(k)]),
        "actions_summary": "\n".join(f"• [{labels[a['action_type']]}] {a['description']}" for a in actions),
        "effectiveness_summary": "\n".join(f"• {c['description']}: {result[c['result']]} — {c['rationale']}" for c in checks) or None,
        "documents_updated": [u["document_reference"] for u in updates],
        "products": [x for x in (case["product_name"], case["part_number"]) if x],
        "processes": [case["process_name"]] if case["process_name"] else [],
        "plant_codes": [plant["code"]],
    }
    number = _next_number(conn, p.organization_id, "lesson")
    cols = ", ".join(prefill)
    row = conn.execute(
        f"""insert into lessons_learned (organization_id, source_case_id, lesson_number, created_by, {cols})
            values (%s, %s, %s, %s, {', '.join(['%s'] * len(prefill))}) returning id""",
        [p.organization_id, case_id, number, p.user_id, *prefill.values()]).fetchone()
    touch(conn, case_id)
    audit.record(conn, p, "lesson.created", "lesson", row["id"], case_id, new={"lesson_number": number, "revision": 1})
    return _detail(conn, p, row["id"])


@router.patch("/lessons/{lesson_id}")
def update_lesson(lesson_id: UUID, body: LessonPatch, p: Principal = Depends(require("lesson.edit")),
                  conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "draft":
        raise ApiError(409, "lesson_locked", "Solo se edita un borrador. Crea una nueva revisión para cambiar una lección publicada.")
    changes = body.model_dump(exclude_unset=True)
    for key in ("documents_updated", "products", "processes", "plant_codes", "situations"):
        if key in changes:
            changes[key] = _clean_list(changes[key]) or []
    if "title" in changes and not changes["title"]:
        raise invalid("El título es obligatorio.")
    for key in ("problem_summary", "verified_root_cause", "actions_summary"):
        if key in changes and changes[key] is None:
            changes[key] = ""
    old, new = audit.diff(row, changes)
    if new:
        conn.execute(f"update lessons_learned set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), lesson_id])
        audit.record(conn, p, "lesson.updated", "lesson", lesson_id, row["source_case_id"], old=old, new=new)
    return _detail(conn, p, lesson_id)


def _set_status(conn, p: Principal, row: dict, to: str, event: str, sets: str = "", args: list | None = None,
                metadata: dict | None = None) -> dict:
    conn.execute(f"update lessons_learned set status = %s{sets}, updated_at = now() where id = %s",
                 [to, *(args or []), row["id"]])
    audit.record(conn, p, event, "lesson", row["id"], row["source_case_id"], old={"status": row["status"]},
                 new={"status": to}, metadata=metadata)
    refresh_case_status(conn, row["source_case_id"])
    return _detail(conn, p, row["id"])


@router.post("/lessons/{lesson_id}/submit")
def submit(lesson_id: UUID, p: Principal = Depends(require("lesson.edit")), conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "draft":
        raise ApiError(409, "invalid_transition", "Solo se envía a revisión un borrador.")
    missing = _detail(conn, p, lesson_id)["missing_to_submit"]
    if missing:
        raise ApiError(409, "requirements_pending", "Faltan datos para enviar la lección a revisión.", missing)
    return _set_status(conn, p, row, "in_review", "lesson.submitted", ", submitted_by = %s, submitted_at = now(), review_comment = null",
                       [p.user_id])


@router.post("/lessons/{lesson_id}/review")
def review(lesson_id: UUID, body: ReviewIn, p: Principal = Depends(require("lesson.review")),
           conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "in_review":
        raise ApiError(409, "invalid_transition", "La lección no está en revisión.")
    if p.user_id in (row["created_by"], row["submitted_by"]):
        raise ApiError(409, "same_person", "El revisor debe ser distinto del autor y de quien la envió.")
    if body.decision == "reject":
        if not (body.comment and body.comment.strip()):
            raise invalid("Indica el motivo del rechazo.")
        return _set_status(conn, p, row, "draft", "lesson.rejected", ", review_comment = %s", [body.comment.strip()])
    return _set_status(conn, p, row, "approved", "lesson.approved", ", reviewed_by = %s, reviewed_at = now(), review_comment = %s",
                       [p.user_id, body.comment])


@router.post("/lessons/{lesson_id}/publish")
def publish(lesson_id: UUID, p: Principal = Depends(require("lesson.publish")), conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "approved":
        raise ApiError(409, "invalid_transition", "Solo se publica una lección aprobada.")
    previous = conn.execute("""select * from lessons_learned where organization_id = %s and lesson_number = %s
                               and status = 'published' for update""", (p.organization_id, row["lesson_number"])).fetchone()
    if previous:
        _set_status(conn, p, previous, "superseded", "lesson.superseded", metadata={"superseded_by": str(row["id"])})
    return _set_status(conn, p, row, "published", "lesson.published", ", published_by = %s, published_at = now()", [p.user_id])


@router.post("/lessons/{lesson_id}/retire")
def retire(lesson_id: UUID, body: ReasonIn, p: Principal = Depends(require("lesson.retire")),
           conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "published":
        raise ApiError(409, "invalid_transition", "Solo se retira una lección publicada.")
    return _set_status(conn, p, row, "retired", "lesson.retired", ", retired_by = %s, retired_at = now(), retire_reason = %s",
                       [p.user_id, body.reason.strip()])


@router.post("/lessons/{lesson_id}/revise", status_code=201)
def revise(lesson_id: UUID, body: ReasonIn, p: Principal = Depends(require("lesson.edit")),
           conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] not in ("published", "retired"):
        raise ApiError(409, "invalid_transition", "Solo se revisa una lección publicada o retirada.")
    if conn.execute("""select 1 from lessons_learned where organization_id = %s and lesson_number = %s
                       and status in ('draft', 'in_review', 'approved')""", (p.organization_id, row["lesson_number"])).fetchone():
        raise ApiError(409, "draft_exists", "Ya existe una revisión en curso de esta lección.")
    top = conn.execute("select max(revision) as r from lessons_learned where organization_id = %s and lesson_number = %s",
                       (p.organization_id, row["lesson_number"])).fetchone()["r"]
    cols = ", ".join(CONTENT)
    new = conn.execute(
        f"""insert into lessons_learned (organization_id, source_case_id, lesson_number, revision, revision_reason, created_by, {cols})
            select organization_id, source_case_id, lesson_number, %s, %s, %s, {cols} from lessons_learned where id = %s
            returning id""", (top + 1, body.reason.strip(), p.user_id, lesson_id)).fetchone()
    conn.execute("""insert into lesson_photos (organization_id, lesson_id, attachment_id, kind, caption, sort_order)
                    select organization_id, %s, attachment_id, kind, caption, sort_order from lesson_photos where lesson_id = %s""",
                 (new["id"], lesson_id))
    audit.record(conn, p, "lesson.revision_started", "lesson", new["id"], row["source_case_id"],
                 new={"revision": top + 1, "reason": body.reason.strip()}, metadata={"from_lesson_id": str(lesson_id)})
    return _detail(conn, p, new["id"])


# ---- Antes y después (fotos) ----------------------------------------------------------------

class LessonPhoto(BaseModel):
    attachment_id: UUID
    kind: Literal["before", "after"]
    caption: str | None = Field(None, max_length=300)


class LessonPhotosIn(BaseModel):
    photos: list[LessonPhoto] = Field(max_length=8)


def _draft_lesson(conn, p: Principal, lesson_id: UUID) -> dict:
    row = _load(conn, p, lesson_id, for_update=True)
    if row["status"] != "draft":
        raise ApiError(409, "lesson_locked", "Las fotos solo se modifican en borrador. Crea una nueva revisión.")
    return row


@router.put("/lessons/{lesson_id}/photos")
def set_photos(lesson_id: UUID, body: LessonPhotosIn, p: Principal = Depends(require("lesson.edit")),
               conn: psycopg.Connection = Depends(get_conn)):
    row = _draft_lesson(conn, p, lesson_id)
    ids = [ph.attachment_id for ph in body.photos]
    if len(set(ids)) != len(ids):
        raise invalid("Una imagen aparece más de una vez.")
    valid = {r["id"] for r in conn.execute(
        """select id from attachments where id = any(%s) and case_id = %s and mime_type in ('image/png', 'image/jpeg')""",
        (ids, row["source_case_id"])).fetchall()}
    if valid != set(ids):
        raise invalid("Las fotos deben ser imágenes PNG/JPEG del caso de origen.")
    conn.execute("delete from lesson_photos where lesson_id = %s", (lesson_id,))
    for i, ph in enumerate(body.photos):
        conn.execute("""insert into lesson_photos (organization_id, lesson_id, attachment_id, kind, caption, sort_order)
                        values (%s, %s, %s, %s, %s, %s)""",
                     (p.organization_id, lesson_id, ph.attachment_id, ph.kind, (ph.caption or "").strip() or None, i))
    audit.record(conn, p, "lesson.photos_changed", "lesson", lesson_id, row["source_case_id"],
                 new={"photos": [{**ph.model_dump(), "attachment_id": str(ph.attachment_id)} for ph in body.photos]})
    return _detail(conn, p, lesson_id)


@router.post("/lessons/{lesson_id}/photos/upload", status_code=201)
async def upload_photo(lesson_id: UUID, file: UploadFile = File(...), kind: Literal["before", "after"] = Form(...),
                       caption: str | None = Form(None, max_length=300), p: Principal = Depends(require("lesson.edit")),
                       conn: psycopg.Connection = Depends(get_conn)):
    content = await file.read(storage.MAX_BYTES + 1)
    mime = storage.sniff(content)
    if mime not in ("image/png", "image/jpeg"):
        raise invalid("La foto debe ser PNG o JPEG.")
    row = _draft_lesson(conn, p, lesson_id)
    # La imagen se guarda como adjunto del caso de origen (aunque esté cerrado): forma parte de la lección, no del 8D.
    key, digest = storage.save(p.organization_id, content, mime)
    att = conn.execute(
        """insert into attachments (organization_id, case_id, purpose, storage_key, file_name, mime_type, file_size_bytes,
                                    sha256_hex, description, uploaded_by)
           values (%s, %s, 'photo', %s, %s, %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, row["source_case_id"], key, storage.safe_name(file.filename, mime), mime, len(content), digest,
         f"Lección LA-{row['lesson_number']:04d}: {'antes' if kind == 'before' else 'después'}", p.user_id)).fetchone()
    order = conn.execute("select coalesce(max(sort_order) + 1, 0) as n from lesson_photos where lesson_id = %s",
                         (lesson_id,)).fetchone()["n"]
    conn.execute("""insert into lesson_photos (organization_id, lesson_id, attachment_id, kind, caption, sort_order)
                    values (%s, %s, %s, %s, %s, %s)""",
                 (p.organization_id, lesson_id, att["id"], kind, (caption or "").strip() or None, order))
    audit.record(conn, p, "attachment.uploaded", "attachment", att["id"], row["source_case_id"],
                 new={"file_name": file.filename, "sha256": digest, "lesson": f"LA-{row['lesson_number']:04d}", "kind": kind})
    return _detail(conn, p, lesson_id)


@router.post("/lessons/{lesson_id}/apply", status_code=201)
def apply(lesson_id: UUID, body: ApplyIn, p: Principal = Depends(require("lesson.apply")),
          conn: psycopg.Connection = Depends(get_conn)):
    row = _load(conn, p, lesson_id)
    if row["status"] != "published":
        raise ApiError(409, "not_published", "Solo se reutilizan lecciones publicadas.")
    target = load_case(conn, p, body.target_case_id, for_update=True)
    if target["id"] == row["source_case_id"]:
        raise invalid("La lección proviene de ese mismo caso.")
    rule(workflow.check_case_open, snapshot(conn, target))
    if conn.execute("select 1 from lesson_applications where lesson_id = %s and target_case_id = %s",
                    (lesson_id, target["id"])).fetchone():
        raise ApiError(409, "duplicate", "Esta revisión de la lección ya está vinculada a ese caso.")
    app_row = conn.execute(
        """insert into lesson_applications (organization_id, lesson_id, target_case_id, evaluation, outcome,
                                            application_notes, applied_by) values (%s, %s, %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, lesson_id, target["id"], body.evaluation.strip(), body.outcome, body.application_notes,
         p.user_id)).fetchone()
    touch(conn, target["id"])
    # Se registra en el caso destino; ni la lección ni el expediente de origen se modifican.
    audit.record(conn, p, "lesson.applied", "lesson_application", app_row["id"], target["id"],
                 new={"lesson": f"LA-{row['lesson_number']:04d} rev {row['revision']}", "outcome": body.outcome,
                      "evaluation": body.evaluation.strip()})
    return _detail(conn, p, lesson_id)


@router.get("/cases/{case_id}/lessons")
def case_lessons(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    visible = _visible_statuses(p)
    origin = conn.execute(
        """select id, lesson_number, revision, title, status, published_at from lessons_learned
           where source_case_id = %s and (%s::text[] is null or status = any(%s::text[]))
           order by lesson_number, revision desc""", (case_id, visible, visible)).fetchall()
    applied = conn.execute(
        """select ap.id, ap.outcome, ap.evaluation, ap.application_notes, ap.applied_at, l.id as lesson_id,
                  l.lesson_number, l.revision, l.title, u.display_name as applied_by_name
           from lesson_applications ap join lessons_learned l on l.id = ap.lesson_id join users u on u.id = ap.applied_by
           where ap.target_case_id = %s order by ap.applied_at desc""", (case_id,)).fetchall()
    return {"origin": [{**r, "folio": f"LA-{r['lesson_number']:04d}"} for r in origin],
            "applied": [{**r, "folio": f"LA-{r['lesson_number']:04d}"} for r in applied]}
