/* Invoice-list integration only: existing filtering and printing remain authoritative. */
function normalizeInvoiceDates(form) {
    form.querySelectorAll('[data-entry-date]').forEach(root => {
        const input = root.querySelector('input');
        const date = parseEntryDate(input.value);
        if (date) input.value = formatEntryDate(date, root.dataset.language);
    });
}
function synchronizeInvoicePrintFilters(filterForm, printFilters, document) {
    const formData = new FormData(filterForm);
    for (const key of ['date_from', 'date_to']) {
        const date = parseEntryDate(formData.get(key) || '');
        if (date) formData.set(key, isoEntryDate(date));
    }
    printFilters.replaceChildren();
    for (const [name, value] of formData.entries()) {
        if (!name || name === 'page' || name === 'candidate_q') continue;
        const input = document.createElement('input');
        input.type = 'hidden'; input.name = name; input.value = value;
        printFilters.appendChild(input);
    }
}
if (typeof module !== 'undefined') module.exports = {normalizeInvoiceDates, synchronizeInvoicePrintFilters};
if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', () => {
    const filterForm = document.getElementById('invoice-filter-form');
    const printForm = document.getElementById('invoice-bulk-print-form');
    const printFilters = document.getElementById('invoice-print-filters');
    if (!filterForm || !printForm || !printFilters) return;
    const sync = () => synchronizeInvoicePrintFilters(filterForm, printFilters, document);
    filterForm.addEventListener('auto-filters:updated', event => {
        if (event.detail.phase === 'success') normalizeInvoiceDates(filterForm);
        sync();
    });
    for (const type of ['input', 'change', 'submit']) filterForm.addEventListener(type, sync);
    printForm.addEventListener('submit', sync);
    // The shared live-filter handler restores URL values; localize after restoration.
    window.addEventListener('popstate', () => window.setTimeout(() => {normalizeInvoiceDates(filterForm); sync();}, 0));
    sync();
});
