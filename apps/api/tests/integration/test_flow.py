"""Flujo D0-D4 completo: requisitos, aprobaciones, contención, alerta PDF versionada e Ishikawa."""
import hashlib
import io

import psycopg
import pytest
from pypdf import PdfReader

from .conftest import png


def flow(case: dict, code: str) -> dict:
    return next(d for d in case["workflow"] if d["code"] == code)


def ok(res, status=200):
    assert res.status_code == status, res.text
    return res.json()


@pytest.fixture
def actors(login):
    return {"ing": login("ing@t.local"), "mgr": login("gerente@t.local")}


def approve_blocked(actors, case_id, code) -> bool:
    res = actors["ing"].post(f"/cases/{case_id}/disciplines/{code}/submit")
    return res.status_code == 409 and res.json()["code"] == "requirements_pending"


def approve(actors, case_id, code):
    ok(actors["ing"].post(f"/cases/{case_id}/disciplines/{code}/submit"))
    return ok(actors["mgr"].post(f"/cases/{case_id}/disciplines/{code}/approve", json={"comment": "OK"}))


def test_full_d0_to_d4(actors, plant, users, sql):
    ing, mgr = actors["ing"], actors["mgr"]
    case = ok(ing.post("/cases", json={"plant_id": str(plant), "title": "Rebaba en carcasa 123",
                                       "process_name": "Maquinado CNC", "severity": "high"}), 201)
    cid = case["id"]
    assert case["status"] == "draft" and flow(case, "D0")["pending_count"] > 0

    # D0: requisitos pendientes bloquean el envío (backend).
    blocked = ing.post(f"/cases/{cid}/disciplines/D0/submit")
    assert blocked.status_code == 409 and blocked.json()["code"] == "requirements_pending"
    ok(ing.patch(f"/cases/{cid}", json={"version": case["version"], "source_type": "customer_complaint"}))
    case = ok(ing.patch(f"/cases/{cid}/disciplines/D0", json={"content": {
        "emergency_response": "Bloqueo de 3 lotes", "justification": "Reclamo de cliente"}}))
    assert case["status"] == "open"
    bad_field = ing.patch(f"/cases/{cid}/disciplines/D0", json={"content": {"inventado": "x"}})
    assert bad_field.status_code == 422
    ok(ing.post(f"/cases/{cid}/disciplines/D0/submit"))
    # El ingeniero no aprueba; el gerente sí.
    assert ing.post(f"/cases/{cid}/disciplines/D0/approve", json={}).status_code == 403
    case = ok(mgr.post(f"/cases/{cid}/disciplines/D0/approve", json={"comment": "Procede"}))
    assert flow(case, "D0")["status"] == "approved" and case["status"] == "in_progress"
    assert "severity" in case["locked_fields"]
    locked = ing.patch(f"/cases/{cid}", json={"version": case["version"], "severity": "low"})
    assert locked.status_code == 409 and locked.json()["code"] == "fields_locked"

    # D1: equipo de 3 con líder.
    team = [{"user_id": str(users["ing@t.local"]), "team_role": "leader"},
            {"user_id": str(users["ing2@t.local"]), "team_role": "member"},
            {"user_id": str(users["gerente@t.local"]), "team_role": "champion"}]
    two_leaders = [{**t, "team_role": "leader"} for t in team]
    assert ing.put(f"/cases/{cid}/team", json={"members": two_leaders}).status_code == 422
    ok(ing.put(f"/cases/{cid}/team", json={"members": team}))
    case = approve(actors, cid, "D1")
    assert ing.put(f"/cases/{cid}/team", json={"members": team[:1]}).json()["code"] == "discipline_locked"

    # D2: descripción del problema.
    ok(ing.patch(f"/cases/{cid}", json={"version": case["version"], "problem_description":
                                        "Rebaba de 0.5 mm en el borde exterior de la carcasa", "part_number": "123-A",
                                        "defect_date": "2026-10-20", "detected_quantity": 40, "affected_quantity": 1200,
                                        "customer_name": "Cliente A"}))
    ok(ing.patch(f"/cases/{cid}/disciplines/D2", json={"content": {
        "what": "Rebaba", "where": "Recepción del cliente", "when": "Turno 2", "how_detected": "Inspección visual"}}))
    case = approve(actors, cid, "D2")

    # D3: contención con evidencia + alerta emitida.
    actions = ok(ing.post(f"/cases/{cid}/containment", json={
        "description": "Inspección 100% del inventario", "responsible_user_id": str(users["ing2@t.local"]),
        "due_date": "2026-10-30", "quantity_checked": 1200, "quantity_rejected": 35}), 201)
    aid = actions[0]["id"]
    no_ev = ing.patch(f"/containment/{aid}", json={"status": "implemented"})
    assert no_ev.status_code == 409 and no_ev.json()["code"] == "evidence_required"
    jump = ing.patch(f"/containment/{aid}", json={"status": "verified", "evidence_notes": "x"})
    assert jump.status_code == 409 and jump.json()["code"] == "invalid_transition"
    ok(ing.patch(f"/containment/{aid}", json={"status": "implemented", "evidence_notes": "Registro de inspección R-12"}))
    ok(ing.patch(f"/containment/{aid}", json={"status": "verified"}))
    evidence = ok(ing.post(f"/cases/{cid}/attachments", data={"purpose": "evidence", "containment_id": aid},
                           files={"file": ("registro.pdf", b"%PDF-1.4 registro", "application/pdf")}), 201)
    assert evidence["containment_id"] == aid
    d3 = flow(ok(ing.get(f"/cases/{cid}")), "D3")["blockers"]
    assert "Alerta de calidad emitida" in d3 and "Contención iniciada (aviso a logística con la alerta)" in d3
    # Iniciar la contención exige la alerta emitida (va adjunta al aviso a logística).
    early = ing.post(f"/cases/{cid}/containment-record/start", json={})
    assert early.status_code == 409 and early.json()["code"] == "alert_required"

    alert = ok(ing.post(f"/cases/{cid}/alerts", json={"failure_type": "external"}), 201)
    assert alert["folio"].startswith("QA-") and alert["affected_quantity"] == 1200
    assert "Inspección 100%" in alert["containment_summary"]
    assert ing.post(f"/alerts/{alert['id']}/issue").status_code == 403  # emitir requiere gerente
    missing = mgr.post(f"/alerts/{alert['id']}/issue")
    assert missing.status_code == 409 and "¿Dónde?" in missing.json()["details"]
    ok(ing.patch(f"/alerts/{alert['id']}", json={"where_happened": "Planta cliente", "who_is_affected": "Cliente A",
                                                 "how_detected": "Inspección visual", "affected_areas": "Línea 3"}))
    nok = ok(ing.post(f"/cases/{cid}/attachments", data={"purpose": "photo"},
                      files={"file": ("nok.png", png(), "image/png")}), 201)
    good = ok(ing.post(f"/cases/{cid}/attachments", data={"purpose": "photo"},
                       files={"file": ("ok.png", png((30, 160, 60)), "image/png")}), 201)
    pdf_as_photo = ing.put(f"/alerts/{alert['id']}/photos",
                           json={"photos": [{"attachment_id": evidence["id"], "kind": "nok"}]})
    assert pdf_as_photo.status_code == 422
    ok(ing.put(f"/alerts/{alert['id']}/photos", json={"photos": [
        {"attachment_id": nok["id"], "kind": "nok"}, {"attachment_id": good["id"], "kind": "ok"}]}))
    rev1 = ok(mgr.post(f"/alerts/{alert['id']}/issue"))
    assert rev1["status"] == "issued" and rev1["revisions"][0]["document_id"]
    assert ing.patch(f"/alerts/{alert['id']}", json={"title": "cambio"}).json()["code"] == "alert_issued"
    with pytest.raises(psycopg.errors.RaiseException):
        sql("update quality_alerts set title = 'x' where id = %s", alert["id"])

    doc1 = ing.get(f"/documents/{rev1['revisions'][0]['document_id']}/content")
    assert doc1.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(doc1.content).hexdigest() == doc1.headers["x-content-sha256"]
    text = PdfReader(io.BytesIO(doc1.content)).pages[0].extract_text()
    assert "ALERTA DE CALIDAD" in text and case["folio"] in text and "Planta cliente" in text

    # Nueva revisión: la anterior queda sustituida y su PDF se conserva.
    rev2 = ok(ing.post(f"/alerts/{alert['id']}/revise", json={"reason": "Cantidad actualizada"}), 201)
    assert rev2["revision"] == 2 and rev2["status"] == "draft" and len(rev2["photos"]) == 2
    assert ing.post(f"/alerts/{alert['id']}/revise", json={"reason": "otra vez"}).json()["code"] == "draft_exists"
    ok(ing.patch(f"/alerts/{rev2['id']}", json={"affected_quantity": 1500}))
    rev2 = ok(mgr.post(f"/alerts/{rev2['id']}/issue"))
    statuses = {r["revision"]: r["status"] for r in rev2["revisions"]}
    assert statuses == {2: "issued", 1: "superseded"}
    docs = ok(ing.get(f"/cases/{cid}/documents"))
    assert sorted(d["status"] for d in docs) == ["issued", "superseded"]
    assert len({d["sha256_hex"] for d in docs}) == 2
    assert ing.get(f"/documents/{rev1['revisions'][0]['document_id']}/content").status_code == 200
    # Alerta emitida → correo al equipo y a la lista de difusión con el PDF (transporte «file» en pruebas).
    from app import storage
    issued_mails = sql("select * from email_outbox where case_id = %s and event = 'alert_issued' order by created_at", cid)
    assert len(issued_mails) == 2 and all(m["status"] == "sent" for m in issued_mails)
    assert "difusion@t.local" in issued_mails[0]["to_addresses"] and "ing@t.local" in issued_mails[0]["to_addresses"]
    eml = (storage.root() / "outbox" / f"{issued_mails[-1]['id']}.eml").read_bytes()
    assert b"application/pdf" in eml and b"QA-" in eml

    # Registro de contención: inicio (aviso a logística con la alerta vigente), lotes y fin con resultado.
    assert approve_blocked(actors, cid, "D3")
    rec = ok(ing.post(f"/cases/{cid}/containment-record/start", json={}))
    assert rec["record"]["started_at"] and rec["emails"][0]["event"] == "containment_started"
    assert ing.post(f"/cases/{cid}/containment-record/start", json={}).json()["code"] == "already_started"
    logistics = sql("select * from email_outbox where case_id = %s and event = 'containment_started'", cid)[0]
    assert logistics["status"] == "sent" and "logistica@t.local" in logistics["to_addresses"]
    assert "Detener material" in logistics["subject"] and logistics["attachments"][0]["file_name"].endswith("rev2.pdf")
    assert ing.post(f"/cases/{cid}/containment-record/end", json={"result": "effective", "result_notes": "Todo bien"}).json()["code"] == "lots_required"
    assert ing.post(f"/cases/{cid}/containment-lots", json={"lot_number": "L-1", "quantity_inspected": 5, "quantity_rejected": 9}).status_code == 422
    ok(ing.post(f"/cases/{cid}/containment-lots", json={"lot_number": "L-1", "location": "Almacén PT", "quantity_inspected": 800,
                                                       "quantity_rejected": 20, "disposition": "rework"}), 201)
    rec = ok(ing.post(f"/cases/{cid}/containment-lots", json={"lot_number": "L-2", "quantity_inspected": 400,
                                                             "quantity_rejected": 15, "disposition": "scrap"}), 201)
    assert rec["totals"] == {"lots": 2, "inspected": 1200, "rejected": 35, "ok": 1165}
    assert ing.post(f"/cases/{cid}/containment-lots", json={"lot_number": "L-2", "quantity_inspected": 1}).status_code == 409
    rec = ok(ing.post(f"/cases/{cid}/containment-record/end", json={"result": "effective",
                                                                   "result_notes": "Sin piezas NOK fuera de los lotes segregados"}))
    assert rec["record"]["result"] == "effective" and rec["record"]["ended_at"]
    assert ing.post(f"/cases/{cid}/containment-lots", json={"lot_number": "L-3", "quantity_inspected": 1}).json()["code"] == "already_ended"
    case = approve(actors, cid, "D3")
    assert ing.post(f"/cases/{cid}/containment", json={"description": "otra"}).json()["code"] == "discipline_locked"

    # D4: Ishikawa y validación con evidencia.
    cats = {c["code"]: c["id"] for c in ok(ing.get("/ishikawa/categories"))}
    assert list(cats) == ["METHOD", "MACHINE", "MATERIAL", "MANPOWER", "MEASUREMENT", "ENVIRONMENT"]
    sugg = ok(ing.get(f"/cases/{cid}/suggestions"))
    tool = next(s for s in sugg if s["title_es"] == "Desgaste de herramental")
    causes = ok(ing.post(f"/cases/{cid}/causes", json={"category_id": cats["MACHINE"], "source_idea_id": tool["id"]}), 201)
    assert causes[0]["potential_cause"] == "Desgaste de herramental" and causes[0]["investigation_status"] == "pending"
    assert tool["id"] not in [s["id"] for s in ok(ing.get(f"/cases/{cid}/suggestions"))]
    dup = ing.post(f"/cases/{cid}/causes", json={"category_id": cats["MACHINE"], "potential_cause": "desgaste de HERRAMENTAL"})
    assert dup.status_code == 409
    causes = ok(ing.post(f"/cases/{cid}/causes", json={"category_id": cats["MANPOWER"],
                                                       "potential_cause": "Operador sin certificación"}), 201)
    c_tool = next(c for c in causes if c["category_code"] == "MACHINE")
    c_op = next(c for c in causes if c["category_code"] == "MANPOWER")

    # Sí/No nunca basta para confirmar causa raíz.
    yes_no = ing.post(f"/causes/{c_tool['id']}/validations", json={
        "documented_answer": "yes", "followed_process_answer": "no", "decision": "root_cause"})
    assert yes_no.status_code == 409 and yes_no.json()["code"] == "evidence_required"
    with pytest.raises(psycopg.errors.CheckViolation):
        sql("insert into cause_validations (organization_id, cause_id, decision, validated_by) "
            "select organization_id, id, 'root_cause', added_by from ishikawa_causes where id = %s", c_tool["id"])
    with pytest.raises(psycopg.errors.RaiseException):
        sql("update ishikawa_causes set investigation_status = 'root_cause' where id = %s", c_tool["id"])
    ok(ing.post(f"/causes/{c_tool['id']}/validations", json={"decision": "investigating",
                                                            "responsible_user_id": str(users["ing2@t.local"])}), 201)
    causes = ok(ing.post(f"/causes/{c_tool['id']}/validations", json={
        "documented_answer": "yes", "followed_process_answer": "no", "decision": "root_cause",
        "verification_method": "Reproducción con herramienta desgastada", "evidence_summary": "10/10 piezas con rebaba",
        "rationale": "El defecto aparece y desaparece al cambiar la herramienta"}), 201)
    c_tool = next(c for c in causes if c["id"] == c_tool["id"])
    assert c_tool["investigation_status"] == "root_cause" and c_tool["validation_count"] == 2
    assert c_tool["procedure_finding"]["code"] == "procedure_not_followed"
    assert len(ok(ing.get(f"/causes/{c_tool['id']}/validations"))) == 2
    assert ing.patch(f"/causes/{c_tool['id']}", json={"notes": "x"}).json()["code"] == "cause_decided"
    assert ing.delete(f"/causes/{c_tool['id']}").json()["code"] == "has_history"

    pending = ing.post(f"/cases/{cid}/disciplines/D4/submit")
    assert pending.status_code == 409
    ok(ing.post(f"/causes/{c_op['id']}/validations", json={
        "documented_answer": "yes", "followed_process_answer": "yes", "decision": "not_root_cause",
        "verification_method": "Revisión de matriz de habilidades", "evidence_summary": "Certificación vigente",
        "rationale": "El operador está certificado y el defecto persiste con otros operadores"}), 201)
    ok(ing.patch(f"/cases/{cid}/disciplines/D4", json={"content": {
        "occurrence_cause": "Herramienta usada más allá de su vida útil", "escape_point": "Inspección final sin criterio de rebaba",
        "five_whys": ["¿Por qué rebaba?", "¿Por qué desgaste?"]}}))
    case = approve(actors, cid, "D4")
    assert flow(case, "D4")["status"] == "approved"

    # D5 queda disponible y con requisitos pendientes.
    assert flow(case, "D5")["available"] is True and flow(case, "D5")["pending_count"] > 0

    # Reabrir exige comentario y respeta el orden.
    assert mgr.post(f"/cases/{cid}/disciplines/D3/reopen", json={"comment": "x"}).json()["code"] == "later_disciplines"
    assert mgr.post(f"/cases/{cid}/disciplines/D4/reopen", json={}).status_code == 422
    case = ok(mgr.post(f"/cases/{cid}/disciplines/D4/reopen", json={"comment": "Nueva evidencia"}))
    assert flow(case, "D4")["status"] == "in_progress"
    events = {e["event_type"] for e in ok(ing.get(f"/cases/{cid}/audit"))}
    assert {"discipline.approved", "discipline.reopened", "alert.issued", "cause.validated",
            "attachment.uploaded", "containment.updated"} <= events


def test_catalog_change_does_not_alter_case_cause(login, plant, sql):
    mgr = login("gerente@t.local")
    cat = sql("select id from ishikawa_categories where code = 'METHOD'")[0]["id"]
    idea = ok(mgr.post("/cause-ideas", json={"category_id": str(cat), "title_es": "Ajuste manual sin estándar",
                                            "process_tags": ["Ensamble Final"]}), 201)
    assert idea["process_tags"] == ["ensamble_final"]
    case = ok(mgr.post("/cases", json={"plant_id": str(plant), "title": "x"}), 201)
    ok(mgr.post(f"/cases/{case['id']}/causes", json={"category_id": str(cat), "source_idea_id": idea["id"]}), 201)
    ok(mgr.patch(f"/cause-ideas/{idea['id']}", json={"title_es": "Texto cambiado en catálogo"}))
    causes = ok(mgr.get(f"/cases/{case['id']}/causes"))
    assert causes[0]["potential_cause"] == "Ajuste manual sin estándar"
    base = sql("select id from cause_ideas where organization_id is null limit 1")[0]["id"]
    assert mgr.patch(f"/cause-ideas/{base}", json={"title_es": "Intento de editar la base"}).status_code == 404


def test_uploads_are_validated_and_private(login, plant):
    ing, other = login("ing@t.local"), login("otra@x.local")
    case = ok(ing.post("/cases", json={"plant_id": str(plant), "title": "x"}), 201)
    exe = ing.post(f"/cases/{case['id']}/attachments", files={"file": ("foto.png", b"MZ\x90\x00", "image/png")})
    assert exe.status_code == 422
    att = ok(ing.post(f"/cases/{case['id']}/attachments", files={"file": ("a.png", png(), "image/png")}), 201)
    assert ing.get(f"/attachments/{att['id']}/content").headers["x-content-type-options"] == "nosniff"
    assert other.get(f"/attachments/{att['id']}/content").status_code == 404


def test_cancelled_case_is_read_only(login, plant):
    mgr = login("gerente@t.local")
    case = ok(mgr.post("/cases", json={"plant_id": str(plant), "title": "x"}), 201)
    assert mgr.post(f"/cases/{case['id']}/cancel", json={"reason": "abc"}).status_code == 422
    case = ok(mgr.post(f"/cases/{case['id']}/cancel", json={"reason": "Duplicado de otro caso"}))
    assert case["status"] == "cancelled"
    res = mgr.patch(f"/cases/{case['id']}/disciplines/D0", json={"content": {"justification": "x"}})
    assert res.status_code == 409 and res.json()["code"] == "case_closed"
