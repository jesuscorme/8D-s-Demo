"""D4: categorías 6M, biblioteca de ideas, causas del expediente y su validación."""
from datetime import date
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, causes_rules
from app.auth import Principal, get_conn, require
from app.cases import ensure_section_editable, load_case, refresh_case_status, same_org_user, touch
from app.errors import ApiError, invalid, not_found

router = APIRouter(tags=["ishikawa"])

Answer = Literal["yes", "no", "unknown", "not_applicable"]
Decision = Literal["pending", "investigating", "root_cause", "not_root_cause", "needs_more_investigation"]
DECIDED = {"root_cause", "not_root_cause"}


class IdeaIn(BaseModel):
    category_id: UUID
    title_es: str = Field(min_length=3, max_length=300)
    title_en: str | None = Field(None, max_length=300)
    description_es: str | None = Field(None, max_length=2000)
    process_tags: list[str] = Field(default_factory=list, max_length=20)
    defect_tags: list[str] = Field(default_factory=list, max_length=20)


class IdeaPatch(BaseModel):
    title_es: str | None = Field(None, min_length=3, max_length=300)
    title_en: str | None = Field(None, max_length=300)
    description_es: str | None = Field(None, max_length=2000)
    process_tags: list[str] | None = Field(None, max_length=20)
    defect_tags: list[str] | None = Field(None, max_length=20)
    is_active: bool | None = None


class CauseIn(BaseModel):
    category_id: UUID
    potential_cause: str | None = Field(None, max_length=500)
    source_idea_id: UUID | None = None
    parent_cause_id: UUID | None = None
    notes: str | None = Field(None, max_length=2000)


class CausePatch(BaseModel):
    potential_cause: str | None = Field(None, min_length=1, max_length=500)
    category_id: UUID | None = None
    notes: str | None = Field(None, max_length=2000)


class ValidationIn(BaseModel):
    documented_answer: Answer = "unknown"
    followed_process_answer: Answer = "unknown"
    verification_method: str | None = Field(None, max_length=1000)
    evidence_summary: str | None = Field(None, max_length=2000)
    rationale: str | None = Field(None, max_length=2000)
    decision: Decision
    responsible_user_id: UUID | None = None
    due_date: date | None = None


def _tags(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    return sorted({causes_rules.normalize(v).replace(" ", "_") for v in values if causes_rules.normalize(v)})


@router.get("/ishikawa/categories")
def categories(_: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    return conn.execute("select id, code, name_es, name_en, display_order from ishikawa_categories order by display_order"
                        ).fetchall()


def _ideas(conn, p: Principal, include_inactive=False) -> list[dict]:
    return conn.execute(
        f"""select i.id, i.category_id, k.code as category_code, i.title_es, i.title_en, i.description_es,
                   i.process_tags, i.defect_tags, i.is_active, (i.organization_id is null) as is_base
            from cause_ideas i join ishikawa_categories k on k.id = i.category_id
            where (i.organization_id is null or i.organization_id = %s){'' if include_inactive else ' and i.is_active'}
            order by k.display_order, i.title_es""", (p.organization_id,)).fetchall()


@router.get("/cause-ideas")
def list_ideas(include_inactive: bool = False, p: Principal = Depends(require("case.read")),
               conn: psycopg.Connection = Depends(get_conn)):
    return _ideas(conn, p, include_inactive)


@router.post("/cause-ideas", status_code=201)
def create_idea(body: IdeaIn, p: Principal = Depends(require("catalog.manage")),
                conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute(
        """insert into cause_ideas (organization_id, category_id, title_es, title_en, description_es, process_tags,
                                    defect_tags, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (p.organization_id, body.category_id, body.title_es.strip(), body.title_en, body.description_es,
         _tags(body.process_tags), _tags(body.defect_tags), p.user_id)).fetchone()
    audit.record(conn, p, "cause_idea.created", "cause_idea", row["id"], new=body.model_dump())
    return next(i for i in _ideas(conn, p, True) if i["id"] == row["id"])


@router.patch("/cause-ideas/{idea_id}")
def update_idea(idea_id: UUID, body: IdeaPatch, p: Principal = Depends(require("catalog.manage")),
                conn: psycopg.Connection = Depends(get_conn)):
    idea = conn.execute("select * from cause_ideas where id = %s and organization_id = %s",
                        (idea_id, p.organization_id)).fetchone()
    if not idea:
        # Las ideas del catálogo base (organization_id NULL) no se editan desde una organización.
        raise not_found("Idea de la biblioteca de tu organización")
    changes = body.model_dump(exclude_unset=True)
    for key in ("process_tags", "defect_tags"):
        if key in changes:
            changes[key] = _tags(changes[key])
    old, new = audit.diff(idea, changes)
    if new:
        conn.execute(f"update cause_ideas set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), idea_id])
        audit.record(conn, p, "cause_idea.updated", "cause_idea", idea_id, old=old, new=new)
    return next(i for i in _ideas(conn, p, True) if i["id"] == idea_id)


@router.get("/cases/{case_id}/suggestions")
def suggestions(case_id: UUID, p: Principal = Depends(require("case.read")),
                conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id)
    d2 = conn.execute("select content from case_disciplines where case_id = %s and discipline_code = 'D2'",
                      (case_id,)).fetchone()
    content = d2["content"] if d2 else {}
    used = {r["source_idea_id"] for r in conn.execute(
        "select source_idea_id from ishikawa_causes where case_id = %s and source_idea_id is not null", (case_id,))}
    text = {"process": case["process_name"], "title": case["title"], "problem": case["problem_description"],
            "what": content.get("what"), "product": case["product_name"]}
    return causes_rules.suggest(text, _ideas(conn, p), used)


def _causes(conn, case_id: UUID) -> list[dict]:
    rows = conn.execute(
        """select c.*, k.code as category_code, k.name_es as category_name, u.display_name as added_by_name,
                  (select count(*)::int from cause_validations v where v.cause_id = c.id) as validation_count,
                  (select count(*)::int from attachments f where f.cause_id = c.id) as attachment_count,
                  lv.documented_answer, lv.followed_process_answer, lv.verification_method, lv.evidence_summary,
                  lv.rationale, lv.validated_at, lv.due_date, lvu.display_name as validated_by_name,
                  lr.display_name as responsible_name, lv.responsible_user_id
           from ishikawa_causes c join ishikawa_categories k on k.id = c.category_id
           join users u on u.id = c.added_by
           left join lateral (select * from cause_validations v where v.cause_id = c.id
                              order by v.validated_at desc, v.id limit 1) lv on true
           left join users lvu on lvu.id = lv.validated_by left join users lr on lr.id = lv.responsible_user_id
           where c.case_id = %s order by k.display_order, c.created_at""", (case_id,)).fetchall()
    for r in rows:
        r["procedure_finding"] = causes_rules.procedure_finding(r["documented_answer"] or "unknown",
                                                                r["followed_process_answer"] or "unknown")
    return rows


def _load_cause(conn, p: Principal, cause_id: UUID) -> tuple[dict, dict]:
    cause = conn.execute("select * from ishikawa_causes where id = %s and organization_id = %s for update",
                         (cause_id, p.organization_id)).fetchone()
    if not cause:
        raise not_found("Causa")
    return cause, load_case(conn, p, cause["case_id"], for_update=True)


@router.get("/cases/{case_id}/causes")
def list_causes(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return _causes(conn, case_id)


@router.post("/cases/{case_id}/causes", status_code=201)
def add_cause(case_id: UUID, body: CauseIn, p: Principal = Depends(require("cause.edit")),
              conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D4", "La investigación de causas")
    text = (body.potential_cause or "").strip()
    category = body.category_id
    if body.source_idea_id:
        idea = conn.execute("""select * from cause_ideas where id = %s and is_active
                               and (organization_id is null or organization_id = %s)""",
                            (body.source_idea_id, p.organization_id)).fetchone()
        if not idea:
            raise invalid("La idea de la biblioteca no existe o no está activa.")
        text = text or idea["title_es"]  # copia: el caso no cambia si el catálogo cambia
        category = idea["category_id"]
    if not text:
        raise invalid("Describe la causa potencial.")
    if body.parent_cause_id and not conn.execute("select 1 from ishikawa_causes where id = %s and case_id = %s",
                                                 (body.parent_cause_id, case_id)).fetchone():
        raise invalid("La causa padre no pertenece al caso.")
    if conn.execute("select 1 from ishikawa_causes where case_id = %s and category_id = %s and lower(potential_cause) = lower(%s)",
                    (case_id, category, text)).fetchone():
        raise ApiError(409, "duplicate", "Esa causa ya está en el Ishikawa de este caso.")
    row = conn.execute(
        """insert into ishikawa_causes (organization_id, case_id, category_id, parent_cause_id, source_idea_id,
                                        potential_cause, notes, added_by) values (%s, %s, %s, %s, %s, %s, %s, %s)
           returning id""",
        (p.organization_id, case_id, category, body.parent_cause_id, body.source_idea_id, text, body.notes,
         p.user_id)).fetchone()
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = 'D4' and status = 'not_started'""", (case_id,))
    touch(conn, case_id)
    audit.record(conn, p, "cause.added", "ishikawa_cause", row["id"], case_id,
                 new={"potential_cause": text, "category_id": category, "source_idea_id": body.source_idea_id})
    refresh_case_status(conn, case_id)
    return _causes(conn, case_id)


@router.patch("/causes/{cause_id}")
def update_cause(cause_id: UUID, body: CausePatch, p: Principal = Depends(require("cause.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    cause, case = _load_cause(conn, p, cause_id)
    ensure_section_editable(conn, case, "D4", "La investigación de causas")
    if cause["investigation_status"] in DECIDED:
        raise ApiError(409, "cause_decided", "La causa ya tiene una decisión; registra una nueva validación para cambiarla.")
    old, new = audit.diff(cause, body.model_dump(exclude_unset=True))
    if new:
        conn.execute(f"update ishikawa_causes set {', '.join(f'{k} = %s' for k in new)}, updated_at = now() where id = %s",
                     [*new.values(), cause_id])
        audit.record(conn, p, "cause.updated", "ishikawa_cause", cause_id, case["id"], old=old, new=new)
    return _causes(conn, case["id"])


@router.delete("/causes/{cause_id}")
def delete_cause(cause_id: UUID, p: Principal = Depends(require("cause.edit")),
                 conn: psycopg.Connection = Depends(get_conn)):
    cause, case = _load_cause(conn, p, cause_id)
    ensure_section_editable(conn, case, "D4", "La investigación de causas")
    if conn.execute("select 1 from cause_validations where cause_id = %s", (cause_id,)).fetchone():
        raise ApiError(409, "has_history", "La causa tiene historial de validación; descártala con evidencia en lugar de borrarla.")
    if conn.execute("select 1 from ishikawa_causes where parent_cause_id = %s", (cause_id,)).fetchone():
        raise ApiError(409, "has_children", "La causa tiene subcausas.")
    conn.execute("delete from ishikawa_causes where id = %s", (cause_id,))
    audit.record(conn, p, "cause.deleted", "ishikawa_cause", cause_id, case["id"],
                 old={"potential_cause": cause["potential_cause"]})
    refresh_case_status(conn, case["id"])
    return _causes(conn, case["id"])


@router.get("/causes/{cause_id}/validations")
def validations(cause_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    cause = conn.execute("select case_id from ishikawa_causes where id = %s and organization_id = %s",
                         (cause_id, p.organization_id)).fetchone()
    if not cause:
        raise not_found("Causa")
    load_case(conn, p, cause["case_id"])
    return conn.execute(
        """select v.*, u.display_name as validated_by_name, r.display_name as responsible_name
           from cause_validations v join users u on u.id = v.validated_by left join users r on r.id = v.responsible_user_id
           where v.cause_id = %s order by v.validated_at desc""", (cause_id,)).fetchall()


@router.post("/causes/{cause_id}/validations", status_code=201)
def validate(cause_id: UUID, body: ValidationIn, p: Principal = Depends(require("cause.validate")),
             conn: psycopg.Connection = Depends(get_conn)):
    cause, case = _load_cause(conn, p, cause_id)
    ensure_section_editable(conn, case, "D4", "La investigación de causas")
    data = body.model_dump()
    for key in ("verification_method", "evidence_summary", "rationale"):
        data[key] = (data[key] or "").strip() or None
    if body.decision in DECIDED:
        # Sí/No nunca basta: una decisión exige método, evidencia y justificación.
        missing = [label for key, label in (("verification_method", "método de verificación"),
                                            ("evidence_summary", "evidencia"), ("rationale", "justificación"))
                   if not data[key]]
        if missing:
            raise ApiError(409, "evidence_required",
                           "Para decidir si es causa raíz faltan: " + ", ".join(missing) + ".", missing)
    same_org_user(conn, p, body.responsible_user_id)
    conn.execute(
        f"""insert into cause_validations (organization_id, cause_id, validated_by, {', '.join(data)})
            values (%s, %s, %s, {', '.join(['%s'] * len(data))})""",
        [p.organization_id, cause_id, p.user_id, *data.values()])
    touch(conn, case["id"])
    audit.record(conn, p, "cause.validated", "ishikawa_cause", cause_id, case["id"],
                 old={"investigation_status": cause["investigation_status"]}, new=data)
    refresh_case_status(conn, case["id"])
    return _causes(conn, case["id"])
