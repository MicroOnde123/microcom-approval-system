"""Trusted, workbook-only Excel tables and visibility-sensitive summaries."""
from collections import defaultdict
from decimal import Decimal
from openpyxl.styles import Font
from openpyxl.utils.cell import range_boundaries, get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.workbook.properties import CalcProperties
from django.utils.translation import gettext as _, get_language


def enhance(workbook):
    """Run AFTER literal-text sanitization; only this code may introduce formulas.

    Existing analytic sheets remain full-export snapshots. Detail table values,
    including frozen prices and authoritative amounts, are never rewritten.
    """
    from .stock_report_foundations import reserve_generated
    reserve_generated(workbook, summary_rows=4)
    french = (get_language() or 'en').startswith('fr')
    tr = lambda en, fr: fr if french else en
    summary = workbook.create_sheet(tr('Visible Totals', 'Totaux visibles'))
    summary.append([tr('Interactive detail totals', 'Totaux interactifs des détails')])
    summary.append([tr('Filter detail tables. Visible totals exclude filtered and manually hidden rows. Full export totals are fixed baselines; other analytics retain their original scope. Totals include numeric evidence only, excluding unknown and precision-preserving text values.',
                       'Filtrez les tableaux de détails. Les totaux visibles excluent les lignes filtrées et masquées manuellement. Les totaux exportés restent fixes ; les autres analyses conservent leur périmètre initial.')])
    summary.append([tr('Use Calculate Now (F9) after manually hiding rows if Excel has not refreshed. Delete TABLE ROWS, not individual cell contents.',
                       'Utilisez Calculer maintenant (F9) après un masquage manuel si nécessaire. Supprimez des LIGNES DU TABLEAU, pas seulement le contenu des cellules.')])
    summary.append([tr('Worksheet', 'Feuille'), tr('Measure', 'Mesure'), tr('Unit / currency', 'Unité / devise'),
                    tr('Full exported dataset', 'Ensemble exporté'), tr('Currently visible', 'Actuellement visible')])
    specifications = [
        ('Material Report', ('Quantity',), 'Unit'),
        ('Stock Movements', ('Quantity',), 'Unit'),
        ('Current Stock Inventory', ('Current Quantity',), 'Unit'),
        ('Material Entries', ('Quantity Received',), 'Unit'),
        ('Issuance and Returns', ('Approved Quantity', 'Quantity Issued', 'Quantity Returned', 'Net Issued Quantity'), 'Unit'),
        ('Bookkeeping', ('Net Quantity',), 'Frozen Unit'),
    ]
    for index, (title, measures, unit) in enumerate(specifications, 1):
        # Material Entries uses contextual translation, resolved by actual header.
        if title == 'Material Entries':
            from django.utils.translation import pgettext
            name = pgettext('Excel worksheet', title)
        else:
            name = _(title)
        if name not in workbook.sheetnames:
            continue
        sheet = workbook[name]
        bounds = range_boundaries(sheet.auto_filter.ref)
        left, top, right, bottom = bounds
        headers = [str(sheet.cell(top, col).value) for col in range(left, right + 1)]
        assert len(headers) == len(set(headers)), 'Duplicate table headings'
        # Header-only tables have one blank body row. Keep existing empty-state
        # messages OUTSIDE the table rather than treating them as transactions.
        if bottom == top:
            sheet.insert_rows(top + 1)
            if sheet.print_area:
                sheet.print_area = f'A1:{get_column_letter(right)}{sheet.max_row}'
            bottom = top + 1
        table_name = f'MicrocomDetail{index}'
        table = Table(displayName=table_name, ref=f'A{top}:{get_column_letter(right)}{bottom}')
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=False,
                                             showColumnStripes=False)
        sheet.add_table(table)
        for measure, group in [(m, unit) for m in measures] + ([('Stored Line Total', 'Currency')] if title == 'Bookkeeping' else []):
            measure, group = _(measure), _(group)
            col, group_col = headers.index(measure) + left, headers.index(group) + left
            totals = defaultdict(Decimal)
            for row in range(top + 1, bottom + 1):
                value, key = sheet.cell(row, col).value, sheet.cell(row, group_col).value
                if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                    totals[str(key or '')] += Decimal(str(value))
            if not totals:
                totals[''] = Decimal(0)
            # SUBTOTAL over one-cell OFFSET references retains Excel row visibility;
            # structured references follow deletions/insertions of actual table rows.
            column = f'{table_name}[{measure}]'
            anchor = f'{table_name}[[#Headers],[{measure}]]'
            visible = f'SUBTOTAL(109,OFFSET({anchor},ROW({column})-ROW({anchor}),0,1))'
            reserve_generated(workbook, summary_rows=len(totals))
            for key, total in sorted(totals.items()):
                row = summary.max_row + 1
                summary.append([name, measure, key, total])
                formula = f'=IFERROR(SUMPRODUCT({visible},--({table_name}[{group}]=C{row})),0)'
                summary.cell(row, 5, formula)
                summary.cell(row, 4).number_format = summary.cell(row, 5).number_format = '#,##0.00'
    for row in summary.iter_rows(min_row=1, max_row=4):
        for cell in row:
            cell.font = Font(bold=True, color='17365D')
    for col, width in zip('ABCDE', (32, 34, 20, 26, 26)):
        summary.column_dimensions[col].width = width
    summary.freeze_panes = 'A5'
    summary.page_setup.orientation = 'landscape'
    summary.page_setup.paperSize = summary.PAPERSIZE_A3
    summary.page_setup.fitToWidth = 1
    summary.page_setup.fitToHeight = 0
    summary.sheet_properties.pageSetUpPr.fitToPage = True
    summary.print_title_rows = '1:4'
    from openpyxl.styles import Alignment
    for row in summary:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            # Labels are always literal, including malicious exported unit strings.
            if cell.column != 5 or cell.row <= 4:
                if isinstance(cell.value, str):cell.data_type = 's'
    summary.row_dimensions[2].height = 55
    summary.row_dimensions[3].height = 45
    workbook.calculation = CalcProperties(calcId=0, calcMode='auto', fullCalcOnLoad=True, forceFullCalc=True)
    return summary
