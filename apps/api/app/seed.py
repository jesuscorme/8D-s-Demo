"""Seed de identidad para la demo: una organización, dos plantas, roles y usuarios.

No crea casos: los expedientes se capturan en vivo por el flujo normal.
La contraseña de los usuarios demo sale de DEMO_PASSWORD (.env); nunca está en el código.
Uso (en apps/api): .venv/Scripts/python -m app.seed
"""
import sys

import psycopg
from psycopg.rows import dict_row

from app.db import database_url, setting
from app.permissions import ROLE_NAMES
from app.security import hash_password

DEMO_USERS = [
    ("admin@demo.local", "Administración Demo", ["admin"]),
    ("calidad@demo.local", "Gerencia de Calidad Demo", ["quality_manager"]),
    ("ingenieria@demo.local", "Ingeniería de Calidad Demo", ["engineer"]),
    ("produccion@demo.local", "Supervisión de Producción Demo", ["engineer"]),
    ("mantenimiento@demo.local", "Mantenimiento Demo", ["engineer"]),
    ("consulta@demo.local", "Consulta Demo", ["viewer"]),
]


def ensure_organization(conn: psycopg.Connection, code: str, name: str, plants: list[tuple[str, str]],
                        users: list[tuple[str, str, list[str]]], password: str) -> dict:
    org = conn.execute("select id from organizations where code = %s", (code,)).fetchone()
    if not org:
        org = conn.execute("insert into organizations (code, name) values (%s, %s) returning id", (code, name)).fetchone()
    org_id = org["id"]
    for plant_code, plant_name in plants:
        conn.execute("""insert into plants (organization_id, code, name) values (%s, %s, %s)
                        on conflict (organization_id, code) do nothing""", (org_id, plant_code, plant_name))
    for role, role_name in ROLE_NAMES.items():
        conn.execute("""insert into roles (organization_id, code, name) values (%s, %s, %s)
                        on conflict (organization_id, code) do nothing""", (org_id, role, role_name))
    hashed = hash_password(password)
    ids = {}
    for email, display, roles in users:
        user = conn.execute("select id from users where email = %s", (email,)).fetchone()
        if not user:
            user = conn.execute("""insert into users (organization_id, email, display_name, password_hash)
                                   values (%s, %s, %s, %s) returning id""", (org_id, email, display, hashed)).fetchone()
            for role in roles:
                conn.execute("""insert into user_roles (organization_id, user_id, role_id)
                                select %s, %s, id from roles where organization_id = %s and code = %s""",
                             (org_id, user["id"], org_id, role))
        ids[email] = user["id"]
    return {"organization_id": org_id, "users": ids}


def main() -> int:
    password = setting("DEMO_PASSWORD")
    if not password or len(password) < 10:
        print("Falta DEMO_PASSWORD (mínimo 10 caracteres) en .env", file=sys.stderr)
        return 1
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        result = ensure_organization(conn, "DEMO", "Organización Demo 8D", [("PLT1", "Planta Uno"), ("PLT2", "Planta Dos")],
                                     DEMO_USERS, password)
    print(f"Seed listo: {len(result['users'])} usuarios demo (contraseña: DEMO_PASSWORD de .env).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
