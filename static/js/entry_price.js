/* Independent pricing form: never serialize or submit the stock receipt. */
(() => {
    const form = document.getElementById('entry-price-form');
    if (!form) return;
    const dialog = document.getElementById('entry-price-dialog');
    const button = document.getElementById('modify-material-price');
    const select = document.getElementById('id_material');
    const fields = document.getElementById('entry-price-fields');
    const save = document.getElementById('entry-price-save');
    const errors = document.getElementById('entry-price-errors');
    const progress = document.getElementById('entry-price-progress');
    let materialId = null, busy = false, generation = 0;
    const url = id => form.dataset.url.replace('/0/', '/' + id + '/');
    function enableButton() { button.disabled = !select.value; }
    select.addEventListener('change', enableButton); enableButton();
    function clearErrors() {
        errors.replaceChildren();
        form.querySelectorAll('[aria-invalid]').forEach(field => field.removeAttribute('aria-invalid'));
        form.querySelectorAll('.errorlist').forEach(list => { list.replaceChildren(); list.hidden = true; });
    }
    function showErrors(data) {
        Object.entries(data.errors || {'__all__': [form.dataset.failure]}).forEach(([name, messages]) => {
            const field = form.elements.namedItem(name);
            const list = field && document.getElementById(field.id + '-price-errors');
            messages.forEach(message => {
                const p = document.createElement('p'); p.textContent = message; errors.append(p);
                if (list) { const li = document.createElement('li'); li.textContent = message; list.append(li); list.hidden = false; }
            });
            if (field) field.setAttribute('aria-invalid', 'true');
        });
        errors.focus();
    }
    function close() { if (!busy) dialog.close(); }
    document.getElementById('entry-price-cancel').addEventListener('click', close);
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { generation++; button.focus(); });
    button.addEventListener('click', async () => {
        materialId = select.value;
        if (!materialId || busy) return;
        const requestGeneration = ++generation;
        form.reset(); clearErrors(); fields.disabled = true; save.disabled = true;
        document.getElementById('dialog-current-price').textContent = '';
        progress.textContent = form.dataset.loading; dialog.showModal();
        try {
            const response = await fetch(url(materialId), {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
            const data = await response.json();
            if (generation !== requestGeneration || !dialog.open) return;
            if (!response.ok) { showErrors(data); return; }
            document.getElementById('dialog-current-price').textContent = data.price == null ? form.dataset.unknown : data.price + ' ' + (data.currency || '');
            form.elements.price.value = data.price == null ? '' : data.price;
            form.elements.currency.value = data.currency || 'USD';
            form.elements.revision.value = data.revision;
            fields.disabled = false; save.disabled = false; form.elements.price.focus();
        } catch (_) { showErrors({}); }
        finally { progress.textContent = ''; }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || fields.disabled) return;
        clearErrors(); busy = true; save.disabled = true;
        const body = new FormData(form);
        fields.disabled = true;
        try {
            const response = await fetch(url(materialId), {method: 'POST', body, credentials: 'same-origin', headers: {'Accept': 'application/json'}});
            const data = await response.json();
            if (!response.ok) { showErrors(data); return; }
            const source = document.getElementById('material-stock-options');
            const stocks = JSON.parse(source.textContent);
            const stock = stocks.find(item => String(item.id) === materialId);
            if (stock) { stock.unit_price = data.price; stock.currency = data.currency; source.textContent = JSON.stringify(stocks); }
            document.dispatchEvent(new Event('entry-price-updated'));
            document.getElementById('price-saved').textContent = data.message;
            dialog.close();
        } catch (_) { showErrors({}); }
        finally { busy = false; fields.disabled = false; save.disabled = false; }
    });
})();
