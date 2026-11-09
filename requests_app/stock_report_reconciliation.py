"""Request/material physical evidence. No stock, invoice or workflow writes."""
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _, get_language
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import ReturnReceiptLine
from .stock_report_export import reporting_time, request_extras
from .stock_report_foundations import ExportBudget, authorize_stock_reporting, quantity_evidence


def evidence_text(values):
    text = '; '.join(map(str, values))
    if len(text) > 32767:
        raise ValidationError(_('The reconciliation evidence exceeds Excel\'s cell limit. Narrow the filters and try again.'))
    return text


def load_issuance_returns(user, requests, movements, limit, used_rows):
    """Reuse bounded loaded sources; one projected query for physical receipts.

    Warehouse/unlinked movements and IN records do not enter this reconciliation.
    A repeated input movement PK is counted once. Repeated material request lines
    are explicitly flagged, not assigned invented per-line movement associations.
    """
    authorize_stock_reporting(user)
    reqmap = {req.pk: req for req in requests if req.status == 'APPROVED'}
    approved, recorded, metadata = [], [], {}
    line_counts = defaultdict(int)
    ids = defaultdict(lambda: {'OUT': [], 'RETURN': []})
    invalid = set()
    move_map = {}
    for req in reqmap.values():
        for item in req.material_items.all():
            key = (req.pk, item.material_id, item.material.unit)
            metadata[key] = item.material
            line_counts[key] += 1
            approved.append(dict(request_id=req.pk, material_id=item.material_id,
                                 material__unit=item.material.unit, quantity=item.quantity))
    for movement in movements:
        if movement.pk in move_map or movement.request_id not in reqmap or movement.movement_type not in ('OUT', 'RETURN'):
            continue
        move_map[movement.pk] = movement
        key = (movement.request_id, movement.material_id, movement.material.unit)
        metadata.setdefault(key, movement.material)
        ids[key][movement.movement_type].append(movement.pk)
        if movement.quantity <= 0:
            invalid.add(key)
        recorded.append(dict(request_id=movement.request_id, material_id=movement.material_id,
                             material__unit=movement.material.unit, movement_type=movement.movement_type,
                             quantity=movement.quantity, records=1))
    evidence = quantity_evidence(approved, recorded)
    budget = ExportBudget(limit)
    budget.reserve('existing_detail', used_rows)
    budget.reserve('reconciliation', len(evidence))
    return_ids = [pk for pk, movement in move_map.items() if movement.movement_type == 'RETURN']
    documents = defaultdict(list)
    invalid_documents = set()
    if return_ids:
        links = ReturnReceiptLine.objects.filter(movement_id__in=return_ids).order_by('movement_id').values(
            'movement_id', 'quantity', 'receipt__request_id', 'receipt__reference')
        for link in links:
            movement = move_map[link['movement_id']]
            key = (movement.request_id, movement.material_id, movement.material.unit)
            if link['receipt__request_id'] == movement.request_id and link['quantity'] == movement.quantity:
                documents[key].append(f"{movement.pk}: {link['receipt__reference']}")
            else:
                invalid_documents.add(key)
    result = []
    for key in sorted(evidence):
        value = evidence[key]
        flags = []
        if key not in line_counts:
            flags.append(_('No approved material line'))
        if line_counts.get(key, 0) > 1:
            flags.append(_('Repeated material lines; movement allocation unavailable'))
        if not value.out_records:
            flags.append(_('Missing OUT evidence'))
        if key in invalid:
            flags.append(_('Non-positive movement quantity; review history'))
        if value.returned > value.issued:
            flags.append(_('Returns exceed recorded issuance'))
        if key in invalid_documents:
            flags.append(_('Unverified return document link'))
        if key in line_counts and value.issued > value.approved:
            flags.append(_('Issued quantity exceeds approved quantity'))
        if not flags:
            if value.issued < value.approved:
                flags.append(_('Partial issuance'))
            elif value.returned == value.issued:
                flags.append(_('Fully returned'))
            elif value.returned:
                flags.append(_('Partially returned'))
            else:
                flags.append(_('Issued; no returns recorded'))
        result.append(dict(request=reqmap[key[0]], material=metadata[key], quantity=value,
            exceptions=tuple(code for code, applies in (
                ('missing_out', not value.out_records), ('unapproved', key not in line_counts),
                ('repeated_lines', line_counts.get(key, 0) > 1), ('non_positive', key in invalid),
                ('excess_returns', value.returned > value.issued), ('bad_document', key in invalid_documents),
                ('over_issued', key in line_counts and value.issued > value.approved),
                ('partial', key in line_counts and value.out_records > 0 and value.issued < value.approved),
            ) if applies),
            approved_known=key in line_counts,
            out_ids=evidence_text(sorted(ids[key]['OUT'])),
            return_ids=evidence_text(sorted(ids[key]['RETURN'])),
            documents=evidence_text(documents[key]) or _('Not recorded'),
            status=evidence_text(flags)))
    return result


def add_issuance_returns(workbook, user, rows):
    authorize_stock_reporting(user)
    sheet = workbook.create_sheet(_('Issuance and Returns'))
    sheet.append([_('Selected approved requests, filtered by Date Needed, search and department. All linked OUT and RETURN dates are included; warehouse activity dates do not apply. No unlinked movements or valuation.')])
    sheet.merge_cells('A1:U1')
    sheet.append([_('Generated At'), reporting_time(timezone.now()), 'Africa/Kinshasa'])
    sheet.append([_('Approved quantities authorize stock; they do not prove issuance. Net issued = recorded OUT minus RETURN. Materials and units are current catalogue data. Movement references are database IDs; return references require verified receipt links.')])
    sheet.merge_cells('A3:U3')
    sheet.append([_('Request Number'), _('Request Status'), _('Date Needed'), _('Approved Date'),
                  _('Department'), _('Request For Department'), _('Request Classification'), _('Succursale'),
                  _('Material Code'), _('Material'), _('Unit'), _('Approved Quantity'),
                  _('Quantity Issued'), _('Quantity Returned'), _('Net Issued Quantity'), _('Issuance Evidence'),
                  _('OUT Movement IDs'), _('RETURN Movement IDs'), _('Linked Return References'),
                  _('Reconciliation Status'), _('Material ID')])
    for row in rows:
        req, material, quantity = row['request'], row['material'], row['quantity']
        issuance = (_('Missing OUT evidence') if not quantity.out_records else
                    _('Recorded zero OUT total') if quantity.issued == 0 else _('Recorded OUT movements'))
        classification, branch = request_extras(req)[:2]
        sheet.append([req.request_number, _(req.get_status_display()), req.date_needed, reporting_time(req.finalized_at),
            req.department.name if req.department else _('Not recorded'), req.request_for_department.name,
            classification, branch, material.code, material.name, material.unit,
            quantity.approved if row['approved_known'] else _('Not recorded'),
            quantity.issued, quantity.returned, quantity.net_issued, issuance,
            row['out_ids'] or _('Not recorded'), row['return_ids'] or _('Not recorded'),
            row['documents'], row['status'], material.pk])
    if not rows:
        sheet.append([_('No request/material reconciliation evidence for the selected requests.')])
    sheet.freeze_panes = 'A5'
    sheet.auto_filter.ref = f'A4:U{max(4, 4 + len(rows))}'
    sheet.sheet_view.showGridLines = False
    widths = (24, 20, 16, 22, 24, 26, 24, 28, 22, 30, 12, 20, 20, 20, 20, 30, 34, 34, 40, 48, 16)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cell in sheet[4]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17365D')
    for cells in sheet:
        for cell in cells:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    for index in range(5, 5 + len(rows)):
        sheet.cell(index, 3).number_format = 'dd/mm/yyyy' if (get_language() or 'en').startswith('fr') else 'yyyy-mm-dd'
        for column in range(12, 16):
            sheet.cell(index, column).number_format = '#,##0.00'
    sheet.row_dimensions[1].height = 32
    sheet.row_dimensions[3].height = 32
    sheet.print_title_rows = '1:4'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_area = f'A1:U{sheet.max_row}'
    return sheet
