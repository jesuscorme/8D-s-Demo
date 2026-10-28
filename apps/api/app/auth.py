"""Sesión, principal autenticado y dependencias de autorización."""
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID

import psycopg
from fastapi import Depends, Request

from app.errors import ApiError, forbidden
from app.permissions import permissions_for
from app.security import token_sha256

SESSION_COOKIE = "d8_session"
SESSION_HOURS = 12


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.db.transaction() as conn:
        yield conn


@dataclass
class Principal:
    user_id: UUID
    organization_id: UUID
    email: str
    display_name: str
    organization_name: str
    roles: set[str]
    permissions: set[str]
    # None = todas las plantas de la organización.
    plant_ids: set[UUID] | None
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    extra: dict = field(default_factory=dict)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def check(self, permission: str) -> None:
        if not self.can(permission):
            raise forbidden()

    def sees_plant(self, plant_id: UUID) -> bool:
        return self.plant_ids is None or plant_id in self.plant_ids


def load_principal(conn: psycopg.Connection, token: str | None) -> Principal | None:
    if not token:
        return None
    row = conn.execute(
        """select u.id, u.organization_id, u.email, u.display_name, o.name as organization_name
           from sessions s
           join users u on u.id = s.user_id and u.organization_id = s.organization_id
           join organizations o on o.id = u.organization_id
           where s.token_sha256 = %s and s.revoked_at is null and s.expires_at > now()
             and u.is_active and o.is_active""",
        (token_sha256(token),)).fetchone()
    if not row:
        return None
    grants = conn.execute(
        """select r.code, ur.plant_id from user_roles ur join roles r on r.id = ur.role_id
           where ur.user_id = %s and ur.organization_id = %s""",
        (row["id"], row["organization_id"])).fetchall()
    roles = {g["code"] for g in grants}
    plants = None if any(g["plant_id"] is None for g in grants) else {g["plant_id"] for g in grants}
    return Principal(user_id=row["id"], organization_id=row["organization_id"], email=row["email"],
                     display_name=row["display_name"], organization_name=row["organization_name"],
                     roles=roles, permissions=permissions_for(roles), plant_ids=plants)


def current(request: Request, conn: psycopg.Connection = Depends(get_conn)) -> Principal:
    principal = load_principal(conn, request.cookies.get(SESSION_COOKIE))
    if principal is None:
        raise ApiError(401, "unauthenticated", "Inicia sesión para continuar.")
    principal.request_id = getattr(request.state, "request_id", None)
    principal.ip = request.headers.get("x-forwarded-for", request.client.host if request.client else None)
    principal.user_agent = (request.headers.get("user-agent") or "")[:300]
    return principal


def require(permission: str):
    def dependency(request: Request, principal: Principal = Depends(current)) -> Principal:
        if not principal.can(permission):
            from app.audit import security_event  # import diferido: audit importa este módulo
            security_event(request.app.state.db, principal.organization_id, principal.user_id, "security.forbidden",
                           principal.ip, principal.user_agent,
                           {"permission": permission, "method": request.method, "path": request.url.path},
                           principal.request_id)
            raise forbidden()
        return principal
    return dependency
