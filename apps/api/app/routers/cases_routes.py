"""Expedientes 8D: alta, consulta, edición, equipo, flujo D0-D8, comentarios y bitácora."""
from datetime import date
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from app import audit, workflow
from app.auth import Principal, get_conn, require
from app.cases import ensure_section_editable, load_case, refresh_case_status, rule, same_org_user, snapshot, touch
from app.errors import ApiError, invalid

router = APIRouter(tags=["cases"])

Severity = Literal["low", "medium", "high", "critical"]
Source = Literal["customer_complaint", "internal", "supplier", "audit", "other"]
Code = Literal["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]


class CaseFields(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    problem_description: str | None = Field(None, max_length=4000)
    severity: Severity | None = None
    source_type: Source | None = None
    customer_name: str | None = Field(None, max_length=200)
    product_name: str | None = Field(None, max_length=200)
    part_number: str | None = Field(None, max_length=100)
    process_name: str | None = Field(None, max_length=200)
    lot_number: str | None = Field(None, max_length=100)
    defect_date: date | None = None
    detected_quantity: int | None = Field(None, ge=0)
    affected_quantity: int | None = Field(None, ge=0)
    owner_user_id: UUID | None = None
    target_close_date: date | None = None

    @field_validator("defect_date")
    @classmethod
    def not_future(cls, value: date | None):
        if value and value > date.today():
            raise ValueError("La fecha de detección no puede ser futura.")
        return value


class CaseIn(CaseFields):
    plant_id: UUID
    title: str = Field(min_length=1, max_length=200)


class CasePatch(CaseFields):
    version: int = Field(ge=1)


class TeamMember(BaseModel):
    user_id: UUID
    team_role: Literal["leader", "champion", "member"] = "member"


class TeamIn(BaseModel):
    members: list[TeamMember] = Field(max_length=30)


class ContentIn(BaseModel):
    content: dict[str, str | list[str] | None]


class ReviewIn(BaseModel):
    comment: str | None = Field(None, max_length=2000)


class CancelIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    discipline_code: Code | None = None


def _next_number(conn: psycopg.Connection, org: UUID, scope: str) -> int:
    """Numeración transaccional: la fila del contador queda bloqueada hasta el commit."""
    return conn.execute(
        """insert into counters (organization_id, scope, last_value) values (%s, %s, 1)
           on conflict (organization_id, scope) do update set last_value = counters.last_value + 1
           returning last_value""", (org, scope)).fetchone()["last_value"]


def _detail(conn: psycopg.Connection, p: Principal, case_id: UUID) -> dict:
    case = load_case(conn, p, case_id)
    meta = conn.execute(
        """select pl.code as plant_code, pl.name as plant_name, o.display_name as owner_name,
                  b.display_name as opened_by_name
           from cases_8d c join plants pl on pl.id = c.plant_id
           left join users o on o.id = c.owner_user_id join users b on b.id = c.opened_by where c.id = %s""",
        (case_id,)).fetchone()
    team = conn.execute(
        """select t.user_id, t.team_role, u.display_name, u.email from case_team t join users u on u.id = t.user_id
           where t.case_id = %s order by (t.team_role = 'leader') desc, u.display_name""", (case_id,)).fetchall()
    disciplines = conn.execute(
        """select d.discipline_code, d.content, d.submitted_at, d.approved_at, d.review_comment,
                  s.display_name as submitted_by_name, a.display_name as approved_by_name
           from case_disciplines d left join users s on s.id = d.submitted_by left join users a on a.id = d.approved_by
           where d.case_id = %s""", (case_id,)).fetchall()
    snap = snapshot(conn, case)
    info = {d["discipline_code"]: d for d in disciplines}
    flow = [{**item, **{k: v for k, v in info.get(item["code"], {}).items() if k != "discipline_code"}}
            for item in workflow.evaluate(snap)]
    return {**case, **meta, "team": team, "workflow": flow, "locked_fields": sorted(workflow.locked_fields(snap)),
            "content_fields": {k: sorted(v) for k, v in workflow.CONTENT_FIELDS.items()}}


@router.get("/cases")
def list_cases(q: str | None = Query(None, max_length=100), status: str | None = None, severity: str | None = None,
               plant_id: UUID | None = None, mine: bool = False,
               p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    where = ["c.organization_id = %(org)s"]
    args: dict = {"org": p.organization_id}
    if p.plant_ids is not None:
        where.append("c.plant_id = any(%(plants)s)")
        args["plants"] = list(p.plant_ids)
    if q:
        where.append("""(c.folio ilike %(q)s or c.title ilike %(q)s or coalesce(c.part_number,'') ilike %(q)s
                         or coalesce(c.customer_name,'') ilike %(q)s or c.problem_description ilike %(q)s)""")
        args["q"] = f"%{q.strip()}%"
    if status:
        where.append("c.status = %(status)s")
        args["status"] = status
    if severity:
        where.append("c.severity = %(severity)s")
        args["severity"] = severity
    if plant_id:
        where.append("c.plant_id = %(plant)s")
        args["plant"] = plant_id
    if mine:
        where.append("(c.owner_user_id = %(me)s or exists (select 1 from case_team t where t.case_id = c.id and t.user_id = %(me)s))")
        args["me"] = p.user_id
    return conn.execute(
        f"""select c.id, c.folio, c.title, c.status, c.severity, c.part_number, c.customer_name, c.defect_date,
                   c.is_demo, c.updated_at, pl.code as plant_code, u.display_name as owner_name,
                   (select min(d.discipline_code) from case_disciplines d
                     where d.case_id = c.id and d.status <> 'approved') as current_discipline
            from cases_8d c join plants pl on pl.id = c.plant_id left join users u on u.id = c.owner_user_id
            where {' and '.join(where)} order by c.updated_at desc limit 200""", args).fetchall()


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, p: Principal = Depends(require("case.create")),
                conn: psycopg.Connection = Depends(get_conn)):
    plant = conn.execute("select id, code from plants where id = %s and organization_id = %s and is_active",
                         (body.plant_id, p.organization_id)).fetchone()
    if not plant or not p.sees_plant(plant["id"]):
        raise invalid("Planta no válida.")
    owner = body.owner_user_id or p.user_id
    same_org_user(conn, p, owner)
    number = _next_number(conn, p.organization_id, f"case:{plant['id']}")
    folio = f"8D-{plant['code']}-{date.today().year}-{number:04d}"
    fields = body.model_dump(exclude={"plant_id", "owner_user_id"}, exclude_none=True)
    columns = ["organization_id", "plant_id", "case_number", "folio", "opened_by", "owner_user_id", *fields]
    values = [p.organization_id, plant["id"], number, folio, p.user_id, owner, *fields.values()]
    case = conn.execute(
        f"insert into cases_8d ({', '.join(columns)}) values ({', '.join(['%s'] * len(values))}) returning *",
        values).fetchone()
    for code in workflow.CODES:
        conn.execute("insert into case_disciplines (organization_id, case_id, discipline_code) values (%s, %s, %s)",
                     (p.organization_id, case["id"], code))
    conn.execute("insert into case_team (organization_id, case_id, user_id, team_role) values (%s, %s, %s, 'leader')",
                 (p.organization_id, case["id"], owner))
    audit.record(conn, p, "case.created", "case", case["id"], case["id"],
                 new={"folio": folio, **fields, "owner_user_id": owner})
    return _detail(conn, p, case["id"])


@router.get("/cases/{case_id}")
def get_case(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    return _detail(conn, p, case_id)


@router.patch("/cases/{case_id}")
def update_case(case_id: UUID, body: CasePatch, p: Principal = Depends(require("case.edit")),
                conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    snap = snapshot(conn, case)
    rule(workflow.check_case_open, snap)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    if "title" in changes and changes["title"] is None:
        raise invalid("El título es obligatorio.")
    if case["version"] != body.version:
        raise ApiError(409, "stale", "Otra persona modificó el caso. Recarga para ver los cambios.")
    old, new = audit.diff(case, changes)
    blocked = sorted(set(new) & workflow.locked_fields(snap))
    if blocked:
        raise ApiError(409, "fields_locked", "Hay campos congelados por una disciplina enviada o aprobada.", blocked)
    if "owner_user_id" in new:
        same_org_user(conn, p, new["owner_user_id"])
    if new:
        sets = ", ".join(f"{k} = %s" for k in new)
        conn.execute(f"update cases_8d set {sets}, updated_at = now(), version = version + 1 where id = %s",
                     [*new.values(), case_id])
        audit.record(conn, p, "case.updated", "case", case_id, case_id, old=old, new=new)
    return _detail(conn, p, case_id)


@router.post("/cases/{case_id}/cancel")
def cancel_case(case_id: UUID, body: CancelIn, p: Principal = Depends(require("case.cancel")),
                conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    rule(workflow.check_case_open, snapshot(conn, case))
    conn.execute("""update cases_8d set status = 'cancelled', cancel_reason = %s, closed_at = now(), updated_at = now(),
                    version = version + 1 where id = %s""", (body.reason.strip(), case_id))
    audit.record(conn, p, "case.cancelled", "case", case_id, case_id, old={"status": case["status"]},
                 new={"status": "cancelled", "cancel_reason": body.reason.strip()})
    return _detail(conn, p, case_id)


@router.put("/cases/{case_id}/team")
def set_team(case_id: UUID, body: TeamIn, p: Principal = Depends(require("case.edit")),
             conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    ensure_section_editable(conn, case, "D1", "El equipo")
    ids = [m.user_id for m in body.members]
    if len(set(ids)) != len(ids):
        raise invalid("Un usuario aparece más de una vez en el equipo.")
    if sum(1 for m in body.members if m.team_role == "leader") > 1:
        raise invalid("Solo puede haber un líder de equipo.")
    for uid in ids:
        same_org_user(conn, p, uid)
    old = conn.execute("select user_id, team_role from case_team where case_id = %s order by user_id",
                       (case_id,)).fetchall()
    conn.execute("delete from case_team where case_id = %s", (case_id,))
    for m in body.members:
        conn.execute("insert into case_team (organization_id, case_id, user_id, team_role) values (%s, %s, %s, %s)",
                     (p.organization_id, case_id, m.user_id, m.team_role))
    new = sorted(({"user_id": m.user_id, "team_role": m.team_role} for m in body.members), key=lambda x: str(x["user_id"]))
    _mark_in_progress(conn, case_id, "D1")
    touch(conn, case_id)
    audit.record(conn, p, "case.team_changed", "case", case_id, case_id, old={"team": old}, new={"team": new})
    refresh_case_status(conn, case_id)
    return _detail(conn, p, case_id)


def _mark_in_progress(conn: psycopg.Connection, case_id: UUID, code: str) -> None:
    conn.execute("""update case_disciplines set status = 'in_progress', updated_at = now()
                    where case_id = %s and discipline_code = %s and status = 'not_started'""", (case_id, code))


@router.patch("/cases/{case_id}/disciplines/{code}")
def update_discipline(case_id: UUID, code: Code, body: ContentIn, p: Principal = Depends(require("case.edit")),
                      conn: psycopg.Connection = Depends(get_conn)):
    case = load_case(conn, p, case_id, for_update=True)
    snap = snapshot(conn, case)
    rule(workflow.check_edit, code, snap)
    allowed = workflow.CONTENT_FIELDS[code]
    unknown = set(body.content) - allowed
    if unknown:
        raise invalid(f"Campos no válidos para {code}: {', '.join(sorted(unknown))}")
    for key, value in body.content.items():
        if isinstance(value, str) and len(value) > 4000:
            raise invalid(f"«{key}» supera 4000 caracteres.")
        if isinstance(value, list) and (key != "five_whys" or len(value) > 5 or any(len(v) > 500 for v in value)):
            raise invalid(f"«{key}» no admite esa lista.")
    old_content = snap.content.get(code, {})
    merged = {**old_content, **body.content}
    old, new = audit.diff(old_content, body.content)
    if new:
        conn.execute("""update case_disciplines set content = %s, updated_at = now(),
                        status = case when status = 'not_started' then 'in_progress' else status end
                        where case_id = %s and discipline_code = %s""", (Jsonb(merged), case_id, code))
        touch(conn, case_id)
        audit.record(conn, p, "discipline.updated", "discipline", None, case_id, old=old, new=new,
                     metadata={"discipline": code})
        refresh_case_status(conn, case_id)
    return _detail(conn, p, case_id)


def _transition(conn, p: Principal, case_id: UUID, code: str, check, new_status: str, event: str,
                comment: str | None = None, require_comment: bool = False) -> dict:
    case = load_case(conn, p, case_id, for_update=True)
    snap = snapshot(conn, case)
    rule(check, code, snap)
    if require_comment and not (comment and comment.strip()):
        raise invalid("Indica el motivo en el comentario.")
    extra = {
        "pending_review": "submitted_by = %(me)s, submitted_at = now(), review_comment = null",
        "approved": "approved_by = %(me)s, approved_at = now(), review_comment = %(comment)s",
        "in_progress": "approved_by = null, approved_at = null, review_comment = %(comment)s",
    }[new_status]
    conn.execute(f"""update case_disciplines set status = %(status)s, {extra}, updated_at = now()
                     where case_id = %(case)s and discipline_code = %(code)s""",
                 {"status": new_status, "me": p.user_id, "comment": comment, "case": case_id, "code": code})
    touch(conn, case_id)
    audit.record(conn, p, event, "discipline", None, case_id, old={"status": snap.status.get(code)},
                 new={"status": new_status}, metadata={"discipline": code, "comment": comment})
    refresh_case_status(conn, case_id)
    return _detail(conn, p, case_id)


@router.post("/cases/{case_id}/disciplines/{code}/submit")
def submit(case_id: UUID, code: Code, p: Principal = Depends(require("case.edit")),
           conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, case_id, code, workflow.check_submit, "pending_review", "discipline.submitted")


@router.post("/cases/{case_id}/disciplines/{code}/approve")
def approve(case_id: UUID, code: Code, body: ReviewIn, p: Principal = Depends(require("discipline.approve")),
            conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, case_id, code, workflow.check_approve, "approved", "discipline.approved", body.comment)


@router.post("/cases/{case_id}/disciplines/{code}/reject")
def reject(case_id: UUID, code: Code, body: ReviewIn, p: Principal = Depends(require("discipline.approve")),
           conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, case_id, code, workflow.check_review, "in_progress", "discipline.rejected",
                       body.comment, require_comment=True)


@router.post("/cases/{case_id}/disciplines/{code}/reopen")
def reopen(case_id: UUID, code: Code, body: ReviewIn, p: Principal = Depends(require("discipline.approve")),
           conn: psycopg.Connection = Depends(get_conn)):
    return _transition(conn, p, case_id, code, workflow.check_reopen, "in_progress", "discipline.reopened",
                       body.comment, require_comment=True)


@router.get("/cases/{case_id}/comments")
def comments(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return conn.execute(
        """select c.id, c.body, c.discipline_code, c.created_at, u.display_name as author_name
           from case_comments c join users u on u.id = c.author_user_id where c.case_id = %s order by c.created_at""",
        (case_id,)).fetchall()


@router.post("/cases/{case_id}/comments", status_code=201)
def add_comment(case_id: UUID, body: CommentIn, p: Principal = Depends(require("comment.create")),
                conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    row = conn.execute(
        """insert into case_comments (organization_id, case_id, discipline_code, body, author_user_id)
           values (%s, %s, %s, %s, %s) returning id, body, discipline_code, created_at""",
        (p.organization_id, case_id, body.discipline_code, body.body.strip(), p.user_id)).fetchone()
    audit.record(conn, p, "comment.created", "comment", row["id"], case_id,
                 metadata={"discipline": body.discipline_code})
    return {**row, "author_name": p.display_name}


@router.get("/cases/{case_id}/audit")
def case_audit(case_id: UUID, p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    load_case(conn, p, case_id)
    return conn.execute(
        """select e.id, e.event_type, e.entity_type, e.entity_id, e.occurred_at, e.old_values, e.new_values,
                  e.metadata, u.display_name as actor_name
           from audit_events e left join users u on u.id = e.actor_user_id
           where e.organization_id = %s and e.case_id = %s order by e.occurred_at desc, e.id desc limit 500""",
        (p.organization_id, case_id)).fetchall()


@router.get("/catalog/disciplines")
def disciplines(_: Principal = Depends(require("case.read"))):
    return [{"code": c, "name": n, "available": c not in workflow.PENDING_MODULE,
             "pending_module": workflow.PENDING_MODULE.get(c)} for c, n in workflow.DISCIPLINES]
