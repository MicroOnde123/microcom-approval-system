"""Invoice-style portrait A4 reconciliation of detached immutable values only."""
import base64
import hashlib
import io
from xml.sax.saxutils import escape
from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _, override
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from .pdf import _fonts, _CONTENT_WIDTH, display_decimal

CLARIFICATION='This document reconciles material values after recorded returns. It does not replace or modify the original finalized invoice and does not constitute a payment adjustment or credit note.'


def render(statement, language):
    if language not in ('en', 'fr'):
        raise ValidationError(_('Choose English or French for the PDF.'))
    _fonts()
    snapshot = statement.snapshot
    with override(language):
        regular = ParagraphStyle('as-body', fontName='InvoiceVera', fontSize=8.5, leading=12,
                                 textColor=colors.HexColor('#202020'), spaceAfter=4)
        bold = ParagraphStyle('as-bold', parent=regular, fontName='InvoiceVeraBold')
        title = ParagraphStyle('as-title', parent=bold, fontSize=15, leading=20, alignment=1, spaceAfter=10)
        right = ParagraphStyle('as-right', parent=regular, alignment=2)
        cell = ParagraphStyle('as-cell', parent=regular, spaceAfter=0)
        numeric = ParagraphStyle('as-numeric', parent=right, spaceAfter=0)
        heading = ParagraphStyle('as-heading', parent=bold, spaceAfter=0)
        numeric_heading = ParagraphStyle('as-heading-right', parent=heading, alignment=2)

        def p(value, style=regular):
            return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)

        brand = snapshot['branding']
        # Match the invoice: validate frozen branding without drawing issuer assets.
        if brand.get('strategy') == 'embedded-content':
            if len(brand['content_base64']) > 2800000:
                raise ValidationError(_('Invalid frozen company logo.'))
            logo = base64.b64decode(brand['content_base64'], validate=True)
            mime = 'image/png' if logo.startswith(b'\x89PNG\r\n\x1a\n') else (
                'image/jpeg' if logo.startswith(b'\xff\xd8\xff') else (
                    'image/webp' if logo[:4] == b'RIFF' and logo[8:12] == b'WEBP' else None))
            if (len(logo) > 2097152 or hashlib.sha256(logo).hexdigest() != brand['sha256']
                    or mime is None or mime != brand['content_type']):
                raise ValidationError(_('Invalid frozen company logo.'))

        metadata = Table([[p(_('Document number') + ': ' + statement.number, bold),
                           p(_('Issue date') + ': ' + statement.issue_date.isoformat(), right)]],
                         colWidths=[_CONTENT_WIDTH - 200, 200], hAlign='LEFT')
        metadata.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                     ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                     ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        branch = snapshot['branch']
        story = [p(_('Adjusted Invoice Statement'), title), metadata,
                 p(_('Client: %(name)s') % {'name': branch['name']}),
                 p(_('Original invoice') + ': ' + snapshot['invoice_number']),
                 p(_('Issued by') + ': ' + statement.issuer_name), Spacer(1, 9)]
        try:
            UUID(snapshot['request_reference'])
        except (ValueError, TypeError, AttributeError):
            story.insert(4, p(_('Material request reference') + ': ' + snapshot['request_reference']))
        if branch.get('physical_address'):
            story.extend([p(_('Succursale physical address'), bold), p(branch['physical_address']), Spacer(1, 6)])

        def table(rows, widths, spans=()):
            result = Table(rows, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
            result.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f1f1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, 0), .8, colors.HexColor('#505050')),
                ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#d8d8d8')),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ] + list(spans)))
            return result

        rows = [[p(_('Material'), heading), p(_('Quantity'), numeric_heading),
                 p(_('Unit price'), numeric_heading), p(_('Line total'), numeric_heading)]]
        spans = []
        for line in snapshot['lines']:
            unit = ' (' + line['unit'] + ')' if line['unit'] else ''
            row = len(rows)
            rows.append([p(line['code'] + unit + ' — ' + line['description'], cell), '', '', ''])
            spans.append(('SPAN', (0, row), (-1, row)))
            for label, quantity, value in (
                ('Original invoiced quantity', 'original_quantity', 'original_value'),
                ('Cumulative returned quantity', 'returned_quantity', 'returned_value'),
                ('Net remaining quantity', 'net_quantity', 'net_value'),
            ):
                rows.append([p(_(label), cell), p(display_decimal(line[quantity]), numeric),
                             p(display_decimal(line['unit_price'], minimum_places=2), numeric),
                             p(display_decimal(line[value], minimum_places=2), numeric)])
        story.append(table(rows, [_CONTENT_WIDTH - 240, 60, 90, 90], spans))
        total_style = ParagraphStyle('as-total', parent=bold, alignment=2, fontSize=10, leading=15)
        summary = [Spacer(1, 10)]
        for label, key in [('Original invoice total', 'original_total'),
                           ('Cumulative documented returns', 'returned_total'),
                           ('Adjusted net material value', 'net_total')]:
            summary.append(p(_(label) + ': ' + display_decimal(snapshot[key], minimum_places=2)
                             + ' ' + snapshot['currency'], total_style))
        summary.append(p(_('Currency') + ': ' + snapshot['currency']))
        story.extend([KeepTogether(summary), Spacer(1, 9), p(_('Included return notes'), bold)])
        returns = [[p(_('Document number'), heading), p(_('Issue date'), heading),
                    p(_('Line total') + ' (' + snapshot['currency'] + ')', numeric_heading)]]
        for note in snapshot['returns']:
            returns.append([p(note['number'], cell), p(note['issue_date'], cell),
                            p(display_decimal(note['total'], minimum_places=2), numeric)])
        story.extend([table(returns, [_CONTENT_WIDTH - 260, 110, 150]),
                      KeepTogether([Spacer(1, 10), p(_(CLARIFICATION)), Spacer(1, 12),
                                    p(_('Stock Department'), ParagraphStyle('as-stock', parent=bold, alignment=2))])])
        output = io.BytesIO()

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor('#d5dce3'))
            canvas.line(42, 37, A4[0] - 42, 37)
            canvas.setFont('InvoiceVera', 7)
            canvas.drawString(42, 24, statement.number[:60])
            canvas.drawRightString(A4[0] - 42, 24, _('Page') + ' ' + str(doc.page))
            canvas.restoreState()

        SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42,
                          topMargin=38, bottomMargin=48, title=statement.number).build(
                              story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()
