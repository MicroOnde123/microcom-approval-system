/* Tab-local explicit selections; authorization remains on the print endpoint. */
function reportSelectionState(storage, context, scope) {
    const key = 'microcom.materialReportSelection';
    let ids = new Set();
    function persist() { try { storage?.setItem(key, JSON.stringify({context, scope, ids:[...ids]})); } catch (_) { storage = null; } }
    function restore() {
        try {
            const saved = JSON.parse(storage?.getItem(key) || 'null');
            if (saved?.context === context && saved.scope === scope && Array.isArray(saved.ids))
                ids = new Set(saved.ids.filter(id => typeof id === 'string' && /^[1-9][0-9]{0,18}$/.test(id)));
        } catch (_) { storage = null; }
    }
    restore(); persist();
    return {
        values: () => [...ids], has: id => ids.has(id),
        set(id, checked) { if (checked) ids.add(id); else ids.delete(id); persist(); },
        clear() { ids.clear(); persist(); },
        changeScope(next) { if (next === scope) return false; scope = next; ids.clear(); persist(); return true; },
        restore() { if (storage) { ids.clear(); restore(); } }
    };
}
function initializeReportSelection(document, window) {
    const bulk = document.getElementById('material-bulk-print-form');
    const filter = document.querySelector('form[data-auto-filters="true"]');
    const marker = document.getElementById('report-selection-context');
    if (!bulk || !filter || !marker) return;
    let storage;
    try { storage = window.sessionStorage; } catch (_) {}
    // New tabs may start with a cloned sessionStorage. Bind to the browsing
    // context name too, so a clone cannot inherit the other tab's selections.
    if (!window.name) window.name = 'microcom-report-' + (window.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2));
    const state = reportSelectionState(storage, marker.dataset.context + ':' + window.name, marker.dataset.scope);
    const counter = document.getElementById('report-selection-count');
    const notice = document.getElementById('report-selection-notice');
    const hidden = document.getElementById('report-selected-inputs');
    let loading = false;
    const names = ['q','date_from','date_to','department','status'];
    function scopeFrom(params) {
        return new URLSearchParams(names.map(name => [name, (params.get(name) || '').trim()])).toString();
    }
    function changed(scope) {
        if (state.changeScope(scope)) notice.textContent = notice.dataset.cleared;
    }
    function redraw() {
        const checks = [...bulk.querySelectorAll('.request-checkbox')];
        checks.forEach(box => { box.checked = state.has(box.value); });
        const all = bulk.querySelector('#select-all');
        if (all) {
            all.checked = checks.length > 0 && checks.every(box => box.checked);
            all.indeterminate = !all.checked && checks.some(box => box.checked);
        }
        const count = state.values().length;
        const label = (count === 0 ? counter.dataset.labelZero : count === 1 ? counter.dataset.labelOne : counter.dataset.label) || counter.dataset.label;
        counter.textContent = label.replace('%(count)s', count);
        hidden.replaceChildren();
    }
    bulk.addEventListener('change', event => {
        if (loading) return;
        if (event.target.id === 'select-all') bulk.querySelectorAll('.request-checkbox').forEach(box => state.set(box.value, event.target.checked));
        else if (event.target.classList.contains('request-checkbox')) state.set(event.target.value, event.target.checked);
        else return;
        notice.textContent = ''; redraw();
    });
    document.getElementById('report-clear-selection').addEventListener('click', () => { state.clear(); notice.textContent = ''; redraw(); });
    function filterChanged() { changed(scopeFrom(new FormData(filter))); redraw(); }
    filter.addEventListener('input', filterChanged); filter.addEventListener('change', filterChanged);
    filter.addEventListener('submit', filterChanged);
    filter.addEventListener('auto-filters:updated', event => {
        loading = event.detail.phase !== 'success';
        if (!loading) {
            changed(document.getElementById('report-selection-context').dataset.scope);
            redraw();
        }
    });
    window.addEventListener('popstate', () => { changed(scopeFrom(new URLSearchParams(window.location.search))); redraw(); });
    window.addEventListener('pageshow', () => {
        changed(scopeFrom(new URLSearchParams(window.location.search))); state.restore(); redraw();
    });
    bulk.addEventListener('submit', event => {
        if (loading) { event.preventDefault(); return; }
        hidden.replaceChildren();
        const visible = new Set([...bulk.querySelectorAll('.request-checkbox')].filter(box => box.checked).map(box => box.value));
        state.values().filter(id => !visible.has(id)).forEach(id => {
            const input = document.createElement('input'); input.type = 'hidden'; input.name = 'selected_requests'; input.value = id; hidden.append(input);
        });
    });
    redraw();
    return state;
}
if (typeof module !== 'undefined' && module.exports) module.exports = {reportSelectionState, initializeReportSelection};
else document.addEventListener('DOMContentLoaded', () => initializeReportSelection(document, window));
