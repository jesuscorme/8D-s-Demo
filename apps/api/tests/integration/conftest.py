"""Pruebas de integración: BD temporal `<APP_DB_NAME>_test` creada desde cero con scripts/migrate.ps1.

Usa el rol de la aplicación (con CREATEDB), nunca el superusuario. Si PostgreSQL no está
configurado (scripts/setup-db.ps1 sin ejecutar) las pruebas se omiten y lo indican.
"""
import os
import subprocess

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.db import REPO_ROOT, read_dotenv
from app.main import create_app
from app.seed import ensure_organization

PASSWORD = "Prueba-Integracion-2026"
DEMO_USERS = [
    ("admin@t.local", "Admin", ["admin"]),
    ("gerente@t.local", "Gerente", ["quality_manager"]),
    ("ing@t.local", "Ingeniera", ["engineer"]),
    ("ing2@t.local", "Ingeniero Dos", ["engineer"]),
    ("lector@t.local", "Lector", ["viewer"]),
]


@pytest.fixture(scope="session")
def db_url(tmp_path_factory):
    env = read_dotenv()
    if not env.get("APP_DB_PASSWORD"):
        pytest.skip("Sin .env con APP_DB_*: ejecuta scripts/setup-db.ps1")
    name = f"{env['APP_DB_NAME']}_test"
    base = f"postgresql://{env['APP_DB_USER']}:{env['APP_DB_PASSWORD']}@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}"
    try:
        admin = psycopg.connect(f"{base}/postgres", autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL no accesible con el rol de la app ({exc.__class__.__name__}): ejecuta scripts/setup-db.ps1")
    with admin:
        admin.execute(f"drop database if exists {name} with (force)")
        admin.execute(f"create database {name} encoding 'UTF8'")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(REPO_ROOT / "scripts" / "migrate.ps1"), "-Database", name],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout[-800:] + out.stderr[-800:]
    url = f"{base}/{name}"
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    os.environ["EMAIL_TRANSPORT"] = "file"  # las pruebas nunca envían correos reales
    with psycopg.connect(url, row_factory=dict_row) as conn:
        org = ensure_organization(conn, "TEST", "Org Prueba", [("P1", "Planta 1"), ("P2", "Planta 2")], DEMO_USERS, PASSWORD)
        for event, email in (("containment_started", "logistica@t.local"), ("alert_issued", "difusion@t.local")):
            conn.execute("""insert into notification_recipients (organization_id, event, email) values (%s, %s, %s)
                            on conflict do nothing""", (org["organization_id"], event, email))
        ensure_organization(conn, "OTRA", "Otra Org", [("X1", "Planta X")], [("otra@x.local", "Ajena", ["admin"])],
                            PASSWORD)
    yield url
    with psycopg.connect(f"{base}/postgres", autocommit=True) as conn:
        conn.execute(f"drop database if exists {name} with (force)")


@pytest.fixture
def sql(db_url):
    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as conn:
        def run(query, *args):
            cur = conn.execute(query, args or None)
            return cur.fetchall() if cur.description else None
        yield run


@pytest.fixture
def app(db_url, sql):
    sql("delete from cases_8d")
    sql("delete from cause_ideas where organization_id is not null")
    application = create_app(db_url)
    with TestClient(application):
        yield application


@pytest.fixture
def login(app):
    clients = []

    def make(email: str) -> TestClient:
        client = TestClient(app, headers={"x-d8-client": "web"})
        res = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert res.status_code == 200, res.text
        clients.append(client)
        return client
    yield make
    for c in clients:
        c.close()


@pytest.fixture
def plant(sql):
    return sql("select p.id from plants p join organizations o on o.id = p.organization_id "
               "where o.code = 'TEST' and p.code = 'P1'")[0]["id"]


@pytest.fixture
def users(sql):
    return {r["email"]: r["id"] for r in sql("select email, id from users")}


def png(color=(200, 30, 30)) -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, format="PNG")
    return buf.getvalue()
