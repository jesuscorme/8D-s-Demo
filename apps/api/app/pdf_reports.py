"""PDF de expediente 8D (completo y avance), reporte de auditoría y lección aprendida.

Servicio de presentación: recibe datos ya autorizados y consultados; no accede a la base de datos.
Plantillas versionadas en TEMPLATES (el número queda registrado en cada documento emitido).
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

TEMPLATES = {"8d_full": "8d_full/1.0", "8d_progress": "8d_progress/1.0", "audit_report": "audit_report/1.0",
             "lesson_learned": "lesson_learned/1.0"}
NAVY = colors.HexColor("#0B1F3A")
BLUE = colors.HexColor("#1D6FE0")
GREY = colors.HexColor("#5B6676")
LINE = colors.HexColor("#D5DCE6")
SOFT = colors.HexColor("#F3F6FA")
GREEN = colors.HexColor("#1F8A4C")
RED = colors.HexColor("#C62828")
AMBER = colors.HexColor("#B26A00")

H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=NAVY, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=NAVY, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=11.5)
SMALL = ParagraphStyle("small", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=GREY)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10)
HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=GREY)

STATUS_ES = {
    "not_started": "Sin iniciar", "in_progress": "En curso", "pending_review": "En revisión", "approved": "Aprobada",
    "draft": "Borrador", "open": "Abierto", "closed": "Cerrado", "cancelled": "Cancelado", "verified": "Verificada",
    "implemented": "Implementada", "pending_approval": "Pendiente de aprobación", "ineffective": "No eficaz",
    "pending": "Pendiente", "investigating": "En investigación", "root_cause": "Causa raíz",
    "not_root_cause": "No es causa raíz", "needs_more_investigation": "Requiere más investigación",
    "effective": "Eficaz", "insufficient_data": "Datos insuficientes", "issued": "Vigente", "superseded": "Sustituida",
    "planned": "Planificada", "completed": "Completada", "in_review": "En revisión", "published": "Publicada",
    "retired": "Retirada",
}


def esc(value) -> str:
    text = "—" if value is None or value == "" or value == [] else (", ".join(value) if isinstance(value, list) else str(value))
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def p(value, style=BODY) -> Paragraph:
    return Paragraph(esc(value), style)


def st(value) -> str:
    return STATUS_ES.get(value, value or "—")


def fdate(value, with_time=False) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M") if with_time else value.strftime("%Y-%m-%d")
    return str(value)


def table(header: list[str], rows: list[list], widths: list[float] | None = None) -> Table:
    data = [[Paragraph(esc(h), HEAD) for h in header]] + [[c if isinstance(c, (Paragraph, Image)) else p(c, CELL) for c in r]
                                                       for r in rows]
    if len(data) == 1:
        data.append([p("Sin registros", SMALL)] + [""] * (len(header) - 1))
    # splitInRow: una fila con texto largo puede continuar en la página siguiente.
    t = Table(data, colWidths=widths, repeatRows=1, splitInRow=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def kv(pairs: list[tuple[str, object]], label_width=45 * mm, total=188 * mm) -> Table:
    t = Table([[Paragraph(esc(k), HEAD), p(v, CELL)] for k, v in pairs], colWidths=[label_width, total - label_width],
              splitInRow=1)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                           ("BACKGROUND", (0, 0), (0, -1), SOFT), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def image(content: bytes, max_w: float, max_h: float) -> Image | None:
    try:
        reader = ImageReader(io.BytesIO(content))
        w, h = reader.getSize()
    except Exception:  # imagen dañada: se omite sin romper el documento
        return None
    scale = min(max_w / w, max_h / h)
    return Image(io.BytesIO(content), width=w * scale, height=h * scale)


def draw_logo(c, logo: bytes | None, x: float, y: float, size: float) -> bool:
    """Logo de la organización en un recuadro blanco; devuelve False si no hay logo o no se puede leer."""
    if not logo:
        return False
    try:
        reader = ImageReader(io.BytesIO(logo))
        w, h = reader.getSize()
    except Exception:
        return False
    c.saveState()
    c.setFillColor(colors.white)
    c.roundRect(x, y, size, size, 1.5 * mm, fill=1, stroke=0)
    pad = 1.2 * mm
    scale = min((size - 2 * pad) / w, (size - 2 * pad) / h)
    c.drawImage(reader, x + (size - w * scale) / 2, y + (size - h * scale) / 2, w * scale, h * scale, mask="auto")
    c.restoreState()
    return True


def _numbered_canvas(meta: dict):
    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total: int):
            width, height = letter
            self.setFillColor(NAVY)
            self.rect(0, height - 18 * mm, width, 18 * mm, fill=1, stroke=0)
            x = 14 * mm + (draw_logo(self, meta.get("logo"), 14 * mm, height - 16 * mm, 14 * mm) and 17 * mm)
            self.setFillColor(colors.white)
            self.setFont("Helvetica-Bold", 10)
            self.drawString(x, height - 8 * mm, f"8D PRO · {meta['organization']}")
            self.setFont("Helvetica", 8.5)
            self.drawString(x, height - 13 * mm, meta["title"])
            self.drawRightString(width - 14 * mm, height - 8 * mm, f"{meta['folio']} · Rev. {meta['revision']}")
            self.drawRightString(width - 14 * mm, height - 13 * mm, meta.get("status_label", ""))
            self.setFillColor(GREY)
            self.setFont("Helvetica", 7)
            self.drawString(14 * mm, 8 * mm, f"Plantilla {meta['template_version']} · Emitido {meta['issued_at']} por "
                                             f"{meta['issued_by']} · Huella SHA-256 registrada en 8D PRO (no es firma electrónica)")
            self.drawRightString(width - 14 * mm, 8 * mm, f"Página {self._pageNumber} de {total}")
            if meta.get("watermark"):
                self.saveState()
                self.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.12))
                self.setFont("Helvetica-Bold", 48)
                self.translate(width / 2, height / 2)
                self.rotate(35)
                self.drawCentredString(0, 0, meta["watermark"])
                self.restoreState()
    return NumberedCanvas


def build(story: list, meta: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=24 * mm,
                            bottomMargin=16 * mm, title=f"{meta['title']} {meta['folio']} rev. {meta['revision']}",
                            author=meta["organization"], subject=meta.get("subject", ""))
    doc.build(story, canvasmaker=_numbered_canvas(meta))
    return buf.getvalue()


# ---- Expediente 8D -----------------------------------------------------------------------------

def _discipline_block(d: dict) -> list:
    out = [p(f"Estado: {st(d['status'])}" + (f" · aprobada por {d['approved_by_name']} el {fdate(d['approved_at'], True)}"
                                             if d.get("approved_at") else ""), SMALL)]
    content = {k: v for k, v in (d.get("content") or {}).items() if v}
    labels = d.get("labels", {})
    if content:
        out.append(kv([(labels.get(k, k), "\n".join(v) if isinstance(v, list) else v) for k, v in content.items()]))
    pending = [r["label"] for r in d["requirements"] if not r["met"]]
    if pending and d["status"] != "approved":
        out.append(p("Pendiente: " + "; ".join(pending), SMALL))
    return out


def case_report(b: dict, meta: dict, full: bool) -> bytes:
    c = b["case"]
    story: list = [Paragraph(esc(c["title"]), H1),
                   p(f"{c['folio']} · {c['plant']} · Estado del caso: {st(c['status'])} · Severidad: {c['severity_label']}", SMALL),
                   Spacer(0, 4)]
    approved = sum(1 for d in b["workflow"] if d["status"] == "approved")
    story.append(kv([
        ("Cliente", c["customer_name"]), ("Producto / parte", " · ".join(x for x in (c["product_name"], c["part_number"]) if x) or None),
        ("Proceso / lote", " · ".join(x for x in (c["process_name"], c["lot_number"]) if x) or None),
        ("Fecha de detección", fdate(c["defect_date"])), ("Cantidad detectada / afectada",
                                                           f"{c['detected_quantity'] if c['detected_quantity'] is not None else '—'} / "
                                                           f"{c['affected_quantity'] if c['affected_quantity'] is not None else '—'}"),
        ("Responsable", c["owner_name"]), ("Fecha objetivo de cierre", fdate(c.get("target_close_date"))),
        ("Avance", f"{approved} de 9 disciplinas aprobadas"), ("Abierto", f"{fdate(c['created_at'], True)} por {c['opened_by_name']}"),
        ("Cerrado", fdate(c.get("closed_at"), True)),
    ]))
    story.append(Paragraph("Estado por disciplina", H2))
    story.append(table(["Disciplina", "Estado", "Pendientes", "Aprobación"],
                       [[f"{d['code']} — {d['name']}", st(d["status"]),
                         "; ".join(r["label"] for r in d["requirements"] if not r["met"]) if d["status"] != "approved" else "—",
                         f"{d['approved_by_name']} · {fdate(d['approved_at'])}" if d.get("approved_at") else "—"]
                        for d in b["workflow"]], [52 * mm, 24 * mm, 76 * mm, 36 * mm]))
    if not full:
        story.append(Paragraph("Acciones abiertas", H2))
        open_rows = [[x["kind"], x["description"], x["responsible_name"], fdate(x["due_date"]), st(x["status"]),
                      "VENCIDA" if x["overdue"] else ""] for x in b["open_items"]]
        story.append(table(["Tipo", "Acción", "Responsable", "Vence", "Estado", ""], open_rows,
                           [24 * mm, 74 * mm, 32 * mm, 20 * mm, 24 * mm, 14 * mm]))
        story.append(Paragraph("Últimos eventos", H2))
        story.append(table(["Fecha", "Usuario", "Evento"], [[fdate(e["occurred_at"], True), e["actor_name"], e["label"]]
                                                           for e in b["audit"][:15]], [34 * mm, 50 * mm, 104 * mm]))
        return build(story, meta)

    disc = {d["code"]: d for d in b["workflow"]}

    def section(code: str, extra: list | None = None):
        d = disc[code]
        block = [Paragraph(f"{code} — {esc(d['name'])}", H2), *_discipline_block(d), *(extra or [])]
        story.append(KeepTogether(block[:3]))
        story.extend(block[3:])

    section("D0")
    section("D1", [table(["Integrante", "Rol", "Correo"], [[m["display_name"], m["role_label"], m["email"]] for m in b["team"]],
                         [70 * mm, 40 * mm, 78 * mm])])
    section("D2", [kv([("Descripción del problema", c["problem_description"])])])
    alert_rows = [[a["folio"], a["revision"], st(a["status"]), a["title"], fdate(a["issued_at"], True),
                   (a["sha256_hex"] or "")[:16]] for a in b["alerts"]]
    photos = []
    for kind, content in b.get("photos", []):
        img = image(content, 85 * mm, 60 * mm)
        if img:
            photos.append([Paragraph("NOK — condición incorrecta" if kind == "nok" else "OK — condición correcta", HEAD), img])
    section("D3", [table(["Acción de contención", "Responsable", "Vence", "Rev./Rech.", "Evidencia", "Estado"],
                         [[a["description"], a["responsible_name"], fdate(a["due_date"]),
                           f"{a['quantity_checked'] if a['quantity_checked'] is not None else '—'}/"
                           f"{a['quantity_rejected'] if a['quantity_rejected'] is not None else '—'}",
                           a["evidence_notes"], st(a["status"])] for a in b["containment"]],
                         [54 * mm, 30 * mm, 18 * mm, 18 * mm, 46 * mm, 22 * mm]),
                   Spacer(0, 4), table(["Alerta", "Rev.", "Estado", "Título", "Emitida", "SHA-256"], alert_rows,
                                       [20 * mm, 10 * mm, 20 * mm, 72 * mm, 32 * mm, 34 * mm])]
            + ([Spacer(0, 4), Table([[x[0] for x in photos], [x[1] for x in photos]])] if photos else []))
    section("D4", [table(["Categoría", "Causa potencial", "Doc./Siguió", "Método · Evidencia · Justificación", "Estado"],
                         [[x["category_name"], x["potential_cause"], f"{x['documented']}/{x['followed']}",
                           " · ".join(v for v in (x["verification_method"], x["evidence_summary"], x["rationale"]) if v) or None,
                           st(x["investigation_status"])] for x in b["causes"]],
                         [26 * mm, 46 * mm, 18 * mm, 72 * mm, 26 * mm])])
    action_header = ["Tipo", "Acción", "Causa", "Responsable", "Vence", "Evidencia", "Estado"]
    widths = [18 * mm, 46 * mm, 30 * mm, 24 * mm, 16 * mm, 32 * mm, 22 * mm]

    def action_rows(types):
        return [[x["type_label"], x["description"], x["cause_text"], x["responsible_name"], fdate(x["due_date"]),
                 x["implementation_evidence"] or (f"Excepción: {x['evidence_exception']}" if x["evidence_exception"] else None),
                 st(x["status"])] for x in b["actions"] if x["action_type"] in types]
    section("D5", [table(action_header, action_rows({"corrective"}), widths), Spacer(0, 4),
                   table(["Criterio de eficacia", "Indicador", "Límite", "Periodo mín.", "Estado"],
                         [[k["description"], f"{k['metric_name']} / {k['denominator']}", k["threshold_label"],
                           f"{k['min_period_days']} días, mín. {k['min_denominator']}", st(k["status"])] for k in b["criteria"]],
                         [60 * mm, 50 * mm, 26 * mm, 30 * mm, 22 * mm])])
    section("D6", [table(["Acción", "Periodo", "Defectos / denominador", "Regla", "Resultado", "Justificación"],
                         [[e["action_description"], f"{fdate(e['period_start'])} a {fdate(e['period_end'])}",
                           f"{e['defect_quantity'] if e['defect_quantity'] is not None else 'sin dato'} / "
                           f"{e['denominator_quantity'] if e['denominator_quantity'] is not None else 'sin dato'}",
                           st(e["computed_result"]), st(e["result"]), e["rationale"]] for e in b["checks"]],
                         [44 * mm, 30 * mm, 28 * mm, 22 * mm, 22 * mm, 42 * mm])])
    section("D7", [table(action_header, action_rows({"preventive", "systemic"}), widths), Spacer(0, 4),
                   table(["Documento del sistema", "Referencia", "Estado", "Completado", "Evidencia"],
                         [[u["type_label"], u["document_reference"], st(u["status"]), fdate(u["completed_on"]), u["evidence_notes"]]
                          for u in b["system_updates"]], [36 * mm, 46 * mm, 24 * mm, 22 * mm, 60 * mm])])
    section("D8", [table(["Lección", "Rev.", "Título", "Estado"], [[l["folio"], l["revision"], l["title"], st(l["status"])]
                                                                for l in b["lessons"]], [24 * mm, 12 * mm, 120 * mm, 32 * mm])])
    story.append(Paragraph("Documentos emitidos del caso", H2))
    story.append(table(["Documento", "Rev.", "Estado", "Emitido", "SHA-256"],
                       [[d["file_name"], d["revision"], st(d["status"]), fdate(d["generated_at"], True), d["sha256_hex"]]
                        for d in b["documents"]], [50 * mm, 10 * mm, 20 * mm, 30 * mm, 78 * mm]))
    return build(story, meta)


def audit_report(b: dict, meta: dict) -> bytes:
    c = b["case"]
    story: list = [Paragraph(f"Reporte de auditoría — {esc(c['title'])}", H1),
                   p(f"{c['folio']} · {len(b['audit'])} evento(s). La bitácora es de solo inserción.", SMALL), Spacer(0, 4)]
    rows = []
    for e in b["audit"]:
        changes = "; ".join(f"{k}: {e['old'].get(k, '—')} » {e['new'].get(k, '—')}" for k in e["keys"][:6])
        rows.append([fdate(e["occurred_at"], True), e["actor_name"], e["label"], changes or None, (e.get("request_id") or "")[:12]])
    story.append(table(["Fecha", "Usuario", "Evento", "Cambios", "Solicitud"], rows,
                       [28 * mm, 30 * mm, 34 * mm, 76 * mm, 20 * mm]))
    story.append(Paragraph("Documentos y huellas", H2))
    story.append(table(["Documento", "Rev.", "Estado", "SHA-256"], [[d["file_name"], d["revision"], st(d["status"]), d["sha256_hex"]]
                                                                for d in b["documents"]], [60 * mm, 12 * mm, 22 * mm, 94 * mm]))
    return build(story, meta)


def before_after(images: list[tuple[str, str | None, bytes]], before_text, after_text) -> list:
    """Dos columnas: ANTES (rojo) y DESPUÉS (verde), con texto, fotos y leyendas."""
    col = 92 * mm

    def cell(item):
        if item is None:
            return ""
        _, caption, content = item
        pic = image(content, col - 6 * mm, 62 * mm)
        return [pic, p(caption, SMALL)] if pic and caption else [pic] if pic else [p("Imagen no legible", SMALL)]

    before = [x for x in images if x[0] == "before"]
    after = [x for x in images if x[0] == "after"]
    header = ParagraphStyle("ba", parent=HEAD, textColor=colors.white, fontSize=9)
    rows = [[Paragraph("ANTES", header), Paragraph("DESPUÉS", header)], [p(before_text, CELL), p(after_text, CELL)]]
    # Una imagen por celda y un par por fila: el salto de página cae entre filas (reportlab no parte celdas con imágenes).
    for i in range(max(len(before), len(after))):
        rows.append([cell(before[i] if i < len(before) else None), cell(after[i] if i < len(after) else None)])
    if not images:
        rows.append([p("Sin fotografía", SMALL), p("Sin fotografía", SMALL)])
    t = Table(rows, colWidths=[col, col], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), RED), ("BACKGROUND", (1, 0), (1, 0), GREEN),
        ("LINEBEFORE", (0, 0), (0, -1), 1, RED), ("LINEAFTER", (0, 0), (0, -1), 1, RED),
        ("LINEAFTER", (1, 0), (1, -1), 1, GREEN), ("LINEBELOW", (0, -1), (0, -1), 1, RED),
        ("LINEBELOW", (1, -1), (1, -1), 1, GREEN),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [t]


def lesson_report(lesson: dict, meta: dict) -> bytes:
    story: list = [Paragraph(esc(lesson["title"]), H1),
                   p(f"{lesson['folio']} · Rev. {lesson['revision']} · {st(lesson['status'])} · Idioma: {lesson['language_code'].upper()}"
                     f" · Caso de origen {lesson['source_folio']}", SMALL), Spacer(0, 4)]
    story.append(kv([("Problema original", lesson["problem_summary"]), ("Causa raíz verificada", lesson["verified_root_cause"]),
                     ("Acciones implementadas", lesson["actions_summary"]), ("Resultados de eficacia", lesson["effectiveness_summary"])]))
    story.append(Paragraph("Antes y después", H2))
    story.extend(before_after(lesson.get("photo_images", []), lesson["before_summary"], lesson["after_summary"]))
    story.append(Spacer(0, 4))
    story.append(kv([("Documentos actualizados", lesson["documents_updated"]), ("Capacitación", lesson["training_summary"])]))
    story.append(Paragraph("Aplicabilidad", H2))
    story.append(kv([("Productos", lesson["products"]), ("Procesos", lesson["processes"]), ("Plantas", lesson["plant_codes"]),
                     ("Situaciones", lesson["situations"])]))
    story.append(Paragraph("Control documental", H2))
    story.append(kv([("Autor", f"{lesson['created_by_name']} · {fdate(lesson['created_at'], True)}"),
                     ("Revisó y aprobó", f"{lesson['reviewed_by_name']} · {fdate(lesson['reviewed_at'], True)}" if lesson.get("reviewed_at") else None),
                     ("Publicó", f"{lesson['published_by_name']} · {fdate(lesson['published_at'], True)}" if lesson.get("published_at") else None),
                     ("Motivo de la revisión", lesson.get("revision_reason"))]))
    if lesson.get("applications"):
        story.append(Paragraph("Reutilización en otros casos", H2))
        story.append(table(["Caso", "Rev. lección", "Resultado", "Evaluación"],
                           [[a["target_folio"], a["revision"], a["outcome_label"], a["evaluation"]] for a in lesson["applications"]],
                           [30 * mm, 20 * mm, 30 * mm, 108 * mm]))
    return build(story, meta)


def page_break() -> PageBreak:
    return PageBreak()
