"""Receipt-line evidence; no price loading, stock reconstruction or writes."""
from django.utils import timezone
from django.utils.translation import gettext as _, get_language, pgettext
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .stock_report_export import reporting_time
from .stock_report_foundations import ExportBudget, authorize_stock_reporting, reporting_scopes


def load_material_entries(user, approved_requests, filters, limit, used_rows):
    scope = reporting_scopes(user, approved_requests, filters).receipts
    budget = ExportBudget(limit)
    budget.reserve('existing_detail', used_rows)
    remaining = budget.remaining
    budget.reserve('receipt_lines', scope.count())
    rows = list(scope[:remaining + 1])
    budget.reserve('receipt_lines', len(rows))
    return rows


def receipt_material(row):
    """Shared descriptive evidence, identical in details and receipt analytics."""
    names = ('code', 'name', 'category_name', 'unit')
    snapshot = str(row['snapshot_version']) == '1' and all(isinstance(row['snapshot_' + name], str) for name in names)
    values = [row['snapshot_' + name] for name in names] if snapshot else [
        row['material__code'], row['material__name'], row['material__category__name'], row['material__unit']]
    return values, snapshot


def add_material_entries(workbook, user, rows, filters):
    authorize_stock_reporting(user)
    sheet = workbook.create_sheet(pgettext('Excel worksheet', 'Material Entries'))
    sheet.append([_('Central warehouse receipts, filtered by business receipt date only. Request search, department, Date Needed and movement dates do not apply. Recorded timestamps: Africa/Kinshasa. No valuation.')])
    sheet.merge_cells('A1:S1')
    sheet.append([_('Generated At'), reporting_time(timezone.now()), 'Africa/Kinshasa',
                  _('Receipt Date From'), filters.get('warehouse_receipt_from') or _('No lower bound'),
                  _('Receipt Date To'), filters.get('warehouse_receipt_to') or _('No upper bound')])
    sheet.append([_('Material evidence identifies recorded snapshots or current catalogue fallback. Stock after receipt is recorded historical evidence, never current stock. Movement references are database IDs.')])
    sheet.merge_cells('A3:S3')
    headers = [_('Receipt Reference'), _('Receipt Date'), _('Date Recorded'), _('Material Code'),
               _('Material'), _('Category'), _('Unit'), _('Quantity Received'), _('Stock After Receipt'),
               _('Transaction Type'), _('Stock Movement ID'), _('Movement Type'), _('Movement Quantity'),
               _('Recorded By'), _('Supplier'), _('Delivery Reference'), _('Notes'),
               _('Material Evidence'), _('Movement Evidence')]
    sheet.append(headers)
    for row in rows:
        material, snapshot = receipt_material(row)
        transaction = {'new': _('New material'), 'existing': _('Existing material')}.get(row['receipt__transaction_type'], _('Not recorded'))
        valid_movement = (row['movement__movement_type'] == 'IN'
                          and row['movement__material_id'] == row['material_id']
                          and row['movement__quantity'] == row['quantity'])
        sheet.append([
            row['receipt__reference'], row['receipt__received_on'], reporting_time(row['receipt__created_at']),
            *material, row['quantity'], row['stock_after'], transaction, row['movement_id'],
            {'IN': _('Stock In'), 'OUT': _('Stock Out'), 'RETURN': _('Return to Stock')}.get(row['movement__movement_type'], _('Not recorded')),
            row['movement__quantity'],
            row['receipt__created_by__full_name'] or row['receipt__created_by__username'] or _('Not recorded'),
            row['receipt__supplier'] or _('Not recorded'), row['receipt__delivery_reference'] or _('Not recorded'),
            row['receipt__notes'],
            _('Recorded material snapshot') if snapshot else _('Current catalogue fallback; historical material details not recorded'),
            _('Linked IN movement') if valid_movement else _('Inconsistent linked movement evidence'),
        ])
    if not rows:
        sheet.append([_('No material receipts for the selected receipt dates.')])
    sheet.freeze_panes = 'A5'
    sheet.auto_filter.ref = f'A4:S{max(4, 4 + len(rows))}'
    sheet.sheet_view.showGridLines = False
    widths = (40, 16, 22, 22, 32, 26, 12, 20, 22, 22, 22, 20, 20, 28, 28, 28, 40, 42, 36)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cell in sheet[4]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17365D')
    for cells in sheet:
        for cell in cells:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    date_format = 'dd/mm/yyyy' if (get_language() or 'en').startswith('fr') else 'yyyy-mm-dd'
    for index in range(5, 5 + len(rows)):
        sheet.cell(index, 2).number_format = date_format
        for column in (8, 9, 13):
            sheet.cell(index, column).number_format = '#,##0.00'
    for column in (5, 7):
        sheet.cell(2, column).number_format = date_format
    sheet.row_dimensions[1].height = 32
    sheet.row_dimensions[3].height = 32
    sheet.print_title_rows = '1:4'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_area = f'A1:S{sheet.max_row}'
    return sheet
