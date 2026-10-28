"""Concurrencia/doble envío, contraseñas, plantas y roles por planta, logo en documentos."""
import io
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from pypdf import PdfReader

from .conftest import PASSWORD, png


def ok(res, status=200):
    assert res.status_code == status, res.text
    return res.json() if res.content else None


def test_parallel_case_creation_gets_unique_consecutive_folios(login, plant):
    clients = [login("ing@t.local") for _ in range(4)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda i: clients[i % 4].post("/cases", json={"plant_id": str(plant), "title": f"Paralelo {i}"}),
                                range(8)))
    assert all(r.status_code == 201 for r in results)
    numbers = sorted(int(r.json()["folio"][-4:]) for r in results)
    assert numbers == list(range(numbers[0], numbers[0] + 8))


def test_double_submit_and_double_approve_are_rejected(login, plant):
    ing, ing2, mgr, mgr2 = login("ing@t.local"), login("ing2@t.local"), login("gerente@t.local"), login("admin@t.local")
    case = ok(ing.post("/cases", json={"plant_id": str(plant), "title": "Doble envío", "source_type": "internal"}), 201)
    ok(ing.patch(f"/cases/{case['id']}/disciplines/D0", json={"content": {"emergency_response": "x", "justification": "y"}}))
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda c: c.post(f"/cases/{case['id']}/disciplines/D0/submit").status_code, [ing, ing2]))
    assert codes == [200, 409]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(lambda c: c.post(f"/cases/{case['id']}/disciplines/D0/approve", json={}).status_code, [mgr, mgr2]))
    assert codes == [200, 409]
    events = [e["event_type"] for e in ok(ing.get(f"/cases/{case['id']}/audit"))]
    assert events.count("discipline.submitted") == 1 and events.count("discipline.approved") == 1


def test_change_own_password_revokes_other_sessions(app, login):
    a, b = login("lector@t.local"), login("lector@t.local")
    assert a.post("/auth/password", json={"current_password": "mala", "new_password": "Nueva-Contrasena-1"}).json()["code"] == "invalid_password"
    assert a.post("/auth/password", json={"current_password": PASSWORD, "new_password": "corta"}).status_code == 422
    assert a.post("/auth/password", json={"current_password": PASSWORD, "new_password": "Nueva-Contrasena-1"}).status_code == 204
    assert a.get("/auth/me").status_code == 200       # la sesión actual sigue
    assert b.get("/auth/me").status_code == 401       # las demás se cierran
    c = TestClient(app, headers={"x-d8-client": "web"})
    assert c.post("/auth/login", json={"email": "lector@t.local", "password": PASSWORD}).status_code == 401
    assert c.post("/auth/login", json={"email": "lector@t.local", "password": "Nueva-Contrasena-1"}).status_code == 200
    ok(a.post("/auth/password", json={"current_password": "Nueva-Contrasena-1", "new_password": PASSWORD}), 204)


def test_admin_reset_password_and_plant_scoped_roles(login, sql, plant):
    admin = login("admin@t.local")
    plant2 = sql("select id from plants where code = 'P2'")[0]["id"]
    user = ok(admin.post("/admin/users", json={"email": "p2@t.local", "display_name": "Solo P2", "password": "Contrasena-Larga-2",
                                               "roles": ["engineer"], "plant_ids": [str(plant2)]}), 201)
    c = TestClient(admin.app, headers={"x-d8-client": "web"})
    ok(c.post("/auth/login", json={"email": "p2@t.local", "password": "Contrasena-Larga-2"}))
    assert [p["code"] for p in ok(c.get("/plants"))] == ["P2"]
    p1_case = ok(admin.post("/cases", json={"plant_id": str(plant), "title": "Solo P1"}), 201)
    assert c.get(f"/cases/{p1_case['id']}").status_code == 404
    assert c.post("/cases", json={"plant_id": str(plant), "title": "x"}).status_code == 422
    ok(c.post("/cases", json={"plant_id": str(plant2), "title": "En P2"}), 201)
    assert [x["title"] for x in ok(c.get("/cases"))] == ["En P2"]
    assert c.post("/exports/audit", json={}).status_code == 403
    # Ampliar a todas las plantas revoca sus sesiones; el restablecimiento de contraseña también.
    ok(admin.patch(f"/admin/users/{user['id']}", json={"plant_ids": []}))
    assert c.get("/auth/me").status_code == 401
    ok(admin.patch(f"/admin/users/{user['id']}", json={"password": "Restablecida-123"}))
    assert c.post("/auth/login", json={"email": "p2@t.local", "password": "Restablecida-123"}).status_code == 200
    assert len(ok(c.get("/plants"))) == 2
    me = ok(admin.get("/auth/me"))["user"]["id"]
    assert admin.patch(f"/admin/users/{me}", json={"password": "Otra-Contrasena-1"}).json()["code"] == "use_own_password"
    assert admin.patch(f"/admin/users/{me}", json={"plant_ids": [str(plant2)]}).json()["code"] == "self_lockout"


def test_create_plant_and_logo_in_documents(login, sql):
    admin, ing = login("admin@t.local"), login("ing@t.local")
    assert ing.post("/admin/plants", json={"code": "P9", "name": "x"}).status_code == 403
    assert admin.post("/admin/plants", json={"code": "P9", "name": "Planta 9", "timezone": "Marte/Base"}).status_code == 422
    new = ok(admin.post("/admin/plants", json={"code": "P9", "name": "Planta 9", "timezone": "America/Monterrey"}), 201)
    assert admin.post("/admin/plants", json={"code": "P9", "name": "Dup"}).status_code == 409
    assert ing.get("/organization/logo").status_code == 404
    assert admin.post("/admin/organization/logo", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 422
    ok(admin.post("/admin/organization/logo", files={"file": ("logo.png", png((20, 60, 200)), "image/png")}))
    assert ing.get("/organization/logo").headers["content-type"] == "image/png"
    case = ok(ing.post("/cases", json={"plant_id": new["id"], "title": "Con logo"}), 201)
    doc = ok(ing.post(f"/cases/{case['id']}/documents/8d_progress"), 201)
    pdf = PdfReader(io.BytesIO(ing.get(f"/documents/{doc['id']}/content").content))
    assert len(pdf.pages[0].images) >= 1  # el logo se dibuja en el encabezado
    sql("update organizations set logo_storage_key = null, logo_mime = null, logo_sha256 = null where code = 'TEST'")
