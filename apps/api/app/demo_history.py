"""Historial de demostración para el tablero: 8D de mayo a octubre con varias armadoras, internos y externos, en
distintas disciplinas. Se crean por la API (mismas validaciones que un usuario) y después se ajustan las fechas de
reporte, aprobación y cierre a la línea de tiempo simulada (solo en casos is_demo; la bitácora conserva la fecha real).
Uso (en apps/api, después de app.demo_data): .venv/Scripts/python -m app.demo_history
"""
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db import database_url, setting
from app.demo_data import Demo, photo
from app.main import create_app

CODES = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]
# Día (desde la fecha de reporte) en que se aprueba cada disciplina.
PACE = {
    "fast": [0, 0, 1, 1, 2, 4, 9, 11, 13],
    "ok": [0, 0, 1, 1, 2, 5, 10, 12, 14],
    "slow": [0, 1, 2, 3, 6, 10, 18, 22, 30],
}

# Por defecto: causa raíz, causas descartadas (categoría, texto, incidencias), acción correctiva y sistémica.
DEFECTS = {
    "Rebaba": (("MACHINE", "Herramienta de corte fuera de vida útil", 8),
               [("METHOD", "Parámetros de corte sin control", 3), ("MEASUREMENT", "Criterio visual ambiguo", 2)],
               "Control de vida útil de herramienta con contador", "Estándar de vida útil para todas las CNC"),
    "Fuga": (("MATERIAL", "Sello con dureza fuera de especificación", 7),
             [("METHOD", "Torque de ensamble variable", 3), ("MACHINE", "Prueba de fuga con fuga en fixtura", 2)],
             "Medición de dureza en recibo y prueba de fuga 100%", "Requisito de dureza en la especificación de compra"),
    "Grieta": (("MACHINE", "Enfriamiento de molde insuficiente", 9),
               [("MATERIAL", "Aleación fuera de especificación", 2), ("MANPOWER", "Extracción prematura", 1)],
               "Limpieza de canales y monitoreo de temperatura de molde", "Monitoreo térmico en todos los moldes"),
    "Porosidad": (("METHOD", "Desgasificado del aluminio insuficiente", 6),
                  [("MACHINE", "Vacío del molde intermitente", 4), ("MATERIAL", "Chatarra con humedad", 2)],
                  "Tiempo de desgasificado con prueba de densidad por colada", "Prueba de densidad en el plan de control"),
    "Dimensional": (("MACHINE", "Fixtura desgastada en el pin de localización", 7),
                    [("MEASUREMENT", "Gage sin calibración vigente", 3), ("METHOD", "Secuencia de sujeción no definida", 2)],
                    "Reemplazo de pines y verificación diaria de fixtura", "Mantenimiento preventivo de fixturas por golpes"),
    "Faltante": (("METHOD", "Sin poka-yoke de conteo de componentes", 6),
                 [("MANPOWER", "Rotación de operadores", 3), ("MEASUREMENT", "Inspección final por muestreo", 2)],
                 "Sensor de presencia con bloqueo de estación", "Poka-yoke de presencia en estaciones de ensamble"),
    "Rayón": (("METHOD", "Empaque sin separadores entre piezas", 5),
              [("MANPOWER", "Manejo manual sin guantes", 3), ("MACHINE", "Banda transportadora con rebaba", 2)],
              "Empaque con separadores y charola dedicada", "Estándar de empaque para piezas Clase A"),
    "Etiqueta": (("METHOD", "Etiqueta impresa antes de confirmar el lote", 5),
                 [("MACHINE", "Impresora sin lectura de verificación", 4), ("MANPOWER", "Captura manual del número de parte", 2)],
                 "Impresión de etiqueta ligada al escaneo del lote", "Trazabilidad por escaneo en todas las líneas"),
    "Torque": (("MACHINE", "Atornillador sin control de torque/ángulo", 7),
               [("METHOD", "Secuencia de apriete no definida", 3), ("MEASUREMENT", "Auditoría de torque mensual", 1)],
               "Atornillador con control de torque y rechazo automático", "Control de torque en todas las uniones críticas"),
    "Contaminación": (("METHOD", "Lavado sin control de concentración", 6),
                      [("MATERIAL", "Aceite de corte degradado", 3), ("MACHINE", "Filtro de lavadora saturado", 3)],
                      "Control de concentración y cambio de filtro por horas", "Prueba de limpieza (Millipore) por turno"),
}

# título, no. de parte, proceso, defecto, cliente (None = interno), origen, mercado, planta, severidad, reporte, hasta, ritmo
CASES = [
    ("Rebaba en tapa de transmisión 2210-F", "2210-F", "Maquinado CNC", "Rebaba", "Ford", "customer_complaint", "OEM", "PLT1", "medium", "2026-05-06", "D8", "fast"),
    ("Porosidad en carcasa de bomba 3120-A", "3120-A", "Inyección de aluminio", "Porosidad", "General Motors", "customer_complaint", "OEM", "PLT2", "high", "2026-05-14", "D8", "slow"),
    ("Etiqueta con número de parte incorrecto 8840-K", "8840-K", "Empaque", "Etiqueta", "Toyota", "customer_complaint", "OEM", "PLT1", "medium", "2026-05-22", "D8", "fast"),
    ("Dimensional fuera en barreno de soporte 4471-B", "4471-B", "Maquinado CNC", "Dimensional", None, "internal", None, "PLT1", "medium", "2026-05-28", "D8", "ok"),
    ("Fuga en tapón de radiador 6630-C", "6630-C", "Ensamble", "Fuga", "Stellantis", "customer_complaint", "OEM", "PLT2", "critical", "2026-06-04", "D8", "ok"),
    ("Rayón en moldura cromada 9015-M", "9015-M", "Empaque", "Rayón", "Honda", "customer_complaint", "OEM", "PLT1", "low", "2026-06-11", "D8", "fast"),
    ("Torque bajo en tornillo de base de motor 5102-T", "5102-T", "Ensamble", "Torque", "Ford", "customer_complaint", "OES", "PLT1", "high", "2026-06-19", "D8", "slow"),
    ("Contaminación en múltiple de admisión 7203-L", "7203-L", "Lavado", "Contaminación", None, "audit", None, "PLT2", "medium", "2026-06-25", "D8", "ok"),
    ("Grieta en brazo de suspensión 1180-S", "1180-S", "Inyección de aluminio", "Grieta", "Nissan", "customer_complaint", "OEM", "PLT2", "critical", "2026-07-03", "D8", "fast"),
    ("Faltante de clip en arnés de puerta 3390-H", "3390-H", "Ensamble", "Faltante", "Volkswagen", "customer_complaint", "OEM", "PLT1", "medium", "2026-07-10", "D8", "ok"),
    ("Dimensional en brida de escape 2650-E", "2650-E", "Maquinado CNC", "Dimensional", None, "supplier", None, "PLT1", "medium", "2026-07-17", "D8", "slow"),
    ("Porosidad en cabeza de cilindro 4020-H", "4020-H", "Inyección de aluminio", "Porosidad", "Toyota", "customer_complaint", "OEM", "PLT2", "high", "2026-07-24", "D8", "fast"),
    ("Rebaba en soporte de alternador 6211-A", "6211-A", "Maquinado CNC", "Rebaba", "General Motors", "customer_complaint", "AM", "PLT1", "low", "2026-08-05", "D8", "ok"),
    ("Etiqueta ilegible en caja de embarque 8850-K", "8850-K", "Empaque", "Etiqueta", None, "internal", None, "PLT1", "low", "2026-08-13", "D8", "fast"),
    ("Fuga en enfriador de aceite 5540-O", "5540-O", "Soldadura brazing", "Fuga", "Ford", "customer_complaint", "OEM", "PLT2", "critical", "2026-08-21", "D8", "slow"),
    ("Torque alto en sensor de temperatura 7710-T", "7710-T", "Ensamble", "Torque", "Tesla", "customer_complaint", "OEM", "PLT1", "medium", "2026-09-02", "D8", "ok"),
    ("Contaminación en riel de inyectores 3305-R", "3305-R", "Lavado", "Contaminación", "BMW", "customer_complaint", "OEM", "PLT2", "high", "2026-09-10", "D6", "slow"),
    ("Rayón en tapa de balancines 2290-V", "2290-V", "Maquinado CNC", "Rayón", None, "audit", None, "PLT1", "low", "2026-09-18", "D8", "fast"),
    ("Grieta en soporte de transmisión 6650-D", "6650-D", "Inyección de aluminio", "Grieta", "Stellantis", "customer_complaint", "OEM", "PLT2", "high", "2026-09-29", "D5", "slow"),
    ("Faltante de arandela en bomba de vacío 4180-P", "4180-P", "Ensamble", "Faltante", "Honda", "customer_complaint", "OES", "PLT1", "medium", "2026-10-07", "D4", "ok"),
    ("Dimensional en ranura de anillo 1145-N", "1145-N", "Maquinado CNC", "Dimensional", "Nissan", "customer_complaint", "OEM", "PLT1", "medium", "2026-10-15", "D3", "slow"),
    ("Fuga en válvula de purga 9920-V", "9920-V", "Ensamble", "Fuga", None, "internal", None, "PLT2", "high", "2026-10-21", "D2", "fast"),
    ("Porosidad en carcasa de termostato 5560-T", "5560-T", "Inyección de aluminio", "Porosidad", "General Motors", "customer_complaint", "OEM", "PLT2", "medium", "2026-10-26", "D3", "fast"),
]


class History(Demo):
    def build(self, spec) -> str:
        title, part, process, defect, customer, source, segment, plant, severity, reported, upto, pace = spec
        reported = date.fromisoformat(reported)
        days = PACE[pace]
        on = lambda code: min(reported + timedelta(days=days[CODES.index(code)]), date.today())  # noqa: E731
        root, others, corrective, systemic = DEFECTS[defect]
        external = customer is not None
        stop = CODES.index(upto)
        case = self.call("ing", "POST", "/cases", json={
            "plant_id": self.plants[plant], "title": title, "severity": severity, "case_type": "external" if external else "internal",
            "source_type": source, "customer_name": customer, "product_name": title.split(" en ")[-1].rsplit(" ", 1)[0].capitalize(),
            "part_number": part, "process_name": process, "market_segment": segment, "main_defect": defect,
            "report_date": reported.isoformat(), "target_close_date": (reported + timedelta(days=14)).isoformat()})
        cid = case["id"]
        who = f"{customer}" if external else "Planta"
        self.content(cid, "D0", emergency_response="Retención del inventario sospechoso y revisión 100% antes de embarque.",
                     justification=f"{'Reclamación de ' + customer if external else 'Hallazgo interno'}: defecto «{defect.lower()}» en {part}.")
        self.approve(cid, "D0")
        self.team(cid)
        case = self.approve(cid, "D1")
        qty = 6 + len(title) % 15
        self.call("ing", "PATCH", f"/cases/{cid}", json={
            "version": case["version"], "problem_description": f"{title}: defecto «{defect.lower()}» detectado por {who.lower() if not external else who}.",
            "defect_date": reported.isoformat(), "detected_quantity": qty, "affected_quantity": qty * 60})
        if stop < 2:
            return cid
        self.content(cid, "D2", what=f"{defect} en {part}", where=f"{'Recibo de ' + customer if external else 'Línea de ' + process}",
                     when=f"{reported:%d-%m-%Y}", who=f"{'Inspección de ' + customer if external else 'Auditor de producto'}",
                     how_detected="Inspección visual y verificación dimensional")
        self.approve(cid, "D2")
        if stop < 3:
            return cid

        act = self.call("ing", "POST", f"/cases/{cid}/containment", json={
            "description": "Revisión 100% del inventario en planta, almacén y tránsito", "location": "Almacén PT y tránsito",
            "responsible_user_id": self.uid["produccion"], "due_date": (reported + timedelta(days=1)).isoformat(),
            "quantity_checked": qty * 60, "quantity_rejected": qty})[0]
        self.call("prod", "PATCH", f"/containment/{act['id']}", json={"status": "implemented", "evidence_notes": "Registro de inspección 100%"})
        self.call("mgr", "PATCH", f"/containment/{act['id']}", json={"status": "verified"})
        alert = self.call("ing", "POST", f"/cases/{cid}/alerts", json={})
        self.call("ing", "PATCH", f"/alerts/{alert['id']}", json={
            "when_happened": f"{reported:%d-%m-%Y}", "where_happened": f"{process}", "who_is_affected": who,
            "how_detected": "Inspección visual", "affected_quantity": qty * 60,
            "containment_summary": "Retención y revisión 100% del inventario"})
        self.call("mgr", "POST", f"/alerts/{alert['id']}/issue")
        half = qty * 30
        self.contain(cid, [(f"L-{part}-A", "Almacén PT", half, qty // 2, "rework"), (f"L-{part}-B", "Tránsito", half, qty - qty // 2, "scrap")],
                     f"{qty * 60} piezas revisadas; {qty} rechazadas. Sin escapes adicionales.")
        self.approve(cid, "D3")
        if stop < 4:
            return cid

        for cat, text, inc in [root, *others]:
            self.call("ing", "POST", f"/cases/{cid}/causes", json={"category_id": self.cats[cat], "potential_cause": text, "incidence_count": inc})
        listed = {x["potential_cause"]: x["id"] for x in self.call("ing", "GET", f"/cases/{cid}/causes")}
        self.call("ing", "POST", f"/causes/{listed[root[1]]}/validations", json={
            "decision": "root_cause", "documented_answer": "yes", "followed_process_answer": "no",
            "verification_method": "Reproducción del defecto en piso", "evidence_summary": "El defecto aparece y desaparece con la causa",
            "rationale": "Explica la ocurrencia y la distribución del defecto"})
        for _, text, _ in others:
            self.call("ing", "POST", f"/causes/{listed[text]}/validations", json={
                "decision": "not_root_cause", "documented_answer": "yes", "followed_process_answer": "yes",
                "verification_method": "Revisión de registros y prueba comparativa", "evidence_summary": "Sin diferencia en el resultado",
                "rationale": "No explica el defecto"})
        self.content(cid, "D4", occurrence_cause=f"{root[1]}.", escape_point="La inspección no cubría la característica afectada.")
        self.approve(cid, "D4")
        if stop < 5:
            return cid

        action = next(x for x in self.call("ing", "POST", f"/cases/{cid}/actions", json={
            "action_type": "corrective", "cause_id": listed[root[1]], "description": corrective,
            "responsible_user_id": self.uid["mantenimiento"], "due_date": on("D6").isoformat()}) if x["description"] == corrective)
        start, end = on("D5"), on("D6")
        period = max((end - start).days, 1)
        start = end - timedelta(days=period)
        eff = self.call("ing", "POST", f"/cases/{cid}/criteria", json={
            "description": f"Cero piezas con {defect.lower()} en {period} días con producción", "metric_name": f"Piezas con {defect.lower()}",
            "defect_unit": "piezas", "denominator_type": "units_produced", "threshold_type": "max_defects", "threshold_value": 0,
            "min_period_days": period, "min_denominator": 1000})
        self.call("mgr", "POST", f"/criteria/{eff['criteria'][0]['id']}/approve")
        self.content(cid, "D5", verification_plan="Corrida de validación con inspección 100% de la característica.")
        self.approve(cid, "D5")
        if stop < 6:
            return cid

        self.call("mant", "POST", f"/actions/{action['id']}/start")
        self.call("mant", "POST", f"/actions/{action['id']}/submit", json={"implementation_evidence": f"OT de implementación: {corrective}"})
        self.call("mgr", "POST", f"/actions/{action['id']}/approve", json={"comment": "Verificado en piso"})
        produced = 1500 + 400 * period
        check = self.call("ing", "POST", f"/actions/{action['id']}/checks", json={
            "criterion_id": eff["criteria"][0]["id"], "period_start": start.isoformat(), "period_end": end.isoformat(),
            "denominator_quantity": produced, "defect_quantity": 0, "days_without_production": 0, "data_notes": "Conteo del MES"})
        pending = next(x for x in check["checks"] if x["result"] == "pending")
        self.call("ing", "POST", f"/checks/{pending['id']}/decide", json={"result": "effective", "rationale": f"0 defectos en {produced} piezas"})
        self.content(cid, "D6", validation_summary=f"Acción implementada y eficaz: 0 defectos en {produced} piezas.")
        self.approve(cid, "D6")
        if stop < 7:
            return cid

        rows = self.call("ing", "POST", f"/cases/{cid}/actions", json={
            "action_type": "systemic", "description": systemic, "responsible_user_id": self.uid["ingenieria"], "due_date": on("D7").isoformat()})
        sysid = next(x["id"] for x in rows if x["action_type"] == "systemic")
        self.call("ing", "POST", f"/actions/{sysid}/submit", json={"implementation_evidence": "Estándar actualizado y publicado"})
        self.call("mgr", "POST", f"/actions/{sysid}/approve", json={})
        for kind, ref in (("pfmea", f"PFMEA-{part}"), ("control_plan", f"PC-{part}"), ("training", f"CAP-{part}")):
            upd = self.call("ing", "POST", f"/cases/{cid}/system-updates", json={"update_type": kind, "document_reference": ref})
            self.call("ing", "PATCH", f"/system-updates/{upd[-1]['id']}", json={"status": "completed", "completed_on": on("D7").isoformat(),
                                                                                 "evidence_notes": "Documento actualizado"})
        self.content(cid, "D7", horizontal_deployment=f"Revisado en las líneas de {process} de PLT1 y PLT2.")
        self.approve(cid, "D7")
        if stop < 8:
            return cid

        kind = "crack" if defect == "Grieta" else "burr"
        nok = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración NOK"},
                        files={"file": ("nok.png", photo(False, kind), "image/png")})
        good = self.call("ing", "POST", f"/cases/{cid}/attachments", data={"purpose": "photo", "description": "Ilustración OK"},
                         files={"file": ("ok.png", photo(True, kind), "image/png")})
        lesson = self.call("ing", "POST", f"/cases/{cid}/lessons")
        self.call("ing", "PATCH", f"/lessons/{lesson['id']}", json={
            "before_summary": f"{qty} piezas con {defect.lower()}; causa: {root[1].lower()}.",
            "after_summary": f"0 defectos en {produced} piezas tras: {corrective.lower()}.",
            "training_summary": "Capacitación al personal de la línea sobre el cambio.",
            "situations": [f"Procesos de {process.lower()}", f"Defectos de tipo {defect.lower()}"]})
        self.call("ing", "PUT", f"/lessons/{lesson['id']}/photos", json={"photos": [
            {"attachment_id": nok["id"], "kind": "before", "caption": "Ilustración: antes"},
            {"attachment_id": good["id"], "kind": "after", "caption": "Ilustración: después"}]})
        self.call("ing", "POST", f"/lessons/{lesson['id']}/submit")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/review", json={"decision": "approve", "comment": "Conforme"})
        self.content(cid, "D8", closure_summary="Causa raíz eliminada, eficacia demostrada y sistema actualizado.",
                     team_recognition="Reconocimiento al equipo.")
        self.approve(cid, "D8", "Caso cerrado")
        self.call("mgr", "POST", f"/lessons/{lesson['id']}/publish")
        return cid

    @staticmethod
    def backdate(conn, cid: str, spec):
        """Lleva fechas de reporte, aprobación, contención y cierre a la línea de tiempo simulada."""
        reported, upto, pace = date.fromisoformat(spec[9]), spec[10], spec[11]
        tz = ZoneInfo("America/Mexico_City")
        at = lambda d, h: datetime.combine(min(d, date.today()), time(h), tz)  # noqa: E731
        for i, code in enumerate(CODES[:CODES.index(upto) + 1]):
            day = reported + timedelta(days=PACE[pace][i])
            conn.execute("""update case_disciplines set submitted_at = %s, approved_at = %s
                            where case_id = %s and discipline_code = %s and status = 'approved'""",
                         (at(day, 12), at(day, 17), cid, code))
        d3 = reported + timedelta(days=PACE[pace][3])
        conn.execute("update case_containment set started_at = %s, ended_at = case when ended_at is null then null else %s end where case_id = %s",
                     (at(reported, 9), at(d3, 15), cid))
        closed = at(reported + timedelta(days=PACE[pace][8]), 17) if upto == "D8" else None
        conn.execute("update cases_8d set created_at = %s, closed_at = coalesce(%s, closed_at), is_demo = true where id = %s",
                     (at(reported, 8), closed, cid))


def main() -> int:
    password = setting("DEMO_PASSWORD")
    if not password:
        print("Falta DEMO_PASSWORD en .env", file=sys.stderr)
        return 1
    app = create_app(database_url())
    with TestClient(app):
        demo = History(app, password)
        existing = {c["title"] for c in demo.call("admin", "GET", "/cases")}
        made = 0
        for spec in CASES:
            if spec[0] in existing:
                continue
            cid = demo.build(spec)
            with app.state.db.transaction() as conn:
                History.backdate(conn, cid, spec)
            made += 1
            print(f"{spec[9]} {spec[10]:>3} {spec[0]}")
    print(f"Casos de historial creados: {made}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
