"""Casos de demostración creados a través de la API (mismas validaciones, aprobaciones y documentos que un usuario).

Quedan marcados con is_demo = true y la interfaz muestra «Datos de demostración».
Requiere el seed (app.seed). Uso (en apps/api): .venv/Scripts/python -m app.demo_data
"""
import io
import sys

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.db import database_url, setting
from app.main import create_app

TITLES = ["Rebaba en carcasa de aluminio 4410-A", "Fuga en conector rápido de manguera 7720-B",
          "Tornillo faltante en soporte de tablero 3305-C"]


def photo(ok: bool) -> bytes:
    """Ilustración simple de la pieza (no es una fotografía real)."""
    img = Image.new("RGB", (640, 420), (236, 239, 244))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((120, 90, 520, 330), 24, fill=(160, 168, 180), outline=(90, 98, 110), width=6)
    d.ellipse((270, 160, 370, 260), fill=(236, 239, 244), outline=(90, 98, 110), width=5)
    if not ok:
        for x in range(130, 510, 22):
            d.polygon([(x, 90), (x + 11, 62), (x + 22, 90)], fill=(198, 40, 40))
        d.text((20, 380), "Ilustración: rebaba en el borde (NOK)", fill=(198, 40, 40))
    else:
        d.text((20, 380), "Ilustración: borde limpio (OK)", fill=(31, 138, 76))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Demo:
    def __init__(self, app, password: str):
        self.c = {}
        for key, email in (("ing", "ingenieria"), ("prod", "produccion"), ("mant", "mantenimiento"),
                           ("mgr", "calidad"), ("admin", "admin")):
            client = TestClient(app, headers={"x-d8-client": "web"})
            r = client.post("/auth/login", json={"email": f"{email}@demo.local", "password": password})
            if r.status_code != 200:
                raise SystemExit(f"No se pudo iniciar sesión como {email}@demo.local: {r.json().get('message')}")
            self.c[key] = client
        users = self.call("ing", "GET", "/users")
        self.uid = {u["email"].split("@")[0]: u["id"] for u in users}
        self.plants = {p["code"]: p["id"] for p in self.call("ing", "GET", "/plants")}
        self.cats = {k["code"]: k["id"] for k in self.call("ing", "GET", "/ishikawa/categories")}

    def call(self, who: str, method: str, path: str, **kw):
        r = self.c[who].request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {r.status_code}: {r.text[:400]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    def approve(self, cid: str, code: str, comment: str = "Revisado y conforme"):
        self.call("ing", "POST", f"/cases/{cid}/disciplines/{code}/submit")
        return self.call("mgr", "POST", f"/cases/{cid}/disciplines/{code}/approve", json={"comment": comment})

    def content(self, cid: str, code: str, **content):
        return self.call("ing", "PATCH", f"/cases/{cid}/disciplines/{code}", json={"content": content})

    def team(self, cid: str):
        self.call("ing", "PUT", f"/cases/{cid}/team", json={"members": [
            {"user_id": self.uid["ingenieria"], "team_role": "leader"},
            {"user_id": self.uid["produccion"], "team_role": "member"},
            {"user_id": self.uid["mantenimiento"], "team_role": "member"},
            {"user_id": self.uid["calidad"], "team_role": "champion"}]})

    # ---- Caso 1: completo y cerrado ----------------------------------------------------------
    def case_closed(self):
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants["PLT1"], "title": TITLES[0], "severity": "high", "source_type": "customer_complaint",
            "customer_name": "Cliente Automotriz Demo", "product_name": "Carcasa de aluminio", "part_number": "4410-A",
            "process_name": "Maquinado CNC", "lot_number": "L-2026-0915", "target_close_date": "2026-10-31"})
        cid = case["id"]
        self.content(cid, "D0", emergency_response="Bloqueo de 3 lotes en almacén y en tránsito; aviso al cliente en 24 h.",
                     justification="Reclamación de cliente con riesgo de interferencia en ensamble; defecto recurrente.")
        self.approve(cid, "D0")
        self.team(cid)
        case = self.approve(cid, "D1")
        self.call("ing", "PATCH", f"/cases/{cid}", json={
            "version": case["version"], "problem_description": "Rebaba de hasta 0.5 mm en el borde exterior de la carcasa "
            "4410-A que impide el asentamiento del sello en la línea del cliente.", "defect_date": "2026-09-16",
            "detected_quantity": 38, "affected_quantity": 1200})
        self.content(cid, "D2", what="Rebaba en el borde exterior (zona de sello)", where="Línea de ensamble del cliente, estación 4",
                     when="16-sep-2026, turno 2; lotes L-2026-0912 a L-2026-0915", who="Inspector de recibo del cliente",
                     how_detected="Falla de asentamiento del sello e inspección visual",
                     is_not="Es: CNC 3, borde exterior. No es: CNC 1 y 2, borde interior")
        self.approve(cid, "D2")
        act = self.call("ing", "POST", f"/cases/{cid}/containment", json={
            "description": "Inspección 100% del inventario en planta, almacén y tránsito", "location": "Almacén PT y tránsito",
            "responsible_user_id": self.uid["produccion"], "due_date": "2026-09-19", "quantity_checked": 1200,
            "quantity_rejected": 41})[0]
        self.call("prod", "PATCH", f"/containment/{act['id']}", json={"status": "implemented",
                                                                     "evidence_notes": "Registro de inspección R-0916 (1 200 piezas, 41 rechazadas)"})
        self.call("mgr", "PATCH", f"/containment/{act['id']}", json={"status": "verified"})
        alert = self.call("ing", "POST", f"/cases/{cid}/alerts", json={"failure_type": "external"})
        self.call("ing", "PATCH", f"/alerts/{alert['id']}", json={
            "when_happened": "16-sep-2026, turno 2", "where_happened": "Cliente — línea de ensamble, estación 4",
            "who_is_affected": "Cliente Automotriz Demo; líneas de ensamble de carcasas",
            "how_detected": "Falla de asentamiento del sello", "affected_areas": "Maquinado CNC 3, almacén PT, embarques"})
        nok = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración NOK"},
                        files={"file": ("nok.png", photo(False), "image/png")})
        good = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración OK"},
                         files={"file": ("ok.png", photo(True), "image/png")})
        self.call("ing", "PUT", f"/alerts/{alert['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "nok"}, {"attachment_id": good["id"], "kind": "ok"}]})
        self.call("mgr", "POST", f"/alerts/{alert['id']}/issue")
        self.approve(cid, "D3")

        causes = self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats["MACHINE"],
                                                                         "potential_cause": "Desgaste de herramienta de corte"})
        root = causes[0]["id"]
        sub = self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats["MACHINE"], "parent_cause_id": root,
                                                                      "potential_cause": "Sin control de vida útil en CNC 3"})
        sub_id = next(x["id"] for x in sub if x["potential_cause"] == "Sin control de vida útil en CNC 3")
        for cat, text in (("METHOD", "Parámetros de corte no especificados"), ("MANPOWER", "Operador de reciente ingreso"),
                          ("MEASUREMENT", "Criterio visual de rebaba ambiguo")):
            self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats[cat], "potential_cause": text})
        listed = self.call("ing", "GET", f"/cases/{cid}/causes")
        evidence = {
            "Desgaste de herramienta de corte": ("root_cause", "yes", "no", "Reproducción con herramienta al 110 % de vida útil",
                                                 "10/10 piezas con rebaba; 0/10 con herramienta nueva",
                                                 "El defecto aparece y desaparece al cambiar la herramienta"),
            "Sin control de vida útil en CNC 3": ("root_cause", "no", "not_applicable", "Revisión del programa y del plan de mantenimiento",
                                                  "CNC 3 sin contador de golpes; CNC 1 y 2 sí lo tienen", "Explica por qué solo CNC 3 falla"),
            "Parámetros de corte no especificados": ("not_root_cause", "yes", "yes", "Auditoría de parámetros vs. hoja de proceso",
                                                     "Parámetros dentro de especificación", "No hay desviación de método"),
            "Operador de reciente ingreso": ("not_root_cause", "yes", "yes", "Matriz de habilidades y prueba con operador senior",
                                             "Defecto persiste con operador certificado", "La mano de obra no cambia el resultado"),
            "Criterio visual de rebaba ambiguo": ("not_root_cause", "yes", "yes", "Estudio de atributos (kappa) con 3 inspectores",
                                                  "Kappa 0.91 (aceptable)", "La detección no es la causa de ocurrencia"),
        }
        for x in listed:
            decision, doc, followed, method, ev, why = evidence[x["potential_cause"]]
            self.call("ing", "POST", f"/causes/{x['id']}/validations", json={
                "decision": decision, "documented_answer": doc, "followed_process_answer": followed,
                "verification_method": method, "evidence_summary": ev, "rationale": why})
        self.content(cid, "D4", occurrence_cause="La herramienta de CNC 3 se usa más allá de su vida útil por falta de contador de golpes.",
                     escape_point="La inspección final no incluía la zona de sello en el plan de control.",
                     five_whys=["¿Por qué hay rebaba? La herramienta corta con filo desgastado.",
                                "¿Por qué está desgastada? Excede su vida útil.",
                                "¿Por qué excede la vida útil? CNC 3 no tiene contador de golpes.",
                                "¿Por qué no tiene contador? Se instaló después del estándar de 2024.",
                                "¿Por qué no se actualizó? El estándar no incluía equipos nuevos."])
        self.approve(cid, "D4")

        plan = [(root, "Cambio de herramienta de corte cada 8 000 piezas en CNC 3", "OT-5520: estándar de cambio publicado en la estación", 1),
                (sub_id, "Instalar contador de golpes con paro automático en CNC 3", "OT-5521: contador instalado y programa actualizado", 0)]
        actions = []
        for cause, text, _, _ in plan:
            rows = self.call("ing", "POST", f"/cases/{cid}/actions", json={
                "action_type": "corrective", "cause_id": cause, "description": text,
                "responsible_user_id": self.uid["mantenimiento"], "due_date": "2026-09-30"})
            actions.append(next(x for x in rows if x["description"] == text))
        eff = self.call("ing", "POST", f"/cases/{cid}/criteria", json={
            "description": "Rebaba en zona de sello ≤ 100 ppm durante 30 días con producción", "metric_name": "Piezas con rebaba",
            "defect_unit": "piezas", "denominator_type": "units_produced", "threshold_type": "max_rate_ppm",
            "threshold_value": 100, "min_period_days": 30, "min_denominator": 5000})
        self.call("mgr", "POST", f"/criteria/{eff['criteria'][0]['id']}/approve")
        self.content(cid, "D5", verification_plan="Prueba piloto de 2 semanas en CNC 3 con contador y medición 100% de la zona de sello.")
        self.approve(cid, "D5")
        for action, (_, _, evidence, defects) in zip(actions, plan):
            self.call("mant", "POST", f"/actions/{action['id']}/start")
            self.call("mant", "POST", f"/actions/{action['id']}/submit", json={"implementation_evidence": evidence})
            self.call("mgr", "POST", f"/actions/{action['id']}/approve", json={"comment": "Verificado en piso"})
            check = self.call("ing", "POST", f"/actions/{action['id']}/checks", json={
                "criterion_id": eff["criteria"][0]["id"], "period_start": "2026-09-26", "period_end": "2026-10-26",
                "denominator_quantity": 24600, "defect_quantity": defects, "days_without_production": 0,
                "data_notes": "Conteo del sistema MES y registro de inspección 100%"})
            pending = next(x for x in check["checks"] if x["result"] == "pending")
            self.call("ing", "POST", f"/checks/{pending['id']}/decide", json={
                "result": "effective", "rationale": f"{defects / 24600 * 1e6:.0f} ppm frente a límite de 100 ppm en 31 días con producción"})
        self.content(cid, "D6", validation_summary="Acciones implementadas (OT-5520, OT-5521) y eficaces: ≤ 41 ppm en 31 días (límite 100 ppm).")
        self.approve(cid, "D6")

        prev = self.call("ing", "POST", f"/cases/{cid}/actions", json={
            "action_type": "systemic", "description": "Actualizar el estándar de equipos para exigir contador de golpes en toda CNC nueva",
            "responsible_user_id": self.uid["ingenieria"], "due_date": "2026-10-20"})
        sysid = next(x["id"] for x in prev if x["action_type"] == "systemic")
        self.call("ing", "POST", f"/actions/{sysid}/submit", json={"implementation_evidence": "EST-MAQ-004 rev. D publicado"})
        self.call("mgr", "POST", f"/actions/{sysid}/approve", json={})
        for kind, ref, ev in (("pfmea", "PFMEA-CNC-12", "Rev. D: modo de falla «rebaba por desgaste» RPN 160 → 48"),
                              ("control_plan", "PC-4410-A", "Rev. F: inspección de zona de sello cada 50 piezas"),
                              ("training", "CAP-2026-118", "12 operadores y 3 inspectores capacitados")):
            upd = self.call("ing", "POST", f"/cases/{cid}/system-updates", json={"update_type": kind, "document_reference": ref})
            self.call("ing", "PATCH", f"/system-updates/{upd[-1]['id']}", json={"status": "completed", "completed_on": "2026-10-15",
                                                                                 "evidence_notes": ev})
        self.content(cid, "D7", horizontal_deployment="Contador de golpes verificado en CNC 1–6 de PLT1 y en las CNC de PLT2.")
        self.approve(cid, "D7")

        lesson = self.call("ing", "POST", f"/cases/{cid}/lessons")
        self.call("ing", "PATCH", f"/lessons/{lesson['id']}", json={
            "before_summary": "3.4 % de piezas con rebaba en CNC 3 y reclamación del cliente.",
            "after_summary": "41 ppm en 31 días; sin reclamaciones.",
            "training_summary": "Capacitación CAP-2026-118 sobre control de vida útil.",
            "situations": ["Equipos nuevos sin contador de golpes", "Herramental con vida útil limitada"]})
        self.call("ing", "PUT", f"/lessons/{lesson['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "before", "caption": "Ilustración: rebaba en la zona de sello"},
            {"attachment_id": good["id"], "kind": "after", "caption": "Ilustración: borde limpio tras el control de vida útil"}]})
        self.call("ing", "POST", f"/lessons/{lesson['id']}/submit")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/review", json={"decision": "approve", "comment": "Clara y reutilizable"})
        self.content(cid, "D8", closure_summary="Causa raíz eliminada, eficacia demostrada y sistema actualizado. Cliente notificado.",
                     team_recognition="Reconocimiento al equipo de Maquinado y Mantenimiento por la respuesta en 24 h.")
        self.approve(cid, "D8", "Caso cerrado")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/publish")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/document")
        for kind in ("8d_full", "8d_progress", "audit_report"):
            self.call("mgr", "POST", f"/cases/{cid}/documents/{kind}")
        self.call("mgr", "POST", f"/cases/{cid}/export")
        return cid, lesson["id"]

    # ---- Caso 2: en D6, eficacia con datos incompletos ------------------------------------------
    def case_in_d6(self, lesson_id: str):
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants["PLT2"], "title": TITLES[1], "severity": "critical", "source_type": "internal",
            "product_name": "Manguera de enfriamiento", "part_number": "7720-B", "process_name": "Ensamble",
            "customer_name": "Cliente Automotriz Demo", "target_close_date": "2026-10-20"})
        cid = case["id"]
        self.content(cid, "D0", emergency_response="Prueba de fuga 100% en línea antes de empaque.",
                     justification="Riesgo de fuga de refrigerante; severidad crítica.")
        self.approve(cid, "D0")
        self.team(cid)
        case = self.approve(cid, "D1")
        self.call("ing", "PATCH", f"/cases/{cid}", json={"version": case["version"], "problem_description":
                  "Fuga en el conector rápido detectada en la prueba de hermeticidad al final de línea.",
                  "defect_date": "2026-09-28", "detected_quantity": 12, "affected_quantity": 450})
        self.content(cid, "D2", what="Fuga en conector rápido", where="Prueba de hermeticidad, fin de línea",
                     when="28-sep-2026", how_detected="Prueba de caída de presión")
        self.approve(cid, "D2")
        act = self.call("ing", "POST", f"/cases/{cid}/containment", json={
            "description": "Prueba de fuga 100% y segregación de lotes", "responsible_user_id": self.uid["produccion"],
            "due_date": "2026-10-01"})[0]
        self.call("prod", "PATCH", f"/containment/{act['id']}", json={"status": "implemented", "evidence_notes": "Registro PF-0929"})
        self.call("mgr", "PATCH", f"/containment/{act['id']}", json={"status": "verified"})
        alert = self.call("ing", "POST", f"/cases/{cid}/alerts", json={"failure_type": "internal"})
        self.call("ing", "PATCH", f"/alerts/{alert['id']}", json={"where_happened": "Ensamble PLT2", "who_is_affected": "Línea de ensamble",
                                                                   "how_detected": "Prueba de caída de presión"})
        self.call("mgr", "POST", f"/alerts/{alert['id']}/issue")
        self.approve(cid, "D3")
        causes = self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats["MATERIAL"],
                                                                         "potential_cause": "O-ring fuera de especificación del proveedor"})
        root = causes[0]["id"]
        self.call("ing", "POST", f"/causes/{root}/validations", json={
            "decision": "root_cause", "documented_answer": "yes", "followed_process_answer": "yes",
            "verification_method": "Medición de dureza Shore A en 30 muestras", "evidence_summary": "Dureza 62 vs. 70±5 especificado",
            "rationale": "Las piezas con fuga tienen O-rings fuera de especificación"})
        self.content(cid, "D4", occurrence_cause="O-ring de dureza insuficiente del lote del proveedor.",
                     escape_point="La inspección de recibo no mide dureza.")
        self.approve(cid, "D4")
        action = self.call("ing", "POST", f"/cases/{cid}/actions", json={
            "action_type": "corrective", "cause_id": root, "description": "Agregar medición de dureza al plan de inspección de recibo",
            "responsible_user_id": self.uid["produccion"], "due_date": "2026-10-10"})[0]
        eff = self.call("ing", "POST", f"/cases/{cid}/criteria", json={
            "description": "Cero fugas en 20 días con producción", "metric_name": "Conectores con fuga", "defect_unit": "piezas",
            "denominator_type": "units_inspected", "threshold_type": "max_defects", "threshold_value": 0,
            "min_period_days": 20, "min_denominator": 2000})
        self.call("mgr", "POST", f"/criteria/{eff['criteria'][0]['id']}/approve")
        self.content(cid, "D5", verification_plan="Lote piloto con O-rings medidos y prueba de fuga 100%.")
        self.approve(cid, "D5")
        self.call("prod", "POST", f"/actions/{action['id']}/submit", json={"implementation_evidence": "PI-REC-7720 rev. C"})
        self.call("mgr", "POST", f"/actions/{action['id']}/approve", json={})
        check = self.call("ing", "POST", f"/actions/{action['id']}/checks", json={
            "criterion_id": eff["criteria"][0]["id"], "period_start": "2026-10-11", "period_end": "2026-10-26",
            "denominator_quantity": 3100, "days_without_production": 2,
            "data_notes": "Falta el registro de fugas del turno 3 (sistema caído del 20 al 22-oct)"})
        pending = next(x for x in check["checks"] if x["result"] == "pending")
        self.call("ing", "POST", f"/checks/{pending['id']}/decide", json={
            "result": "insufficient_data", "rationale": "Faltan defectos del turno 3 y solo hay 14 días con producción; se repetirá la medición."})
        self.call("ing", "POST", f"/lessons/{lesson_id}/apply", json={
            "target_case_id": cid, "outcome": "partially_applied",
            "evaluation": "Se revisó si los equipos de prueba de fuga tienen control de vida útil de sellos; se aplicó a los sellos de la fixtura."})
        return cid

    # ---- Caso 3: en D3 ----------------------------------------------------------------------
    def case_in_d3(self):
        case = self.call("prod", "POST", "/cases", json={
            "plant_id": self.plants["PLT1"], "title": TITLES[2], "severity": "medium", "source_type": "audit",
            "product_name": "Soporte de tablero", "part_number": "3305-C", "process_name": "Ensamble",
            "target_close_date": "2026-11-30"})
        cid = case["id"]
        self.content(cid, "D0", emergency_response="Revisión 100% del turno afectado.", justification="Hallazgo de auditoría de producto.")
        self.approve(cid, "D0")
        self.team(cid)
        case = self.approve(cid, "D1")
        self.call("ing", "PATCH", f"/cases/{cid}", json={"version": case["version"], "problem_description":
                  "Soporte de tablero ensamblado con un tornillo faltante en la posición 3.", "defect_date": "2026-10-22",
                  "detected_quantity": 3, "affected_quantity": 600})
        self.content(cid, "D2", what="Tornillo faltante en posición 3", where="Auditoría de producto", when="22-oct-2026",
                     how_detected="Auditoría de producto terminado")
        self.approve(cid, "D2")
        self.call("ing", "POST", f"/cases/{cid}/containment", json={
            "description": "Revisión 100% de 600 piezas en almacén", "responsible_user_id": self.uid["produccion"],
            "due_date": "2026-10-24", "quantity_checked": 380, "quantity_rejected": 2})
        alert = self.call("ing", "POST", f"/cases/{cid}/alerts", json={"failure_type": "internal"})
        self.call("ing", "PATCH", f"/alerts/{alert['id']}", json={"where_happened": "Ensamble PLT1, estación de atornillado"})
        return cid


def main() -> int:
    password = setting("DEMO_PASSWORD")
    if not password:
        print("Falta DEMO_PASSWORD en .env", file=sys.stderr)
        return 1
    app = create_app(database_url())
    with TestClient(app):
        demo = Demo(app, password)
        existing = {c["title"] for c in demo.call("admin", "GET", "/cases")}
        if existing & set(TITLES):
            print("Los casos de demostración ya existen; no se crean de nuevo.")
            return 0
        closed, lesson = demo.case_closed()
        d6 = demo.case_in_d6(lesson)
        d3 = demo.case_in_d3()
        with app.state.db.transaction() as conn:
            conn.execute("update cases_8d set is_demo = true where id = any(%s)", ([closed, d6, d3],))
    print(f"Casos de demostración creados: cerrado {closed}, en D6 {d6}, en D3 {d3}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
