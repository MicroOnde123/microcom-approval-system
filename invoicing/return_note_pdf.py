"""Logo-free return valuation PDF from detached immutable note snapshots only."""
import base64
import hashlib
import io
from decimal import Decimal
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape

import reportlab
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, override
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from .document_presentation import amount_words

RENDERER_VERSION = "return-note-a4-v2-rl5.1.0"
_FONT_LOCK = Lock()
_FONTS = Path(reportlab.__file__).parent / "fonts"
# SimpleDocTemplate's frame has 6pt internal padding on each side.
_CONTENT_WIDTH = A4[0] - 2 * 42 - 12


def _fonts():
    with _FONT_LOCK:
        if "InvoiceVera" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("InvoiceVera", str(_FONTS / "Vera.ttf")))
            pdfmetrics.registerFont(TTFont("InvoiceVeraBold", str(_FONTS / "VeraBd.ttf")))


def display_decimal(value, *, minimum_places=0):
    """Presentation only: trim redundant zeros, never round meaningful digits."""
    whole, separator, fraction = format(Decimal(value), "f").partition(".")
    fraction = fraction.rstrip("0").ljust(minimum_places, "0")
    return whole + ("." + fraction if fraction else "")


def render_pdf(snapshot, language):
    """Snapshot is a detached value dictionary, never an ORM document."""
    if language not in {"en", "fr"}:
        raise ValidationError(_("Choose English or French for the PDF."))
    _fonts()
    with override(language):
        regular = ParagraphStyle("invoice", fontName="InvoiceVera", fontSize=8.5, leading=12,
                                 textColor=colors.HexColor("#202020"), spaceAfter=4)
        bold = ParagraphStyle("invoice-bold", parent=regular, fontName="InvoiceVeraBold")
        title = ParagraphStyle("invoice-title", parent=bold, fontSize=15, leading=20, alignment=1, spaceAfter=10)
        right = ParagraphStyle("invoice-right", parent=regular, alignment=2)
        cell = ParagraphStyle("invoice-cell", parent=regular, spaceAfter=0)
        cell_right = ParagraphStyle("invoice-cell-right", parent=right, spaceAfter=0)
        cell_bold = ParagraphStyle("invoice-cell-bold", parent=bold, spaceAfter=0)

        def p(value, style=regular):
            value = str(value)
            # Fail rather than silently replacing unsupported characters by squares.
            glyphs = pdfmetrics.getFont(style.fontName).face.charToGlyph
            if any(ord(c) not in glyphs for c in value if not c.isspace()):
                raise ValidationError(_("The frozen material return note contains characters unsupported by the PDF font. Administrator review is required."))
            return Paragraph(escape(value).replace("\n", "<br/>"), style)

        branch = snapshot["branch"]
        branding = snapshot["branding"]
        story = []
        if branding["strategy"] == "embedded-content":
            if len(branding["content_base64"]) > 2800000:
                raise ValidationError(_("The frozen company logo is incomplete or damaged. Administrator review is required."))
            data = base64.b64decode(branding["content_base64"], validate=True)
            mime = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else (
                "image/jpeg" if data.startswith(b"\xff\xd8\xff") else (
                "image/webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else None))
            if (len(data) > 2 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != branding["sha256"]
                    or mime is None or mime != branding["content_type"]):
                raise ValidationError(_("The frozen company logo is incomplete or damaged. Administrator review is required."))
        # Retain frozen-asset integrity checks, but v2 deliberately draws no logo.
        metadata = Table([[p(_("Document number") + ": " + snapshot["number"], bold),
                           p(_("Issue date") + ": " + snapshot["issue_date"], right)]],
                         colWidths=[_CONTENT_WIDTH-200,200], hAlign="LEFT")
        metadata.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                                     ("LEFTPADDING",(0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0)]))
        story.extend([p(_("Material return note"), title), metadata,
                      p(_("Client: %(name)s") % {"name": branch["name"]}),
                      p(_("Original invoice") + ": " + snapshot["original"]["number"] + " — " + snapshot["original"]["issue_date"]),
                      p(_("Material request reference") + ": " + snapshot["request_reference"]),
                      p(_("Internal valuation of materials already returned to stock. No payment, refund or credit adjustment.")), Spacer(1, 9)])
        if branch.get("physical_address"):
            story.extend([p(_("Succursale physical address"), bold), p(branch["physical_address"]), Spacer(1, 6)])
        headings = [_('Material'), _('Returned quantity'), _('Original unit price'), _('Returned value')]
        numeric_heading = ParagraphStyle("numeric-heading", parent=cell_bold, alignment=2)
        rows = [[p(label, cell_bold if index == 0 else numeric_heading) for index,label in enumerate(headings)]]
        for line in snapshot["lines"]:
            unit = " (" + line["unit"] + ")" if line["unit"] else ""
            rows.append([[p(line["code"] + unit + " — " + line["description"], cell),
                          p(_("Return movement") + ": " + str(line["movement"]), cell)],
                         p(display_decimal(line["quantity"]), cell_right),
                         p(display_decimal(line["price"], minimum_places=2), cell_right),
                         p(display_decimal(line["total"], minimum_places=2), cell_right)])
        table = Table(rows, colWidths=[_CONTENT_WIDTH-240, 60, 90, 90], repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f1f1")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LINEBELOW", (0, 0), (-1, 0), .8, colors.HexColor("#505050")),
                                   ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#d8d8d8")),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        total_style = ParagraphStyle("invoice-total", parent=bold, alignment=2, fontSize=10, leading=15)
        stock_style = ParagraphStyle("invoice-stock", parent=bold, alignment=2)
        money = lambda value: display_decimal(value, minimum_places=2) + " " + snapshot["currency"]
        summary = [Spacer(1, 10),
                   p(_("Returned value on this note") + ": " + money(snapshot["total"]), total_style),
                   p(_("Original invoice value") + ": " + money(snapshot["original"]["total"])),
                   p(_("Cumulative returned value as of this note") + ": " + money(snapshot["cumulative_returned_value"])),
                   p(_("Adjusted net material value as of this note") + ": " + money(snapshot["adjusted_net_value"])),
                   p(_("Amount in words") + ": " + amount_words(snapshot["total"], snapshot["currency"], language, snapshot["amount_words_fr"])),
                   Spacer(1, 7), p(_("Operation reason"), bold), p(snapshot["reason"]),
                   Spacer(1, 12), p(_("Stock Department"), stock_style)]
        story.extend([table, KeepTogether(summary)])
        output = io.BytesIO()
        document = SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                                     topMargin=38, bottomMargin=48, title=snapshot["number"],
                                     author="",
                                     subject=(_FONTS / "bitstream-vera-license.txt").read_text(encoding="utf-8"))

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#d5dce3"))
            canvas.line(42, 37, A4[0] - 42, 37)
            canvas.setFont("InvoiceVera", 7)
            # Truncate footer only; the complete reference is printed in the body.
            canvas.drawString(42, 24, snapshot["number"][:60])
            canvas.drawRightString(A4[0] - 42, 24, _("Page") + " " + str(doc.page))
            canvas.restoreState()

        document.build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()
