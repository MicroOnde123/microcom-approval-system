"""Read-only, permission-scoped frozen values and long-form stock statistics."""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _
from openpyxl.styles import Font, PatternFill

from .stock_report_export import reporting_time


def load_bookkeeping(user, requests, remaining):
    # Do not even query invoices when financial permission is absent.
    if not getattr(user, 'is_active', False):
        return None
    from invoicing.permissions import require_permission, request_scope
    try:
        require_permission(user, 'view_invoice')
    except PermissionDenied:
        return None
    allowed = set(request_scope(user).filter(pk__in=[r.pk for r in requests]).values_list('pk', flat=True))
    if not allowed:
        return None
    from invoicing.models import Invoice, InvoiceLine
    invoices = list(Invoice.objects.filter(request_id__in=allowed, status='FINALIZED').order_by('pk'))
    lines = list(InvoiceLine.objects.filter(invoice_id__in=[i.pk for i in invoices]).select_related('material__category').order_by('invoice_id', 'position', 'pk')[:remaining + 1])
    populated = {line.invoice_id for line in lines}
    missing = len(allowed - {invoice.request_id for invoice in invoices})
    empty = len([invoice for invoice in invoices if invoice.pk not in populated])
    if len(lines) + missing + empty > remaining:
        raise ValidationError(_("The workbook exceeds the export row limit. Narrow the filters and try again."))
    return {'allowed': allowed, 'invoices': invoices, 'lines': lines}


def exact_number(value):
    # Excel has 15 significant digits. Preserve larger Decimal evidence as text.
    if isinstance(value, Decimal) and len(value.as_tuple().digits) > 15:
        return format(value, 'f')
    return value


def table(workbook, name, headers, rows, note):
    sheet = workbook.create_sheet(name)
    sheet.append([note])
    sheet.append(headers)
    for row in rows:
        sheet.append([exact_number(value) for value in row])
    sheet.freeze_panes = 'A3'
    sheet.auto_filter.ref = f'A2:{sheet.cell(2, len(headers)).column_letter}{sheet.max_row}'
    for cell in sheet[2]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='D9EAF7')
    from openpyxl.styles import Alignment
    for row in sheet:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            sheet.column_dimensions[cell.column_letter].width = 28
            if isinstance(cell.value, (Decimal, float)):
                cell.number_format = '#,##0.####'
    return sheet


def frozen_branch(invoice):
    snapshot = invoice.succursale_snapshot if isinstance(invoice.succursale_snapshot, dict) else {}
    name = snapshot.get('name') or _("Frozen succursale unavailable")
    code = snapshot.get('code') or ''
    # Do not substitute current editable branch data for missing frozen evidence.
    return str(code) + (' - ' if code else '') + str(name)


def branch_group(invoice):
    snapshot = invoice.succursale_snapshot if isinstance(invoice.succursale_snapshot, dict) else {}
    identity = snapshot.get('id')
    return frozen_branch(invoice) + ' [' + (str(identity) if identity is not None else 'invoice:' + str(invoice.pk)) + ']'


def category_label(material):
    # Category names are not unique. Preserve their unique code in grouping.
    code = getattr(material.category, 'code', '')
    return material.category.name + (' [' + code + ']' if code else '')


def unit(material, frozen=None):
    value = material.unit if frozen is None else frozen
    return value or (_("Unit unavailable") + ' [' + material.code + ']')


def add_statistics(workbook, requests, movements, financial):
    reqmap = {r.pk: r for r in requests}
    invoices = {i.pk: i for i in financial['invoices']} if financial is not None else {}
    by_request = {i.request_id: i for i in invoices.values()}
    branch_for = {}
    # Long-form metrics prevent currency/unit Cartesian products and repeated
    # request counts. Stock balances are deduplicated by material primary key.
    branches = defaultdict(lambda: {'requests': set(), 'materials': set(), 'issued': defaultdict(Decimal), 'missing': 0})
    groups = defaultdict(lambda: {'materials': {}, 'issued': defaultdict(Decimal), 'movements': 0})
    monthly = defaultdict(lambda: {'requests': set(), 'movements': 0, 'issued': defaultdict(Decimal), 'BC': 0, 'BS': 0, 'missing': 0})
    for request in requests:
        if request.pk in by_request:
            branch = branch_group(by_request[request.pk])
        elif request.classification == 'CLIENT':
            branch = _("Not applicable")
        elif request.classification == 'MICROCOM':
            branch = (str(request.succursale) + ' [' + str(request.succursale_id) + ']') if request.succursale_id else _("Missing succursale")
        else:
            branch = _("Classification unavailable")
        branch_for[request.pk] = branch
        branches[branch]['requests'].add(request.pk)
        month = reporting_time(request.finalized_at)[:7] or _("Date unavailable")
        monthly[month]['requests'].add(request.pk)
        missing = int(not request.classification or (request.classification == 'MICROCOM' and not request.succursale_id))
        branches[branch]['missing'] += missing
        monthly[month]['missing'] += missing
        for item in request.material_items.all():
            material = item.material
            groups[category_label(material)]['materials'][item.material_id] = material
        for document in request.material_documents.all():
            monthly[reporting_time(document.allocated_at)[:7] or _("Date unavailable")][document.kind] += 1
    for movement in movements:
        material = movement.material
        group = groups[category_label(material)]
        group['materials'][material.pk] = material
        group['movements'] += 1
        month = reporting_time(movement.created_at)[:7] or _("Date unavailable")
        monthly[month]['movements'] += 1
        if movement.movement_type == 'OUT':
            key = unit(material)
            group['issued'][key] += movement.quantity
            monthly[month]['issued'][key] += movement.quantity
            if movement.request_id in branch_for:
                entry = branches[branch_for[movement.request_id]]
                entry['materials'].add(material.pk)
                entry['issued'][key] += movement.quantity

    branch_money = defaultdict(lambda: defaultdict(Decimal))
    group_money = defaultdict(lambda: defaultdict(Decimal))
    month_money = defaultdict(lambda: defaultdict(Decimal))
    branch_unknown = defaultdict(int)
    group_unknown = defaultdict(int)
    month_unknown = defaultdict(int)
    coverage = defaultdict(int)
    month_coverage = defaultdict(int)
    bookkeeping = []
    if financial is not None:
        lines_by_invoice = defaultdict(list)
        for line in financial['lines']:
            lines_by_invoice[line.invoice_id].append(line)
        for request_id in sorted(financial['allowed'] - set(by_request)):
            request = reqmap[request_id]
            if request.classification == 'CLIENT':
                status = _("Internal invoice not applicable")
                value = _("Not applicable")
            elif request.classification == 'MICROCOM':
                status = _("Invoice not issued or not finalized (on demand)")
                value = _("Unknown")
                coverage[branch_for[request_id]] += 1
                month_coverage[reporting_time(request.finalized_at)[:7] or _("Date unavailable")] += 1
            else:
                status = _("Classification unavailable")
                value = _("Unknown")
            bookkeeping.append(['', '', request.request_number, branch_for[request_id], '', '', '', '', value, '', value, status])
        for invoice in invoices.values():
            branch = branch_group(invoice)
            if not isinstance(invoice.succursale_snapshot, dict) or not invoice.succursale_snapshot.get('name'):
                branch_unknown[branch] += 1
            month = reporting_time(invoice.finalized_at)[:7] or _("Date unavailable")
            if invoice.total is not None:
                branch_money[branch][invoice.currency] += invoice.total
                month_money[month][invoice.currency] += invoice.total
            else:
                branch_unknown[branch] += 1
                month_unknown[month] += 1
            lines = lines_by_invoice[invoice.pk]
            if not lines:
                bookkeeping.append([invoice.number, invoice.issue_date, invoice.request_reference_snapshot, frozen_branch(invoice), '', '', '', '', _("Unknown"), invoice.currency, _("Unknown"), _("Missing frozen lines")])
                branch_unknown[branch] += 1
            for line in lines:
                unknown = line.unit_price is None or line.line_total is None
                bookkeeping.append([invoice.number, invoice.issue_date, invoice.request_reference_snapshot, frozen_branch(invoice),
                    line.description_snapshot, category_label(line.material), line.quantity, line.unit_snapshot,
                    _("Unknown") if line.unit_price is None else line.unit_price, line.currency,
                    _("Unknown") if line.line_total is None else line.line_total,
                    _("Frozen price unavailable") if unknown else _("Finalized")])
                if line.line_total is not None:
                    group_money[category_label(line.material)][line.currency] += line.line_total
                if unknown:
                    branch_unknown[branch] += 1
                    group_unknown[category_label(line.material)] += 1
                    month_unknown[month] += 1
        table(workbook, _("Bookkeeping"), [_("Invoice Reference"), _("Invoice Issue Date"), _("Request Number"), _("Succursale"),
            _("Frozen Material"), _("Material Category (current)"), _("Net Quantity"), _("Frozen Unit"), _("Frozen Unit Price"),
            _("Currency"), _("Stored Line Total"), _("Bookkeeping Status")], bookkeeping,
            _("Authorized finalized invoice evidence only. Later returns and credits are not netted. Categories are current; invoice amounts and branch names are frozen."))

    branch_rows = []
    for name in sorted(set(branches) | set(branch_money)):
        data = branches[name]
        branch_rows += [[name, _("Relevant Requests"), '', len(data['requests'])], [name, _("Materials Issued"), '', len(data['materials'])], [name, _("Missing Stock Information"), '', data['missing']]]
        branch_rows += [[name, _("Quantity Issued"), key, value] for key, value in sorted(data['issued'].items())]
        if financial is not None:
            branch_rows += [[name, _("Known Authorized Invoice Totals"), currency, value] for currency, value in sorted(branch_money[name].items())]
            # Only counts of authorized missing financial evidence are exposed.
            if name in {branch_for[rid] for rid in financial['allowed']}:
                branch_rows += [[name, _("MICROCOM invoices not issued or not finalized (on demand)"), '', coverage[name]], [name, _("Missing Frozen Values"), '', branch_unknown[name]]]
    group_rows = []
    for name in sorted(set(groups) | set(group_money)):
        data = groups[name]
        balances = defaultdict(Decimal)
        for material in data['materials'].values():
            balances[unit(material)] += material.stock_quantity
        group_rows += [[name, _("Material Count"), '', len(data['materials'])], [name, _("Movement Count"), '', data['movements']]]
        group_rows += [[name, _("Quantity Issued"), key, value] for key, value in sorted(data['issued'].items())]
        group_rows += [[name, _("Available Central Stock"), key, value] for key, value in sorted(balances.items())]
        if financial is not None:
            group_rows += [[name, _("Known Authorized Stored Line Totals"), currency, value] for currency, value in sorted(group_money[name].items())]
            if name in group_unknown:
                group_rows.append([name, _("Missing Frozen Values"), '', group_unknown[name]])
    month_rows = []
    for month in sorted(set(monthly) | set(month_money) | set(month_unknown)):
        data = monthly[month]
        month_rows += [[month, _("Approved Material Requests"), '', len(data['requests'])], [month, _("Stock Movements"), '', data['movements']],
            [month, _("Missing Stock Information"), '', data['missing']], [month, _("BC Documents"), '', data['BC']], [month, _("BS Documents"), '', data['BS']]]
        month_rows += [[month, _("Quantity Issued"), key, value] for key, value in sorted(data['issued'].items())]
        if financial is not None:
            month_rows += [[month, _("Known Authorized Invoice Totals"), currency, value] for currency, value in sorted(month_money[month].items())]
            if month in month_coverage:
                month_rows.append([month, _("MICROCOM invoices not issued or not finalized (on demand)"), '', month_coverage[month]])
            if month in month_unknown:
                month_rows.append([month, _("Missing Frozen Values"), '', month_unknown[month]])
    headers = [_("Grouping"), _("Measure"), _("Unit / Currency"), _("Value")] if financial is not None else [_("Grouping"), _("Measure"), _("Unit"), _("Value")]
    note = _("Separate measures: never add incompatible units or currencies. Issued quantities use recorded OUT movements; stock is central, not held by succursales.")
    table(workbook, _("Succursale Summary"), headers, branch_rows, note)
    table(workbook, _("Material Group Summary"), headers, group_rows, note + ' ' + _("Categories and available stock are current; each material balance is counted once."))
    table(workbook, _("Monthly Statistics"), headers, month_rows, note + ' ' + _("Africa/Kinshasa: requests by approval time, movements by movement time, BC/BS by issuance time; invoices by finalization time. Official invoice issue dates remain unchanged in Bookkeeping."))
