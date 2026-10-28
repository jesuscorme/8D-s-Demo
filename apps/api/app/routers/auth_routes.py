"""Inicio y cierre de sesión."""
from datetime import timedelta

import psycopg
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app import audit
from app.auth import SESSION_COOKIE, SESSION_HOURS, Principal, current, get_conn, load_principal
from app.db import setting
from app.errors import ApiError
from app.permissions import ROLE_NAMES
from app.security import hash_password, new_session_token, token_sha256, verify_password

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def me_payload(p: Principal) -> dict:
    return {
        "user": {"id": p.user_id, "email": p.email, "display_name": p.display_name},
        "organization": {"id": p.organization_id, "name": p.organization_name},
        "roles": sorted(p.roles), "role_names": [ROLE_NAMES[r] for r in sorted(p.roles)],
        "permissions": sorted(p.permissions),
    }


MAX_FAILURES, WINDOW_MINUTES = 5, 15


def _attempt(request: Request, email: str, success: bool) -> None:
    # Conexión propia: el intento fallido se registra aunque la petición termine en 401 (rollback).
    with request.app.state.db.pool.connection() as c:
        c.execute("insert into login_attempts (email, ip_address, success) values (%s, %s, %s)",
                  (email, audit._ip(request.client.host if request.client else None), success))


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, conn: psycopg.Connection = Depends(get_conn)):
    email = body.email.strip().lower()
    ip, agent = (request.client.host if request.client else None), request.headers.get("user-agent")
    failures = conn.execute(
        """select count(*)::int as n from login_attempts where email = %s and not success
             and attempted_at > now() - make_interval(mins => %s)
             and attempted_at > coalesce((select max(attempted_at) from login_attempts where email = %s and success),
                                         '-infinity')""",
        (email, WINDOW_MINUTES, email)).fetchone()["n"]
    user = conn.execute(
        """select u.id, u.organization_id, u.password_hash, u.is_active and o.is_active as active
           from users u join organizations o on o.id = u.organization_id where u.email = %s""",
        (email,)).fetchone()
    if failures >= MAX_FAILURES:
        if user:
            audit.security_event(request.app.state.db, user["organization_id"], user["id"], "auth.locked", ip, agent,
                                 {"email": email, "failures": failures})
        raise ApiError(429, "too_many_attempts",
                       f"Demasiados intentos fallidos. Espera {WINDOW_MINUTES} minutos o pide ayuda al administrador.")
    valid = verify_password(body.password, user["password_hash"] if user else None)
    if not user or not valid or not user["active"]:
        _attempt(request, email, False)
        if user:
            audit.security_event(request.app.state.db, user["organization_id"], user["id"], "auth.login_failed", ip,
                                 agent, {"email": email, "reason": "inactive" if valid else "bad_password"})
        raise ApiError(401, "invalid_credentials", "Correo o contraseña incorrectos.")
    _attempt(request, email, True)
    token, digest = new_session_token()
    conn.execute(
        "insert into sessions (token_sha256, organization_id, user_id, expires_at) values (%s, %s, %s, now() + %s)",
        (digest, user["organization_id"], user["id"], timedelta(hours=SESSION_HOURS)))
    principal = load_principal(conn, token)
    principal.ip = request.client.host if request.client else None
    principal.user_agent = (request.headers.get("user-agent") or "")[:300]
    audit.record(conn, principal, "auth.login", "user", principal.user_id)
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, samesite="lax",
                        secure=(setting("COOKIE_SECURE", "false") == "true"), path="/")
    return me_payload(principal)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, conn: psycopg.Connection = Depends(get_conn)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = conn.execute("""update sessions set revoked_at = now() where token_sha256 = %s and revoked_at is null
                              returning organization_id, user_id""", (token_sha256(token),)).fetchone()
        if row:
            conn.execute("""insert into audit_events (organization_id, actor_user_id, event_type, entity_type, entity_id)
                            values (%s, %s, 'auth.logout', 'user', %s)""",
                         (row["organization_id"], row["user_id"], row["user_id"]))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me")
def me(p: Principal = Depends(current)):
    return me_payload(p)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordIn, request: Request, p: Principal = Depends(current),
                    conn: psycopg.Connection = Depends(get_conn)):
    row = conn.execute("select password_hash from users where id = %s", (p.user_id,)).fetchone()
    if not verify_password(body.current_password, row["password_hash"]):
        audit.security_event(request.app.state.db, p.organization_id, p.user_id, "auth.password_change_failed",
                             p.ip, p.user_agent, {}, p.request_id)
        raise ApiError(409, "invalid_password", "La contraseña actual no es correcta.")
    if body.new_password == body.current_password:
        raise ApiError(422, "invalid", "La nueva contraseña debe ser distinta de la actual.")
    conn.execute("update users set password_hash = %s where id = %s", (hash_password(body.new_password), p.user_id))
    # Cierra las demás sesiones del usuario; la actual sigue activa.
    conn.execute("""update sessions set revoked_at = now() where user_id = %s and revoked_at is null
                    and token_sha256 <> %s""", (p.user_id, token_sha256(request.cookies.get(SESSION_COOKIE, ""))))
    audit.record(conn, p, "auth.password_changed", "user", p.user_id)
    return Response(status_code=204)
