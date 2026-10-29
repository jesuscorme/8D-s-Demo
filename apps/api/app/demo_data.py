"""Casos de demostración creados a través de la API (mismas validaciones, aprobaciones y documentos que un usuario).

Quedan marcados con is_demo = true y la interfaz muestra «Datos de demostración».
Requiere el seed (app.seed). Uso (en apps/api): .venv/Scripts/python -m app.demo_data
"""
import io
import sys
from datetime import date, timedelta

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.db import database_url, setting
from app.main import create_app

TITLES = ["Rebaba en carcasa de aluminio 4410-A", "Fuga en conector rápido de manguera 7720-B",
          "Tornillo faltante en soporte de tablero 3305-C"]
FORD_TITLE = "Grieta en brida de soporte de motor 5560-D"


def photo(ok: bool, defect: str = "burr") -> bytes:
    """Ilustración simple de la pieza (no es una fotografía real). defect: burr (rebaba) o crack (grieta)."""
    img = Image.new("RGB", (640, 420), (236, 239, 244))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((120, 90, 520, 330), 24, fill=(160, 168, 180), outline=(90, 98, 110), width=6)
    d.ellipse((270, 160, 370, 260), fill=(236, 239, 244), outline=(90, 98, 110), width=5)
    if not ok and defect == "crack":
        d.line([(370, 205), (405, 190), (420, 222), (455, 210), (470, 245), (505, 238)], fill=(198, 40, 40), width=6)
        d.text((20, 380), "Ilustración: grieta junto al barreno (NOK)", fill=(198, 40, 40))
    elif not ok:
        for x in range(130, 510, 22):
            d.polygon([(x, 90), (x + 11, 62), (x + 22, 90)], fill=(198, 40, 40))
        d.text((20, 380), "Ilustración: rebaba en el borde (NOK)", fill=(198, 40, 40))
    else:
        d.text((20, 380), "Ilustración: pieza sin defecto (OK)" if defect == "crack" else "Ilustración: borde limpio (OK)",
               fill=(31, 138, 76))
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

    def contain(self, cid: str, lots: list[tuple], result_notes: str):
        """Registro de contención de D3 (requiere la alerta emitida): inicio con aviso a logística, lotes y fin."""
        self.call("ing", "POST", f"/cases/{cid}/containment-record/start", json={})
        for lot, location, inspected, rejected, disposition in lots:
            self.call("prod", "POST", f"/cases/{cid}/containment-lots", json={
                "lot_number": lot, "location": location, "quantity_inspected": inspected,
                "quantity_rejected": rejected, "disposition": disposition})
        self.call("prod", "POST", f"/cases/{cid}/containment-record/end", json={"result": "effective", "result_notes": result_notes})

    # ---- Caso 1: completo y cerrado ----------------------------------------------------------
    def case_closed(self):
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants["PLT1"], "title": TITLES[0], "severity": "high", "source_type": "customer_complaint",
            "customer_name": "General Motors", "product_name": "Carcasa de aluminio", "part_number": "4410-A",
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
            "who_is_affected": "General Motors; líneas de ensamble de carcasas",
            "how_detected": "Falla de asentamiento del sello", "affected_areas": "Maquinado CNC 3, almacén PT, embarques"})
        nok = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración NOK"},
                        files={"file": ("nok.png", photo(False), "image/png")})
        good = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración OK"},
                         files={"file": ("ok.png", photo(True), "image/png")})
        self.call("ing", "PUT", f"/alerts/{alert['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "nok"}, {"attachment_id": good["id"], "kind": "ok"}]})
        self.call("mgr", "POST", f"/alerts/{alert['id']}/issue")
        self.contain(cid, [("L-2026-0912", "Almacén PT", 300, 9, "rework"), ("L-2026-0913", "Almacén PT", 300, 11, "rework"),
                           ("L-2026-0914", "Tránsito a cliente", 300, 12, "rework"), ("L-2026-0915", "Cliente", 300, 9, "returned")],
                     "1 200 piezas revisadas; 41 con rebaba retrabajadas o devueltas. Sin escapes en embarques posteriores.")
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

    # ---- Caso 4: externo (Ford), completo y cerrado dentro de los hitos de 24 h / 48 h / 7 / 14 días ----
    def case_closed_ford(self):
        today = date.today()
        reported = today - timedelta(days=1)
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants["PLT1"], "title": FORD_TITLE, "severity": "high", "case_type": "external",
            "source_type": "customer_complaint", "customer_name": "Ford", "product_name": "Soporte de motor (brida)",
            "part_number": "5560-D", "process_name": "Inyección de aluminio (HPDC)", "lot_number": "L-5560-1026",
            "market_segment": "OEM", "main_defect": "Grieta", "report_date": reported.isoformat(),
            "target_close_date": (reported + timedelta(days=14)).isoformat()})
        cid = case["id"]
        self.content(cid, "D0", emergency_response="Retención de inventario en planta y en tránsito; aviso a Ford en menos de 24 h.",
                     justification="Reclamación de cliente OEM en una pieza de soporte estructural; riesgo de falla en campo.")
        self.approve(cid, "D0")
        self.team(cid)
        case = self.approve(cid, "D1")
        self.call("ing", "PATCH", f"/cases/{cid}", json={
            "version": case["version"], "problem_description": "Grieta de 3 a 6 mm junto al barreno de fijación de la brida "
            "5560-D, detectada por Ford en la inspección de recibo.", "defect_date": reported.isoformat(),
            "detected_quantity": 14, "affected_quantity": 1800})
        self.content(cid, "D2", what="Grieta junto al barreno de fijación de la brida",
                     where="Inspección de recibo de Ford; origen en celda de inyección 2 (HPDC-2)",
                     when=f"{reported:%d-%m-%Y}; lotes L-5560-1024 a L-5560-1026", who="Inspector de recibo de Ford",
                     how_detected="Inspección visual y líquidos penetrantes",
                     is_not="Es: HPDC-2, cavidad 1, barreno de fijación. No es: HPDC-1, cavidad 2, otras zonas de la brida")
        self.approve(cid, "D2")

        act = self.call("ing", "POST", f"/cases/{cid}/containment", json={
            "description": "Inspección 100% con líquidos penetrantes del inventario en planta, almacén y tránsito",
            "location": "Almacén PT y tránsito", "responsible_user_id": self.uid["produccion"],
            "due_date": today.isoformat(), "quantity_checked": 1800, "quantity_rejected": 17})[0]
        self.call("prod", "PATCH", f"/containment/{act['id']}", json={
            "status": "implemented", "evidence_notes": "Registro LP-5560 (1 800 piezas, 17 con grieta)"})
        self.call("mgr", "PATCH", f"/containment/{act['id']}", json={"status": "verified"})
        alert = self.call("ing", "POST", f"/cases/{cid}/alerts", json={})
        self.call("ing", "PATCH", f"/alerts/{alert['id']}", json={
            "when_happened": f"{reported:%d-%m-%Y}, inspección de recibo", "where_happened": "Ford — inspección de recibo",
            "who_is_affected": "Ford; línea de ensamble de motor", "how_detected": "Líquidos penetrantes en el barreno de fijación",
            "affected_quantity": 1800, "affected_areas": "Inyección HPDC-2, almacén PT, embarques",
            "containment_summary": "Retención e inspección 100% con líquidos penetrantes; piezas con grieta a desecho"})
        nok = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración NOK"},
                        files={"file": ("grieta_nok.png", photo(False, "crack"), "image/png")})
        good = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración OK"},
                         files={"file": ("brida_ok.png", photo(True, "crack"), "image/png")})
        self.call("ing", "PUT", f"/alerts/{alert['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "nok"}, {"attachment_id": good["id"], "kind": "ok"}]})
        self.call("mgr", "POST", f"/alerts/{alert['id']}/issue")
        self.contain(cid, [("L-5560-1024", "Almacén PT", 600, 4, "scrap"), ("L-5560-1025", "Almacén PT", 600, 6, "scrap"),
                           ("L-5560-1026", "Tránsito a Ford", 600, 7, "scrap")],
                     "1 800 piezas revisadas con líquidos penetrantes; 17 con grieta a desecho. Ford confirma cero piezas adicionales.")
        self.approve(cid, "D3")

        # Ishikawa con incidencias: la causa con más ocurrencias registradas es la que se valida como raíz.
        ideas = [("MACHINE", "Canal de enfriamiento del molde obstruido en la cavidad 1", 9),
                 ("METHOD", "Temperatura de molde sin límite de control en arranque", 6),
                 ("MATERIAL", "Aleación con hierro fuera de especificación", 2),
                 ("MANPOWER", "Extracción manual de la pieza antes de tiempo", 1),
                 ("MEASUREMENT", "Inspección de grietas solo por muestreo", 4)]
        for cat, text, incidences in ideas:
            self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats[cat], "potential_cause": text,
                                                                    "incidence_count": incidences})
        listed = {x["potential_cause"]: x["id"] for x in self.call("ing", "GET", f"/cases/{cid}/causes")}
        evidence = {
            ideas[0][1]: ("root_cause", "yes", "no", "Prueba de flujo del circuito y termografía del molde",
                          "Flujo 40 % del nominal; 285 °C en cavidad 1 vs. 220 °C en cavidad 2",
                          "Las grietas solo aparecen en la cavidad con el canal obstruido"),
            ideas[1][1]: ("root_cause", "no", "not_applicable", "Revisión del plan de control y del registro de arranque",
                          "Sin límite de temperatura de molde; 9 de 14 piezas con grieta son del primer turno tras arranque",
                          "Permite operar con el molde fuera de ventana térmica"),
            ideas[2][1]: ("not_root_cause", "yes", "yes", "Espectrometría de 5 coladas", "Fe 0.8 % (especificación ≤ 1.0 %)",
                          "La aleación cumple"),
            ideas[3][1]: ("not_root_cause", "yes", "yes", "Revisión de video de la celda (robot de extracción)",
                          "La extracción es automática; no hay intervención manual", "No aplica al proceso actual"),
            ideas[4][1]: ("not_root_cause", "yes", "yes", "Revisión del plan de inspección",
                          "El muestreo explica el escape, no la ocurrencia", "Se atiende como punto de escape en D4"),
        }
        for text, (decision, doc, followed, method, ev, why) in evidence.items():
            self.call("ing", "POST", f"/causes/{listed[text]}/validations", json={
                "decision": decision, "documented_answer": doc, "followed_process_answer": followed,
                "verification_method": method, "evidence_summary": ev, "rationale": why})
        self.content(cid, "D4", occurrence_cause="Canal de enfriamiento de la cavidad 1 obstruido por sarro: la zona del barreno "
                     "solidifica más caliente y se agrieta por contracción.",
                     escape_point="La inspección de grietas era por muestreo y no incluía líquidos penetrantes en el barreno.",
                     five_whys=["¿Por qué hay grieta? La zona del barreno se contrae a mayor temperatura.",
                                "¿Por qué está más caliente? El canal de enfriamiento de la cavidad 1 tiene 40 % de flujo.",
                                "¿Por qué tiene poco flujo? Está obstruido por sarro.",
                                "¿Por qué hay sarro? El agua de enfriamiento no tiene tratamiento ni limpieza programada.",
                                "¿Por qué no se detectó? No hay monitoreo de flujo ni límite de temperatura de molde."])
        self.approve(cid, "D4")

        plan = [(listed[ideas[0][1]], "Limpieza química de canales y filtro con tratamiento de agua en HPDC-2",
                 "OT-7781: canales limpios, flujo 98 % del nominal"),
                (listed[ideas[1][1]], "Sensor de flujo y temperatura de molde con paro automático fuera de ventana",
                 "OT-7782: sensores instalados y alarma probada")]
        actions = []
        for cause, text, _ in plan:
            rows = self.call("ing", "POST", f"/cases/{cid}/actions", json={
                "action_type": "corrective", "cause_id": cause, "description": text,
                "responsible_user_id": self.uid["mantenimiento"], "due_date": today.isoformat()})
            actions.append(next(x for x in rows if x["description"] == text))
        eff = self.call("ing", "POST", f"/cases/{cid}/criteria", json={
            "description": "Cero piezas con grieta (líquidos penetrantes 100%) en 2 días con producción y al menos 3 000 piezas",
            "metric_name": "Piezas con grieta", "defect_unit": "piezas", "denominator_type": "units_produced",
            "threshold_type": "max_defects", "threshold_value": 0, "min_period_days": 2, "min_denominator": 3000})
        self.call("mgr", "POST", f"/criteria/{eff['criteria'][0]['id']}/approve")
        self.content(cid, "D5", verification_plan="Corrida a ritmo (run @ rate) en HPDC-2 con inspección 100% por líquidos "
                     "penetrantes y registro de temperatura de molde.")
        self.approve(cid, "D5")
        for action, (_, _, ev) in zip(actions, plan):
            self.call("mant", "POST", f"/actions/{action['id']}/start")
            self.call("mant", "POST", f"/actions/{action['id']}/submit", json={"implementation_evidence": ev})
            self.call("mgr", "POST", f"/actions/{action['id']}/approve", json={"comment": "Verificado en piso"})
            check = self.call("ing", "POST", f"/actions/{action['id']}/checks", json={
                "criterion_id": eff["criteria"][0]["id"], "period_start": reported.isoformat(), "period_end": today.isoformat(),
                "denominator_quantity": 3240, "defect_quantity": 0, "days_without_production": 0,
                "data_notes": "Conteo del MES y registro de líquidos penetrantes 100%"})
            pending = next(x for x in check["checks"] if x["result"] == "pending")
            self.call("ing", "POST", f"/checks/{pending['id']}/decide", json={
                "result": "effective", "rationale": "0 piezas con grieta en 3 240 producidas (2 días con producción)"})
        self.content(cid, "D6", validation_summary="Acciones OT-7781 y OT-7782 implementadas y eficaces: 0 grietas en 3 240 piezas.")
        self.approve(cid, "D6")

        prev = self.call("ing", "POST", f"/cases/{cid}/actions", json={
            "action_type": "systemic", "description": "Incluir monitoreo de flujo y limpieza de canales en el estándar de moldes HPDC",
            "responsible_user_id": self.uid["ingenieria"], "due_date": today.isoformat()})
        sysid = next(x["id"] for x in prev if x["action_type"] == "systemic")
        self.call("ing", "POST", f"/actions/{sysid}/submit", json={"implementation_evidence": "EST-HPDC-002 rev. C publicado"})
        self.call("mgr", "POST", f"/actions/{sysid}/approve", json={})
        for kind, ref, ev in (("pfmea", "PFMEA-HPDC-07", "Rev. E: modo de falla «grieta por sobrecalentamiento» RPN 180 → 40"),
                              ("control_plan", "PC-5560-D", "Rev. G: temperatura de molde con límite y líquidos penetrantes 1/50"),
                              ("training", "CAP-2026-131", "8 operadores y 2 técnicos de mantenimiento capacitados")):
            upd = self.call("ing", "POST", f"/cases/{cid}/system-updates", json={"update_type": kind, "document_reference": ref})
            self.call("ing", "PATCH", f"/system-updates/{upd[-1]['id']}", json={"status": "completed", "completed_on": today.isoformat(),
                                                                                 "evidence_notes": ev})
        self.content(cid, "D7", horizontal_deployment="Prueba de flujo y sensores verificados en los 6 moldes HPDC de PLT1 y PLT2.")
        self.approve(cid, "D7")

        lesson = self.call("ing", "POST", f"/cases/{cid}/lessons")
        self.call("ing", "PATCH", f"/lessons/{lesson['id']}", json={
            "before_summary": "14 bridas con grieta en Ford; canal de enfriamiento al 40 % de flujo y sin límite de temperatura de molde.",
            "after_summary": "0 grietas en 3 240 piezas; flujo y temperatura de molde monitoreados con paro automático.",
            "training_summary": "Capacitación CAP-2026-131 sobre ventana térmica del molde.",
            "situations": ["Moldes HPDC con canales de enfriamiento", "Piezas estructurales con barrenos cerca de zonas gruesas"]})
        self.call("ing", "PUT", f"/lessons/{lesson['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "before", "caption": "Ilustración: grieta junto al barreno de fijación"},
            {"attachment_id": good["id"], "kind": "after", "caption": "Ilustración: brida sin grieta tras corregir el enfriamiento"}]})
        self.call("ing", "POST", f"/lessons/{lesson['id']}/submit")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/review", json={"decision": "approve", "comment": "Clara y reutilizable"})
        self.content(cid, "D8", closure_summary="Causa raíz eliminada, eficacia demostrada y sistema actualizado. Ford aceptó el 8D.",
                     team_recognition="Reconocimiento al equipo de Inyección y Mantenimiento por cerrar dentro de los 14 días.")
        self.approve(cid, "D8", "Caso cerrado")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/publish")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/document")
        for kind in ("8d_full", "8d_progress", "audit_report"):
            self.call("mgr", "POST", f"/cases/{cid}/documents/{kind}")
        self.call("mgr", "POST", f"/cases/{cid}/export")
        return cid

    # ---- Caso 2: en D6, eficacia con datos incompletos ------------------------------------------
    def case_in_d6(self, lesson_id: str):
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants["PLT2"], "title": TITLES[1], "severity": "critical", "source_type": "internal",
            "product_name": "Manguera de enfriamiento", "part_number": "7720-B", "process_name": "Ensamble",
            "customer_name": "Toyota", "target_close_date": "2026-10-20"})
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
        self.contain(cid, [("L-7720-0927", "Ensamble PLT2", 250, 7, "scrap"), ("L-7720-0928", "Almacén PT", 200, 5, "scrap")],
                     "450 conectores probados; 12 con fuga desechados. Lotes liberados con prueba 100%.")
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
        created = []
        if existing & set(TITLES):
            print("Los casos de demostración base ya existen; no se crean de nuevo.")
        else:
            closed, lesson = demo.case_closed()
            created += [closed, demo.case_in_d6(lesson), demo.case_in_d3()]
        if FORD_TITLE not in existing:
            created.append(demo.case_closed_ford())
        with app.state.db.transaction() as conn:
            conn.execute("update cases_8d set is_demo = true where id = any(%s)", (created,))
    print(f"Casos de demostración creados: {len(created)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
