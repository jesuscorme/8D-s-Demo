"""Usuarios, plantas, tablero de inicio y administración de usuarios."""
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import audit, storage
from app.auth import Principal, get_conn, require
from app.errors import ApiError, invalid, not_found
from app.permissions import ROLE_NAMES
from app.security import hash_password

router = APIRouter(tags=["core"])
MAX_LOGO = 1024 * 1024


@router.get("/users")
def users(p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    return conn.execute(
        """select id, display_name, email from users where organization_id = %s and is_active
           order by display_name""", (p.organization_id,)).fetchall()


@router.get("/plants")
def plants(p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    rows = conn.execute("select id, code, name from plants where organization_id = %s and is_active order by code",
                        (p.organization_id,)).fetchall()
    return [r for r in rows if p.sees_plant(r["id"])]


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    plant_filter = "" if p.plant_ids is None else " and c.plant_id = any(%(plants)s)"
    args = {"org": p.organization_id, "plants": list(p.plant_ids or []), "me": p.user_id}
    by_status = conn.execute(f"""select status, count(*)::int as n from cases_8d c
                                 where organization_id = %(org)s{plant_filter} group by status""", args).fetchall()
    overdue = conn.execute(f"""select count(*)::int as n from containment_actions a join cases_8d c on c.id = a.case_id
                               where a.organization_id = %(org)s and a.status not in ('verified','cancelled')
                                 and a.due_date < current_date{plant_filter}""", args).fetchone()["n"]
    pending_review = conn.execute(f"""select count(*)::int as n from case_disciplines d join cases_8d c on c.id = d.case_id
                                      where d.organization_id = %(org)s and d.status = 'pending_review'{plant_filter}""",
                                  args).fetchone()["n"]
    mine = conn.execute(f"""select c.id, c.folio, c.title, c.status, c.severity, c.updated_at from cases_8d c
                            where c.organization_id = %(org)s and c.status not in ('closed','cancelled')
                              and (c.owner_user_id = %(me)s or exists (select 1 from case_team t
                                   where t.case_id = c.id and t.user_id = %(me)s)){plant_filter}
                            order by c.updated_at desc limit 8""", args).fetchall()
    alerts = conn.execute(f"""select count(*)::int as n from quality_alerts a join cases_8d c on c.id = a.case_id
                              where a.organization_id = %(org)s and a.status = 'issued'{plant_filter}""",
                          args).fetchone()["n"]
    attention = conn.execute(f"""select
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where a.organization_id = %(org)s
           and a.status in ('open','in_progress') and a.due_date < current_date{plant_filter})::int as actions_overdue,
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where a.organization_id = %(org)s
           and a.status = 'pending_approval'{plant_filter})::int as actions_pending_approval,
        (select count(*) from corrective_actions a join cases_8d c on c.id = a.case_id where a.organization_id = %(org)s
           and a.status = 'ineffective'{plant_filter})::int as actions_ineffective,
        (select count(*) from effectiveness_criteria a join cases_8d c on c.id = a.case_id where a.organization_id = %(org)s
           and a.status = 'draft'{plant_filter})::int as criteria_pending,
        (select count(*) from lessons_learned a join cases_8d c on c.id = a.source_case_id where a.organization_id = %(org)s
           and a.status in ('in_review','approved'){plant_filter})::int as lessons_pending,
        (select count(*) from cases_8d c where c.organization_id = %(org)s and c.status not in ('closed','cancelled')
           and c.target_close_date < current_date{plant_filter})::int as cases_overdue""", args).fetchone()
    attention_items = conn.execute(f"""
        select 'action' as kind, a.id, c.id as case_id, c.folio, a.description as title, a.status, a.due_date,
               (a.due_date < current_date) as overdue
        from corrective_actions a join cases_8d c on c.id = a.case_id
        where a.organization_id = %(org)s and ((a.status in ('open','in_progress') and a.due_date < current_date)
              or a.status in ('pending_approval','ineffective')){plant_filter}
        union all
        select 'containment', a.id, c.id, c.folio, a.description, a.status, a.due_date, true
        from containment_actions a join cases_8d c on c.id = a.case_id
        where a.organization_id = %(org)s and a.status not in ('verified','cancelled') and a.due_date < current_date{plant_filter}
        order by 7 nulls last limit 12""", args).fetchall()
    return {"by_status": {r["status"]: r["n"] for r in by_status}, "overdue_containment": overdue,
            "pending_review": pending_review, "issued_alerts": alerts, "my_cases": mine,
            "attention": attention, "attention_items": attention_items}


# ---- Administración -------------------------------------------------------------------------

class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)
    roles: list[str] = Field(min_length=1)
    # Vacío o ausente = todas las plantas de la organización.
    plant_ids: list[UUID] | None = None


class UserPatch(BaseModel):
    is_active: bool | None = None
    roles: list[str] | None = None
    plant_ids: list[UUID] | None = None
    password: str | None = Field(None, min_length=10, max_length=200)


class PlantIn(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    timezone: str = Field("America/Mexico_City", max_length=60)


def _roles(conn, org: UUID, codes: list[str]) -> list[dict]:
    unknown = set(codes) - set(ROLE_NAMES)
    if unknown:
        raise invalid(f"Roles desconocidos: {', '.join(sorted(unknown))}")
    return conn.execute("select id, code from roles where organization_id = %s and code = any(%s)",
                        (org, codes)).fetchall()


def _plants(conn, org: UUID, plant_ids: list[UUID] | None) -> list[UUID | None]:
    if not plant_ids:
        return [None]
    found = {r["id"] for r in conn.execute("select id from plants where organization_id = %s and id = any(%s)",
                                           (org, list(set(plant_ids)))).fetchall()}
    if found != set(plant_ids):
        raise invalid("Alguna planta no existe en tu organización.")
    return sorted(found, key=str)


def _grant(conn, org: UUID, user_id: UUID, roles: list[dict], plants: list[UUID | None]) -> None:
    for r in roles:
        for plant in plants:
            conn.execute("insert into user_roles (organization_id, user_id, role_id, plant_id) values (%s, %s, %s, %s)",
                         (org, user_id, r["id"], plant))


def _grants(conn, user_id: UUID) -> dict:
    rows = conn.execute("""select r.code, pl.code as plant from user_roles ur join roles r on r.id = ur.role_id
                           left join plants pl on pl.id = ur.plant_id where ur.user_id = %s""", (user_id,)).fetchall()
    return {"roles": sorted({r["code"] for r in rows}), "plants": sorted({r["plant"] for r in rows if r["plant"]})}


@router.get("/admin/users")
def admin_users(p: Principal = Depends(require("admin.users")), conn: psycopg.Connection = Depends(get_conn)):
    return conn.execute(
        """select u.id, u.email, u.display_name, u.is_active, u.created_at,
                  coalesce(array_agg(distinct r.code) filter (where r.code is not null), '{}') as roles,
                  coalesce(array_agg(distinct ur.plant_id) filter (where ur.plant_id is not null), '{}') as plant_ids
           from users u left join user_roles ur on ur.user_id = u.id left join roles r on r.id = ur.role_id
           where u.organization_id = %s group by u.id order by u.display_name""", (p.organization_id,)).fetchall()


@router.post("/admin/users", status_code=201)
def admin_create_user(body: UserIn, p: Principal = Depends(require("admin.users")),
                      conn: psycopg.Connection = Depends(get_conn)):
    roles = _roles(conn, p.organization_id, body.roles)
    plants = _plants(conn, p.organization_id, body.plant_ids)
    user = conn.execute(
        """insert into users (organization_id, email, display_name, password_hash) values (%s, %s, %s, %s)
           returning id, email, display_name, is_active""",
        (p.organization_id, body.email.strip().lower(), body.display_name.strip(), hash_password(body.password))
    ).fetchone()
    _grant(conn, p.organization_id, user["id"], roles, plants)
    audit.record(conn, p, "user.created", "user", user["id"], new={"email": user["email"], **_grants(conn, user["id"])})
    return {**user, "roles": sorted(body.roles)}


@router.post("/admin/plants", status_code=201)
def admin_create_plant(body: PlantIn, p: Principal = Depends(require("admin.users")),
                       conn: psycopg.Connection = Depends(get_conn)):
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise invalid("Zona horaria no válida (usa el formato IANA, p. ej. America/Mexico_City).") from None
    row = conn.execute("insert into plants (organization_id, code, name, timezone) values (%s, %s, %s, %s) returning id, code, name",
                       (p.organization_id, body.code, body.name.strip(), body.timezone)).fetchone()
    audit.record(conn, p, "plant.created", "plant", row["id"], new=body.model_dump())
    return row


@router.post("/admin/organization/logo")
async def upload_logo(file: UploadFile = File(...), p: Principal = Depends(require("admin.users")),
                      conn: psycopg.Connection = Depends(get_conn)):
    content = await file.read(MAX_LOGO + 1)
    if len(content) > MAX_LOGO:
        raise invalid("El logo no debe superar 1 MB.")
    mime = storage.sniff(content)
    if mime not in ("image/png", "image/jpeg"):
        raise invalid("El logo debe ser PNG o JPEG.")
    key, digest = storage.save(p.organization_id, content, mime)
    old = conn.execute("select logo_sha256 from organizations where id = %s", (p.organization_id,)).fetchone()
    conn.execute("update organizations set logo_storage_key = %s, logo_mime = %s, logo_sha256 = %s, updated_at = now() where id = %s",
                 (key, mime, digest, p.organization_id))
    audit.record(conn, p, "organization.logo_changed", "organization", p.organization_id,
                 old={"sha256": old["logo_sha256"]}, new={"sha256": digest})
    return {"sha256": digest}


@router.get("/organization/logo")
def get_logo(p: Principal = Depends(require("case.read")), conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("select logo_storage_key, logo_mime from organizations where id = %s", (p.organization_id,)).fetchone()
    if not row["logo_storage_key"]:
        raise not_found("Logo")
    return Response(storage.read(row["logo_storage_key"]), media_type=row["logo_mime"],
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.patch("/admin/users/{user_id}")
def admin_update_user(user_id: UUID, body: UserPatch, p: Principal = Depends(require("admin.users")),
                      conn: psycopg.Connection = Depends(get_conn)):
    user = conn.execute("select id, is_active from users where id = %s and organization_id = %s",
                        (user_id, p.organization_id)).fetchone()
    if not user:
        raise not_found("Usuario")
    if user_id == p.user_id and body.password is not None:
        raise ApiError(409, "use_own_password", "Para tu propia contraseña usa «Cambiar contraseña».")
    if user_id == p.user_id and (body.is_active is False or (body.roles is not None and "admin" not in body.roles)):
        raise ApiError(409, "self_lockout", "No puedes desactivarte ni quitarte el rol de administrador.")
    if body.is_active is not None and body.is_active != user["is_active"]:
        conn.execute("update users set is_active = %s where id = %s", (body.is_active, user_id))
        if not body.is_active:
            conn.execute("update sessions set revoked_at = now() where user_id = %s and revoked_at is null", (user_id,))
        audit.record(conn, p, "user.updated", "user", user_id, old={"is_active": user["is_active"]},
                     new={"is_active": body.is_active})
    if body.roles is not None or body.plant_ids is not None:
        old = _grants(conn, user_id)
        roles = _roles(conn, p.organization_id, body.roles if body.roles is not None else old["roles"])
        if body.plant_ids is not None:
            plants = _plants(conn, p.organization_id, body.plant_ids)
        else:
            plants = [None] if not old["plants"] else [r["plant_id"] for r in conn.execute(
                "select distinct plant_id from user_roles where user_id = %s and plant_id is not null", (user_id,)).fetchall()]
        if user_id == p.user_id and plants != [None]:
            raise ApiError(409, "self_lockout", "No puedes limitar tus propias plantas.")
        conn.execute("delete from user_roles where user_id = %s", (user_id,))
        _grant(conn, p.organization_id, user_id, roles, plants)
        conn.execute("update sessions set revoked_at = now() where user_id = %s and revoked_at is null and %s",
                     (user_id, user_id != p.user_id))
        audit.record(conn, p, "user.roles_changed", "user", user_id, old=old, new=_grants(conn, user_id))
    if body.password is not None:
        conn.execute("update users set password_hash = %s where id = %s", (hash_password(body.password), user_id))
        conn.execute("update sessions set revoked_at = now() where user_id = %s and revoked_at is null", (user_id,))
        audit.record(conn, p, "user.password_reset", "user", user_id)
    return {"ok": True}
