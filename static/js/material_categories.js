/* Native dialog provides Escape handling and keyboard focus containment. */
function initMaterialCategories(document, fetchRequest) {
    const opener = document.getElementById('new-category');
    const dialog = document.getElementById('category-dialog');
    if (!opener || !dialog || typeof dialog.showModal !== 'function') return;
    const form = document.getElementById('category-form');
    const select = document.getElementById('id_category');
    const save = document.getElementById('category-save');
    const fields = document.getElementById('category-fields');
    const summary = document.getElementById('category-errors');
    const progress = document.getElementById('category-progress');
    const announcement = document.getElementById('category-created');
    let busy = false;
    function clearErrors() {
        summary.textContent = '';
        for (const name of ['name', 'code', 'description']) {
            const input = form.elements.namedItem('category-' + name);
            input.removeAttribute('aria-invalid');
            input.removeAttribute('aria-describedby');
            const errors = document.getElementById(input.id + '-errors');
            errors.replaceChildren(); errors.hidden = true;
        }
    }
    function showErrors(errors) {
        let first;
        for (const [name, messages] of Object.entries(errors)) {
            const input = form.elements.namedItem('category-' + name);
            const list = input && document.getElementById(input.id + '-errors');
            if (!list) continue;
            for (const message of messages) {
                const item = document.createElement('li');
                item.textContent = message; list.append(item);
            }
            list.hidden = false;
            input.setAttribute('aria-invalid', 'true');
            input.setAttribute('aria-describedby', list.id);
            first = first || input;
        }
        summary.textContent = form.dataset.failure;
        fields.disabled = false;
        (first || summary).focus();
    }
    opener.hidden = false;
    opener.addEventListener('click', () => {
        clearErrors(); announcement.textContent = '';
        progress.textContent = busy ? form.dataset.saving : '';
        dialog.showModal(); form.elements.namedItem('category-name').focus();
    });
    for (const close of dialog.querySelectorAll('[data-category-close]')) {
        close.addEventListener('click', () => dialog.close());
    }
    dialog.addEventListener('close', () => opener.focus());
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy) return;
        clearErrors();
        const body = new FormData(form);
        busy = true; save.disabled = true; fields.disabled = true;
        form.setAttribute('aria-busy', 'true'); progress.textContent = form.dataset.saving;
        try {
            const response = await fetchRequest(form.action, {
                method: 'POST', body, credentials: 'same-origin', headers: {'Accept': 'application/json'}
            });
            if (response.redirected) throw new Error('Session expired');
            const data = await response.json();
            if (!response.ok) {
                showErrors(data.errors || {}); return;
            }
            if (!data.category || !Number.isInteger(data.category.id) || typeof data.category.name !== 'string') {
                throw new Error('Invalid response');
            }
            const id = String(data.category.id);
            let option = Array.from(select.options).find(item => item.value === id);
            if (!option) {
                option = new Option(data.category.name, id); select.add(option);
            }
            select.value = id;
            select.dispatchEvent(new Event('change', {bubbles: true}));
            // Only reset the separate category form. Material and stock fields stay in place.
            form.reset(); dialog.close();
            announcement.textContent = form.dataset.success;
        } catch (_error) {
            summary.textContent = form.dataset.failure; summary.focus();
        } finally {
            busy = false; save.disabled = false; fields.disabled = false;
            form.removeAttribute('aria-busy'); progress.textContent = '';
        }
    });
}
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {initMaterialCategories};
} else {
    initMaterialCategories(document, window.fetch.bind(window));
}
