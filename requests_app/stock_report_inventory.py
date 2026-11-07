"""Current central-stock evidence only; no price or historical valuation."""
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl.styles import Alignment, Font, PatternFill

from .stock_report_export import reporting_time
from .stock_report_foundations import ExportBudget, reporting_scopes, authorize_stock_reporting


def load_current_inventory(user, approved_requests, warehouse_filters, limit, used_rows):
    """Count before loading and recheck a bounded load against the detail budget."""
    scope = reporting_scopes(user, approved_requests, warehouse_filters).inventory
    budget = ExportBudget(limit)
    budget.reserve('existing_detail', used_rows)
    remaining = budget.remaining
    budget.reserve('inventory', scope.count())
    rows = list(scope[:remaining + 1])
    budget.reserve('inventory', len(rows))
    return rows


def stock_status(quantity, minimum):
    if quantity < 0:
        return _('Negative stock')
    if quantity == 0:
        return _('Out of stock')
    if quantity <= minimum:
        return _('Low stock')
    return _('In stock')


def add_current_inventory(workbook, user, rows):
    authorize_stock_reporting(user)
    sheet = workbook.create_sheet(_('Current Stock Inventory'))
    sheet.append([_('Current central warehouse snapshot. Includes inactive materials. Request and activity filters do not apply. No historical balances or valuation.')])
    sheet.merge_cells('A1:H1')
    sheet.append([_('Generated At'), reporting_time(timezone.now()), 'Africa/Kinshasa'])
    sheet.append([_('Stock status: negative below zero; out of stock at zero; low stock above zero and at or below minimum; in stock above minimum.')])
    sheet.merge_cells('A3:H3')
    sheet.append([_('Material Code'), _('Material'), _('Category'), _('Unit'),
                  _('Active status'), _('Current Quantity'), _('Minimum Stock Level'), _('Stock Status')])
    # Eight columns: no catalogue prices, currencies or financial metadata.
    for row in rows:
        sheet.append([row['code'], row['name'], row['category__name'], row['unit'],
                      _('Active') if row['is_active'] else _('Inactive'),
                      row['stock_quantity'], row['minimum_stock_level'],
                      stock_status(row['stock_quantity'], row['minimum_stock_level'])])
    if not rows:
        sheet.append([_('No materials in the current inventory.')])
    sheet.freeze_panes = 'A5'
    sheet.auto_filter.ref = f'A4:H{max(4, 4 + len(rows))}'
    sheet.sheet_view.showGridLines = False
    for cell in sheet[4]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='17365D')
    for column, width in zip('ABCDEFGH', (22, 32, 26, 14, 18, 20, 22, 22)):
        sheet.column_dimensions[column].width = width
    for row in sheet:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    for row in sheet.iter_rows(min_row=5, max_row=4 + len(rows), min_col=6, max_col=7):
        for cell in row:
            cell.number_format = '#,##0.00'
    sheet.row_dimensions[1].height = 32
    sheet.row_dimensions[3].height = 32
    sheet.print_title_rows = '1:4'
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_area = f'A1:H{sheet.max_row}'
    return sheet
