"""Nonfinancial receipt PDF: immutable snapshots only, no ORM or network."""
import io
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
from datetime import datetime

from django.utils.translation import gettext as _, override
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from invoicing.return_note_pdf import _fonts

RENDERER_VERSION = "physical-return-receipt-v2"


def render_receipt(snapshot, language):
    if language not in {"en", "fr"}:
        raise ValueError("Unsupported language")
    _fonts()
    output = io.BytesIO()
    with override(language):
        style = ParagraphStyle("receipt", fontName="InvoiceVera", fontSize=8.5, leading=12)
        title = ParagraphStyle("title", parent=style, fontName="InvoiceVeraBold", fontSize=15, leading=20, alignment=1)
        def p(value, selected=style):
            return Paragraph(escape(str(value)).replace("\n", "<br/>"), selected)
        story = [p(_("Material Return Receipt"), title), Spacer(1, 12), p(snapshot["reference"]),
            p(_("Material request reference") + ": " + snapshot["request"]),
            p(_("Nonfinancial receipt. No credit, refund or invoice adjustment.")),
            p(_("Business timezone") + ": Africa/Kinshasa"), Spacer(1, 12)]
        rows = [[p(_("Material")), p(_("Returned quantity")), p(_("Return date")), p(_("Stock employee"))]]
        for line in snapshot["lines"]:
            date = datetime.fromisoformat(line["returned_at"]).astimezone(ZoneInfo("Africa/Kinshasa"))
            rows.append([p(line["code"] + " — " + line["material"]),
                p(line["quantity"] + " " + line["unit"]), p(date.strftime("%Y-%m-%d %H:%M")),
                p(line["stock_employee"] or _("Not recorded"))])
            rows.append([p(_("Return movement") + ": " + str(line["movement"]) + "; " + _("Return Reason") + ": " + line["reason"]), "", "", ""])
        table = Table(rows, colWidths=[180, 85, 115, 110], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([("VALIGN", (0,0),(-1,-1),"TOP"),
            ("BACKGROUND", (0,0),(-1,0),colors.HexColor("#eeeeee")),
            ("LINEBELOW",(0,0),(-1,-1),.3,colors.HexColor("#dddddd"))]))
        story.append(table)
        def footer(canvas, doc):
            canvas.saveState(); canvas.setFont("InvoiceVera", 7)
            canvas.setStrokeColor(colors.HexColor("#d5dce3")); canvas.line(42, 37, A4[0]-42, 37)
            canvas.drawString(42, 24, snapshot["reference"][:60])
            canvas.drawRightString(A4[0]-42, 24, _("Page") + " " + str(doc.page)); canvas.restoreState()
        SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                          topMargin=38, bottomMargin=48, title=snapshot["reference"]).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
