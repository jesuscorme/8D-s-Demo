"""Autenticación, permisos en backend, aislamiento entre organizaciones y bitácora."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from .conftest import PASSWORD


def new_case(client, plant, **kw):
    res = client.post("/cases", json={"plant_id": str(plant), "title": "Rebaba en carcasa", **kw})
    assert res.status_code == 201, res.text
    return res.json()


def test_login_me_logout(app, sql):
    c = TestClient(app, headers={"x-d8-client": "web"})
    assert c.get("/auth/me").status_code == 401
    bad = c.post("/auth/login", json={"email": "ing@t.local", "password": "incorrecta"})
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_credentials"
    assert c.post("/auth/login", json={"email": "nadie@t.local", "password": "x"}).status_code == 401
    ok = c.post("/auth/login", json={"email": "ING@t.local", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["roles"] == ["engineer"]
    assert "d8_session" in ok.headers["set-cookie"] and "HttpOnly" in ok.headers["set-cookie"]
    assert c.get("/auth/me").json()["user"]["email"] == "ing@t.local"
    # Solo se guarda el hash del token.
    token = c.cookies.get("d8_session")
    assert not sql("select 1 from sessions where token_sha256 = %s", token)
    assert c.post("/auth/logout").status_code == 204
    c.cookies.set("d8_session", token)
    assert c.get("/auth/me").status_code == 401  # sesión revocada en servidor


def test_csrf_header_required_for_mutations(app):
    c = TestClient(app)
    res = c.post("/auth/login", json={"email": "ing@t.local", "password": PASSWORD})
    assert res.status_code == 403 and res.json()["code"] == "csrf"


def test_role_permissions_enforced_in_backend(login, plant):
    viewer, engineer = login("lector@t.local"), login("ing@t.local")
    assert viewer.post("/cases", json={"plant_id": str(plant), "title": "x"}).status_code == 403
    case = new_case(engineer, plant)
    assert viewer.get(f"/cases/{case['id']}").status_code == 200
    assert viewer.patch(f"/cases/{case['id']}", json={"version": 1, "title": "y"}).status_code == 403
    assert engineer.post(f"/cases/{case['id']}/cancel", json={"reason": "no aplica"}).status_code == 403
    assert engineer.get("/admin/users").status_code == 403
    assert engineer.post("/cause-ideas", json={"category_id": case["id"], "title_es": "abc"}).status_code == 403


def test_organization_isolation(login, plant, sql):
    mine, other = login("ing@t.local"), login("otra@x.local")
    case = new_case(mine, plant)
    assert other.get(f"/cases/{case['id']}").status_code == 404
    assert other.get(f"/cases/{case['id']}/audit").status_code == 404
    assert other.patch(f"/cases/{case['id']}", json={"version": 1, "title": "hack"}).status_code == 404
    assert other.get("/cases").json() == []
    assert all(u["email"].endswith("x.local") for u in other.get("/users").json())
    # No se puede asignar como responsable a un usuario de otra organización.
    foreign = sql("select id from users where email = 'otra@x.local'")[0]["id"]
    res = mine.patch(f"/cases/{case['id']}", json={"version": case["version"], "owner_user_id": str(foreign)})
    assert res.status_code == 422 and res.json()["code"] == "invalid_user"
    # Tampoco crear un caso en una planta ajena.
    other_plant = sql("select id from plants where code = 'X1'")[0]["id"]
    assert mine.post("/cases", json={"plant_id": str(other_plant), "title": "x"}).status_code == 422


def test_folio_sequence_and_optimistic_concurrency(login, plant):
    c = login("ing@t.local")
    a, b = new_case(c, plant), new_case(c, plant)
    assert a["folio"].startswith("8D-P1-") and int(b["folio"][-4:]) == int(a["folio"][-4:]) + 1
    first = c.patch(f"/cases/{a['id']}", json={"version": a["version"], "part_number": "123-A"})
    assert first.status_code == 200 and first.json()["version"] == a["version"] + 1
    stale = c.patch(f"/cases/{a['id']}", json={"version": a["version"], "part_number": "999"})
    assert stale.status_code == 409 and stale.json()["code"] == "stale"


def test_search_and_filters(login, plant):
    c = login("ing@t.local")
    new_case(c, plant, part_number="ABC-1", severity="critical")
    new_case(c, plant, title="Golpe en tapa", part_number="ZZZ-9")
    assert [x["part_number"] for x in c.get("/cases", params={"q": "abc"}).json()] == ["ABC-1"]
    assert len(c.get("/cases", params={"severity": "critical"}).json()) == 1
    assert len(c.get("/cases", params={"mine": True}).json()) == 2


def test_audit_trail_is_append_only(login, plant, sql):
    c = login("ing@t.local")
    case = new_case(c, plant)
    c.patch(f"/cases/{case['id']}", json={"version": case["version"], "severity": "high"})
    events = c.get(f"/cases/{case['id']}/audit").json()
    assert [e["event_type"] for e in events][:2] == ["case.updated", "case.created"]
    assert events[0]["old_values"] == {"severity": "medium"} and events[0]["new_values"] == {"severity": "high"}
    with pytest.raises(psycopg.errors.RaiseException):
        sql("update audit_events set event_type = 'x'")
    with pytest.raises(psycopg.errors.RaiseException):
        sql("delete from audit_events")


def test_admin_creates_user_and_deactivation_revokes_sessions(login):
    admin = login("admin@t.local")
    res = admin.post("/admin/users", json={"email": "nuevo@t.local", "display_name": "Nuevo",
                                          "password": "Contrasena-Larga-1", "roles": ["viewer"]})
    assert res.status_code == 201
    weak = admin.post("/admin/users", json={"email": "n2@t.local", "display_name": "N", "password": "corta",
                                           "roles": ["viewer"]})
    assert weak.status_code == 422
    dup = admin.post("/admin/users", json={"email": "nuevo@t.local", "display_name": "N",
                                          "password": "Contrasena-Larga-1", "roles": ["viewer"]})
    assert dup.status_code == 409
    me = admin.get("/auth/me").json()["user"]["id"]
    assert admin.patch(f"/admin/users/{me}", json={"is_active": False}).json()["code"] == "self_lockout"
