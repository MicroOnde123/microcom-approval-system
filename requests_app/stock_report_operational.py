"""Explicitly separated operational scopes; no financial models or values."""
from collections import Counter, defaultdict
from decimal import Decimal
from math import ceil

from django.utils.translation import gettext as _
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.data_source import AxDataSource, StrRef
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .stock_report_foundations import ExportBudget, reporting_scopes, reserve_generated
from .stock_report_export import reporting_time
from .stock_report_inventory import stock_status
from .stock_report_bookkeeping import category_label, exact_number
from .stock_report_entries import receipt_material


def category(name, code):
    return name + (' [' + code + ']' if code else '')


def load_warehouse_movements(user, requests, filters, existing_movements, limit, used_rows):
    """Independent movement dates; charge only IDs absent from the detail ledger."""
    existing_ids = {movement.pk for movement in existing_movements}
    scope = reporting_scopes(user, requests, filters).movements.filter(movement_type__in=['OUT', 'RETURN'])
    budget = ExportBudget(limit)
    budget.reserve('existing_detail', used_rows)
    remaining = budget.remaining
    budget.reserve('additional_movements', scope.exclude(pk__in=existing_ids).count())
    rows = list(scope[:remaining + len(existing_ids) + 1])
    additional = len({row['pk'] for row in rows} - existing_ids)
    budget.reserve('additional_movements', additional)
    return rows, additional


def operational_data(requests, inventory, entries, reconciliation, warehouse_movements):
    """All quantities stay per material/unit or category/unit, never a global sum."""
    unique_moves = {row['pk']: row for row in warehouse_movements}
    receipts = {row['pk']: row for row in entries}
    request_ids = {req.pk for req in requests}
    issued_requests, returned_requests, missing_requests = set(), set(), set()
    exceptions = Counter()
    exception_rows = 0
    for row in reconciliation:
        req_id = row['request'].pk
        if row['quantity'].out_records:
            issued_requests.add(req_id)
        if row['return_ids']:
            returned_requests.add(req_id)
        if row['approved_known'] and not row['quantity'].out_records:
            missing_requests.add(req_id)
        codes = row.get('exceptions', ())
        exceptions.update(set(codes))
        exception_rows += bool(codes)
    stock = Counter(stock_status(row['stock_quantity'], row['minimum_stock_level']) for row in inventory)
    receipt_months = defaultdict(lambda: {'receipts': set(), 'lines': 0})
    for row in receipts.values():
        data = receipt_months[row['receipt__received_on'].strftime('%Y-%m')]
        data['receipts'].add(row['receipt_id']); data['lines'] += 1
    movement_months = defaultdict(Counter)
    for row in unique_moves.values():
        month = reporting_time(row['created_at'])[:7]
        movement_months[month][row['movement_type']] += 1
    sections = [
        (_('Request cohort — selected approved requests'), [
            (_('Approved Material Requests'), len(request_ids)),
            (_('Approved Material Lines'), sum(len(req.material_items.all()) for req in requests)),
            (_('Requests with recorded issuance'), len(issued_requests)),
            (_('Requests missing OUT evidence on at least one approved material'), len(missing_requests)),
            (_('Requests with recorded returns'), len(returned_requests)),
            (_('Reconciliation exception rows'), exception_rows)]),
        (_('Current inventory — all central warehouse materials'), [
            (_('Total catalogue materials'), len(inventory)),
            (_('Active materials'), sum(bool(row['is_active']) for row in inventory)),
            (_('Inactive materials'), sum(not row['is_active'] for row in inventory)),
            (_('Materials strictly below minimum stock'), sum(row['stock_quantity'] < row['minimum_stock_level'] for row in inventory)),
            (_('Materials with zero stock'), sum(row['stock_quantity'] == 0 for row in inventory))]),
        (_('Receipt activity — business receipt dates'), [
            (_('Receipt transactions'), len({row['receipt_id'] for row in receipts.values()})),
            (_('Received material lines'), len(receipts))]),
        (_('Physical movement activity — movement dates in Africa/Kinshasa'), [
            (_('Physical OUT movement count'), sum(row['movement_type'] == 'OUT' for row in unique_moves.values())),
            (_('Physical RETURN movement count'), sum(row['movement_type'] == 'RETURN' for row in unique_moves.values()))]),
    ]
    return dict(sections=sections, stock=stock, receipts=receipt_months, movements=movement_months,
                exceptions=exceptions, warehouse=list(unique_moves.values()))


def append_summary(workbook, name, rows):
    reserve_generated(workbook, summary_rows=len(rows))
    sheet = workbook[_(name)]
    first = sheet.max_row + 1
    for row in rows:
        sheet.append([exact_number(value) for value in row])
    for row in sheet.iter_rows(min_row=first, max_row=sheet.max_row, max_col=4):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if isinstance(cell.value, Decimal):
                cell.number_format = '#,##0.00'
    sheet.auto_filter.ref = f'A2:D{sheet.max_row}'
    sheet.print_title_rows = '1:2'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_area = f'A1:D{sheet.max_row}'


def add_operational_reporting(workbook, requests, inventory, entries, reconciliation, warehouse_movements, filters):
    data = operational_data(requests, inventory, entries, reconciliation, warehouse_movements)
    dashboard, graphs = workbook[_('Dashboard')], workbook[_('Graphs')]
    scope_note = _('Scopes are independent: request Date Needed; current inventory including inactive materials; business receipt dates; physical movement dates in Africa/Kinshasa. Reconciliation uses all selected-request movement dates. Missing issuance means an approved material lacks OUT evidence. Exception categories may overlap.')
    start = dashboard.max_row + 3
    dashboard.cell(start, 1, scope_note).alignment = Alignment(wrap_text=True)
    dashboard.merge_cells(start_row=start, start_column=1, end_row=start + 2, end_column=12)
    start += 4
    bounds = [(_('Receipt Date From'), filters.get('warehouse_receipt_from')),
              (_('Receipt Date To'), filters.get('warehouse_receipt_to')),
              (_('Movement Date From'), filters.get('warehouse_movement_from')),
              (_('Movement Date To'), filters.get('warehouse_movement_to'))]
    for label, value in bounds:
        dashboard.cell(start, 1, label); dashboard.cell(start, 5, str(value) if value else _('Unbounded'))
        start += 1
    reserve_generated(workbook, summary_rows=sum(len(metrics) for _, metrics in data['sections']))
    for scope, metrics in data['sections']:
        dashboard.cell(start, 1, scope).font = Font(bold=True, color='FFFFFF')
        dashboard.cell(start, 1).fill = PatternFill('solid', fgColor='17365D')
        dashboard.merge_cells(start_row=start, start_column=1, end_row=start, end_column=12)
        start += 1
        for label, value in metrics:
            dashboard.cell(start, 1, label)
            dashboard.merge_cells(start_row=start, start_column=1, end_row=start, end_column=8)
            dashboard.cell(start, 9, value).number_format = '0'
            start += 1
    dashboard.print_area = f'A1:L{start}'

    # Add new measures; preserve legacy summary definitions and label each scope.
    branch = defaultdict(lambda: defaultdict(Decimal))
    group = defaultdict(lambda: defaultdict(Decimal))
    month_quantities = defaultdict(lambda: defaultdict(Decimal))
    months = []
    for req in requests:
        label = str(req.succursale) if req.classification == 'MICROCOM' and req.succursale_id else (
            _('Not applicable') if req.classification == 'CLIENT' else _('Classification unavailable'))
        for item in req.material_items.all():
            unit = item.material.unit or (_('Unit unavailable') + ' [' + item.material.code + ']')
            branch[label][(_('Approved demand — request cohort'), unit)] += item.quantity
            group[category_label(item.material)][(_('Approved demand — request cohort'), unit)] += item.quantity
            month_quantities[reporting_time(req.finalized_at)[:7] or _('Date unavailable')][(_('Approved demand — request cohort'), unit)] += item.quantity
    for row in reconciliation:
        req, mat, q = row['request'], row['material'], row['quantity']
        label = str(req.succursale) if req.classification == 'MICROCOM' and req.succursale_id else (
            _('Not applicable') if req.classification == 'CLIENT' else _('Classification unavailable'))
        unit = mat.unit or (_('Unit unavailable') + ' [' + mat.code + ']')
        for metric, value in [(_('Returned quantity — request cohort'), q.returned), (_('Net issued — request cohort'), q.net_issued)]:
            branch[label][(metric, unit)] += value
            group[category_label(mat)][(metric, unit)] += value
    for row in inventory:
        unit = row['unit'] or (_('Unit unavailable') + ' [' + row['code'] + ']')
        group[category(row['category__name'], row['category__code'])][(_('Current central stock — entire catalogue'), unit)] += row['stock_quantity']
    for row in entries:
        material, snapshot = receipt_material(row)
        unit = material[3]
        unit = unit or (_('Unit unavailable') + ' [' + row['material__code'] + ']')
        name = material[2]
        code = ((row['snapshot_category_code'] or '') if isinstance(row['snapshot_category_code'], str) else '') if snapshot else row['material__category__code']
        group[category(name, code)][(_('Received quantity — receipt dates'), unit)] += row['quantity']
        month_quantities[row['receipt__received_on'].strftime('%Y-%m')][(_('Received quantity — receipt dates'), unit)] += row['quantity']
    for row in data['warehouse']:
        unit = row['material__unit'] or (_('Unit unavailable') + ' [' + row['material__code'] + ']')
        metric = _('Issued quantity — warehouse movement dates') if row['movement_type'] == 'OUT' else _('Returned quantity — warehouse movement dates')
        group[category(row['material__category__name'], row['material__category__code'])][(metric, unit)] += row['quantity']
        month = reporting_time(row['created_at'])[:7]
        month_quantities[month][(metric, unit)] += row['quantity']
        month_quantities[month][(_('Net issued — warehouse movement dates'), unit)] += (
            row['quantity'] if row['movement_type'] == 'OUT' else -row['quantity'])
    for name, target in [('Succursale Summary', branch), ('Material Group Summary', group)]:
        append_summary(workbook, name, [[label, metric, unit, value] for label in sorted(target)
                                       for (metric, unit), value in sorted(target[label].items())])
    for month, values in sorted(data['receipts'].items()):
        months.extend([[month, _('Receipt transactions — receipt dates'), '', len(values['receipts'])],
                       [month, _('Received lines — receipt dates'), '', values['lines']]])
    for month, values in sorted(data['movements'].items()):
        months.extend([[month, _('OUT count — warehouse movement dates'), '', values['OUT']],
                       [month, _('RETURN count — warehouse movement dates'), '', values['RETURN']]])
    months.extend([[month, metric, unit, value] for month in sorted(month_quantities)
                   for (metric, unit), value in sorted(month_quantities[month].items())])
    append_summary(workbook, 'Monthly Statistics', months)
    for name in ('Succursale Summary', 'Material Group Summary', 'Monthly Statistics'):
        workbook[_(name)]['A1'] = str(workbook[_(name)]['A1'].value) + ' ' + scope_note + ' ' + _(
            'Legacy issued and available-stock summary rows retain their original request/movement scope; entire-catalogue and warehouse-period measures have separate labels. Financial summaries appear only in authorized Bookkeeping.')
        sheet = workbook[_(name)]
        sheet.merge_cells('A1:D1')
        sheet.row_dimensions[1].height = max(60, 15 * (ceil(len(str(sheet['A1'].value)) / 90) + 1))
        sheet.row_dimensions[2].height = 30

    exception_labels = dict(missing_out=_('Missing OUT evidence'), unapproved=_('No approved material line'),
        repeated_lines=_('Repeated material lines'), non_positive=_('Non-positive movement quantity'),
        excess_returns=_('Returns exceed recorded issuance'), bad_document=_('Unverified return document link'),
        over_issued=_('Issued quantity exceeds approved quantity'), partial=_('Partial issuance'))
    sources = [
        (_('Current inventory stock-status counts'), [_('Stock Status'), _('Material Count')], sorted(data['stock'].items()), BarChart, 'A47'),
        (_('Monthly receipt transactions and lines'), [_('Month'), _('Receipt transactions'), _('Received material lines')],
         [[month, len(values['receipts']), values['lines']] for month, values in sorted(data['receipts'].items())], LineChart, 'L47'),
        (_('Monthly physical OUT and RETURN counts'), [_('Month'), _('Stock Out'), _('Return to Stock')],
         [[month, values['OUT'], values['RETURN']] for month, values in sorted(data['movements'].items())], LineChart, 'A67'),
        (_('Reconciliation exceptions by category (overlapping)'), [_('Reconciliation Status'), _('Exception rows')],
         [[exception_labels[code], count] for code, count in sorted(data['exceptions'].items())], BarChart, 'L67'),
    ]
    graphs['A45'] = scope_note
    graphs.merge_cells('A45:U46')
    graphs['A45'].alignment = Alignment(wrap_text=True)
    graphs.row_dimensions[45].height = 32
    for index, (title, headers, rows, chart_type, anchor) in enumerate(sources):
        if not rows:
            continue
        reserve_generated(workbook, chart_rows=len(rows))
        col = 40 + index * 4
        for offset, header in enumerate(headers):
            graphs.cell(1, col + offset, header)
        for number, row in enumerate(rows, 2):
            for offset, value in enumerate(row):
                graphs.cell(number, col + offset, value)
        for offset in range(len(headers)):
            graphs.column_dimensions[get_column_letter(col + offset)].hidden = True
        chart = chart_type()
        chart.title = title
        chart.add_data(Reference(graphs, min_col=col + 1, max_col=col + len(headers) - 1,
                                 min_row=1, max_row=len(rows) + 1), titles_from_data=True)
        categories = Reference(graphs, min_col=col, min_row=2, max_row=len(rows) + 1)
        for series in chart.series:
            series.cat = AxDataSource(strRef=StrRef(f=str(categories)))
        chart.visible_cells_only = False
        chart.width, chart.height = 18.5, 9.5
        chart.y_axis.title = _('Count')
        chart.y_axis.scaling.min = 0
        chart.y_axis.numFmt = '0'
        chart.y_axis.majorUnit = max(1, ceil(max(value for row in rows for value in row[1:]) / 5))
        chart.style = 13
        if chart_type is BarChart:
            chart.type = 'bar'
            chart.x_axis.axPos = 'l'
            chart.y_axis.axPos = 'b'
            chart.x_axis.scaling.orientation = 'maxMin'
            chart.y_axis.crosses = 'max'
        for number, series in enumerate(chart.series):
            color = ('2874A6', '178578')[number % 2]
            series.graphicalProperties.line.solidFill = color
            series.graphicalProperties.solidFill = color
        if len(headers) == 2:
            chart.legend = None
        graphs.add_chart(chart, anchor)
    graphs.print_area = 'A1:U86'
    graphs.page_setup.fitToHeight = 0
