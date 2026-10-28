"""Seguridad, almacenamiento, reglas de causas y PDF (sin base de datos)."""
import io
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from app import causes_rules, pdf_alert, storage
from app.errors import ApiError
from app.permissions import permissions_for
from app.security import hash_password, new_session_token, token_sha256, verify_password

def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 3), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


PNG_1PX = _png()


def test_password_hash_roundtrip_and_salt():
    h1, h2 = hash_password("correcta-123"), hash_password("correcta-123")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("correcta-123", h1)
    assert not verify_password("incorrecta", h1)
    assert not verify_password("x", None)
    assert not verify_password("x", "basura")


def test_session_token_only_hash_is_stored():
    token, digest = new_session_token()
    assert len(digest) == 64 and token not in digest and token_sha256(token) == digest


def test_permissions_matrix():
    assert permissions_for({"viewer"}) == {"case.read", "lesson.read"}
    engineer = permissions_for({"engineer"})
    assert {"discipline.approve", "action.approve", "criteria.approve", "lesson.review", "lesson.publish",
            "audit.read"}.isdisjoint(engineer)
    assert {"action.edit", "effectiveness.edit", "lesson.edit", "report.export"} <= engineer
    assert {"discipline.approve", "alert.issue", "lesson.retire"} <= permissions_for({"quality_manager"})
    assert "admin.users" in permissions_for({"admin"})
    assert "admin.users" not in permissions_for({"quality_manager"})


def test_sniff_by_content_not_by_name():
    assert storage.sniff(PNG_1PX) == "image/png"
    assert storage.sniff(b"%PDF-1.7 ...") == "application/pdf"
    with pytest.raises(ApiError):
        storage.sniff(b"MZ\x90\x00 ejecutable")
    with pytest.raises(ApiError):
        storage.sniff(b"")
    with pytest.raises(ApiError):
        storage.sniff(b"%PDF-" + b"0" * storage.MAX_BYTES)


def test_safe_name_strips_paths_and_forces_extension():
    assert storage.safe_name("..\\..\\evil.exe", "image/png") == "evil.exe.png"
    assert storage.safe_name('foto "1".jpg', "image/jpeg") == "foto _1_.jpg"


def test_suggestions_match_tags_and_skip_used():
    ideas = [
        {"id": 1, "title_es": "Desgaste de herramental", "process_tags": ["maquinado"], "defect_tags": ["rebaba"]},
        {"id": 2, "title_es": "Humedad del material", "process_tags": ["inyeccion"], "defect_tags": ["porosidad"]},
        {"id": 3, "title_es": "Genérica", "process_tags": [], "defect_tags": []},
    ]
    text = {"process": "Maquinado CNC", "title": "Rebaba en borde", "problem": None}
    result = causes_rules.suggest(text, ideas, used_idea_ids=set())
    assert [r["id"] for r in result] == [1] and result[0]["score"] == 2
    assert causes_rules.suggest(text, ideas, used_idea_ids={1}) == []
    # Acentos y mayúsculas no impiden la coincidencia.
    assert causes_rules.suggest({"process": "INYECCIÓN"}, ideas, set())[0]["id"] == 2


def test_procedure_finding_distinguishes_missing_vs_not_followed():
    assert causes_rules.procedure_finding("no", "unknown")["code"] == "procedure_missing"
    assert causes_rules.procedure_finding("yes", "no")["code"] == "procedure_not_followed"
    assert causes_rules.procedure_finding("yes", "yes")["code"] == "procedure_followed"
    assert causes_rules.procedure_finding("unknown", "no") is None


def test_alert_pdf_renders_with_photos_and_qr():
    alert = {"alert_number": 7, "revision": 2, "failure_type": "external", "title": "Rebaba <borde> & filo",
             "what_happened": "Rebaba", "when_happened": "2026-10-01", "where_happened": "Cliente",
             "who_is_affected": "Cliente A", "how_detected": "Visual", "affected_areas": "Línea 3",
             "affected_quantity": 1200, "containment_summary": "• Bloqueo", "revision_reason": "Cambio de cantidad"}
    case = {"folio": "8D-PLT1-2026-0001", "part_number": "123-A", "product_name": "Carcasa"}
    pdf = pdf_alert.render(alert, case, "Org", "PLT1 — Planta", [("nok", PNG_1PX)], "Ana", "Luis",
                           datetime(2026, 10, 27, tzinfo=timezone.utc), "http://localhost:3000/alertas/x")
    reader = PdfReader(io.BytesIO(pdf))
    text = reader.pages[0].extract_text()
    assert len(reader.pages) == 1
    for expected in ("ALERTA DE CALIDAD", "FALLA EXTERNA", "QA-0007", "Rev. 2", "8D-PLT1-2026-0001", "1,200 piezas",
                     "Sin fotografía adjunta"):
        assert expected in text
