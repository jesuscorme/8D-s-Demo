"""Generación del PDF de alerta de calidad (servicio separado de la lógica de negocio).

Solo dibuja los datos que recibe; no consulta la base de datos ni decide nada.
"""
import io
from datetime import datetime

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Table, TableStyle

TEMPLATE_VERSION = "quality_alert/1.0"
NAVY = colors.HexColor("#0B1F3A")
BLUE = colors.HexColor("#1D6FE0")
RED = colors.HexColor("#C62828")
GREEN = colors.HexColor("#2E7D32")
GREY = colors.HexColor("#5B6676")
LINE = colors.HexColor("#D5DCE6")

_LABEL = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, textColor=GREY, leading=10)
_VALUE = ParagraphStyle("value", fontName="Helvetica", fontSize=9.5, leading=12)


def _p(text, style=_VALUE) -> Paragraph:
    safe = (str(text) if text not in (None, "") else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe.replace("\n", "<br/>"), style)


def _qr(url: str, size: float) -> Drawing:
    widget = QrCodeWidget(url, barLevel="M")
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    return drawing


def _photo_box(c, x, y, w, h, kind: str, image: bytes | None) -> None:
    color = RED if kind == "nok" else GREEN
    c.setStrokeColor(color)
    c.setLineWidth(2)
    c.rect(x, y, w, h)
    c.setFillColor(color)
    c.rect(x, y + h - 6 * mm, w, 6 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 2 * mm, y + h - 4.2 * mm, "NOK — CONDICIÓN INCORRECTA" if kind == "nok" else "OK — CONDICIÓN CORRECTA")
    inner_h = h - 8 * mm
    if image:
        img = ImageReader(io.BytesIO(image))
        iw, ih = img.getSize()
        scale = min((w - 4 * mm) / iw, (inner_h - 2 * mm) / ih)
        dw, dh = iw * scale, ih * scale
        c.drawImage(img, x + (w - dw) / 2, y + 1 * mm + (inner_h - dh) / 2, dw, dh, preserveAspectRatio=True)
    else:
        c.setFillColor(GREY)
        c.setFont("Helvetica-Oblique", 9)
        c.drawCentredString(x + w / 2, y + inner_h / 2, "Sin fotografía adjunta")


def render(alert: dict, case: dict, organization: str, plant: str, photos: list[tuple[str, bytes]],
           issued_by: str, responsible: str | None, issued_at: datetime, url: str, logo: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    from reportlab.pdfgen.canvas import Canvas
    c = Canvas(buf, pagesize=letter, pageCompression=1)
    folio = f"QA-{alert['alert_number']:04d}"
    c.setTitle(f"Alerta de calidad {folio} rev. {alert['revision']}")
    c.setAuthor(organization)
    c.setSubject(f"Caso {case['folio']}")
    width, height = letter
    m = 14 * mm

    # Encabezado
    c.setFillColor(NAVY)
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=1, stroke=0)
    from app.pdf_reports import draw_logo  # misma rutina de logo que el resto de documentos
    x = m + (draw_logo(c, logo, m, height - 27 * mm, 24 * mm) and 28 * mm)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, height - 10 * mm, organization.upper())
    c.setFont("Helvetica", 8.5)
    c.drawString(x, height - 14.5 * mm, f"Planta: {plant}")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, height - 24 * mm, "ALERTA DE CALIDAD")
    kind = "EXTERNA" if alert["failure_type"] == "external" else "INTERNA"
    c.setFillColor(RED if kind == "EXTERNA" else BLUE)
    c.roundRect(width - m - 40 * mm, height - 25 * mm, 40 * mm, 9 * mm, 2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(width - m - 20 * mm, height - 22 * mm, f"FALLA {kind}")
    c.setFont("Helvetica", 8.5)
    c.drawRightString(width - m, height - 10 * mm, f"{folio}  ·  Rev. {alert['revision']}")
    c.drawRightString(width - m, height - 14.5 * mm, f"Caso 8D: {case['folio']}")

    # Título
    y = height - 38 * mm
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 13)
    title = Paragraph(alert["title"].replace("&", "&amp;").replace("<", "&lt;"),
                      ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY))
    _, th = title.wrap(width - 2 * m, 30 * mm)
    title.drawOn(c, m, y - th + 4 * mm)
    y -= th + 2 * mm

    # 5W
    qty = alert.get("affected_quantity")
    rows = [
        [_p("¿QUÉ PASÓ?", _LABEL), _p(alert.get("what_happened"))],
        [_p("¿CUÁNDO?", _LABEL), _p(alert.get("when_happened"))],
        [_p("¿DÓNDE?", _LABEL), _p(alert.get("where_happened"))],
        [_p("¿QUIÉN / A QUIÉN AFECTA?", _LABEL), _p(alert.get("who_is_affected"))],
        [_p("¿CÓMO SE DETECTÓ?", _LABEL), _p(alert.get("how_detected"))],
        [_p("ÁREAS AFECTADAS", _LABEL), _p(alert.get("affected_areas"))],
        [_p("CANTIDAD AFECTADA", _LABEL), _p(f"{qty:,} piezas" if qty is not None else None)],
        [_p("NÚMERO DE PARTE / PRODUCTO", _LABEL),
         _p(" · ".join(x for x in (case.get("part_number"), case.get("product_name")) if x) or None)],
        [_p("CONTENCIÓN (D3)", _LABEL), _p(alert.get("containment_summary"))],
    ]
    table = Table(rows, colWidths=[48 * mm, width - 2 * m - 48 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F6FA")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    _, tbl_h = table.wrap(width - 2 * m, y)
    table.drawOn(c, m, y - tbl_h)
    y -= tbl_h + 6 * mm

    # Fotos NOK / OK
    footer_h = 34 * mm
    photo_h = max(min(y - footer_h - 6 * mm, 70 * mm), 35 * mm)
    nok = next((b for k, b in photos if k == "nok"), None)
    ok = next((b for k, b in photos if k == "ok"), None)
    box_w = (width - 2 * m - 6 * mm) / 2
    _photo_box(c, m, y - photo_h, box_w, photo_h, "nok", nok)
    _photo_box(c, m + box_w + 6 * mm, y - photo_h, box_w, photo_h, "ok", ok)

    # Pie: emisión, responsable y QR
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(m, footer_h, width - m, footer_h)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m, footer_h - 6 * mm, "EMITIDA POR")
    c.drawString(m + 62 * mm, footer_h - 6 * mm, "RESPONSABLE")
    c.drawString(m, footer_h - 17 * mm, "FECHA DE EMISIÓN")
    c.drawString(m + 62 * mm, footer_h - 17 * mm, "REVISIÓN")
    c.setFont("Helvetica", 9)
    c.drawString(m, footer_h - 10.5 * mm, issued_by)
    c.drawString(m + 62 * mm, footer_h - 10.5 * mm, responsible or "—")
    c.drawString(m, footer_h - 21.5 * mm, issued_at.strftime("%Y-%m-%d %H:%M %Z").strip())
    c.drawString(m + 62 * mm, footer_h - 21.5 * mm, f"{alert['revision']}" + (
        f" — {alert['revision_reason']}"[:60] if alert.get("revision_reason") else ""))
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(GREY)
    c.drawString(m, 9 * mm, f"Documento controlado ({TEMPLATE_VERSION}). Su huella SHA-256 queda registrada en 8D PRO.")
    c.drawString(m, 5.5 * mm, "Una revisión nueva sustituye a esta; consulte siempre la revisión vigente.")
    qr_size = 26 * mm
    renderPDF.draw(_qr(url, qr_size), c, width - m - qr_size, 5 * mm)
    c.setFont("Helvetica", 6.5)
    c.drawRightString(width - m - qr_size - 2 * mm, 8 * mm + 3 * mm, "Escanea para consultar")
    c.drawRightString(width - m - qr_size - 2 * mm, 8 * mm, "(requiere iniciar sesión)")
    c.showPage()
    c.save()
    return buf.getvalue()
