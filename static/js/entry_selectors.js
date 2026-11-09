/* Progressive enhancement: the original selects remain the server authority. */
function enhanceEntrySelect(root, document) {
    const select = document.getElementById(root.dataset.selectId);
    const enhanced = root.querySelector('.entry-search-enhanced');
    const input = enhanced.querySelector('input');
    const list = enhanced.querySelector('[role="listbox"]');
    const status = enhanced.querySelector('[role="status"]');
    let matches = [], active = -1, editing = false;
    const labels = Array.from(select.labels || []);
    const errorLinks = Array.from(document.querySelectorAll('a[href="#' + select.id + '"]'));
    function pointLabels(native) {
        labels.forEach(label => label.htmlFor = native ? select.id : input.id);
        errorLinks.forEach(link => link.setAttribute('href', '#' + (native ? select.id : input.id)));
    }
    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.className = 'btn btn-tertiary entry-selector-toggle';
    toggle.textContent = root.dataset.native;
    root.append(toggle);
    function collapse() {
        list.hidden = true; input.setAttribute('aria-expanded', 'false');
        input.removeAttribute('aria-activedescendant'); active = -1;
    }
    function synchronize() {
        if (!editing) input.value = select.value ? select.selectedOptions[0]?.text || '' : '';
        input.setAttribute('aria-required', select.required ? 'true' : 'false');
        input.setAttribute('aria-invalid', select.getAttribute('aria-invalid') || 'false');
        const description = select.getAttribute('aria-describedby');
        if (description) input.setAttribute('aria-describedby', description);
        collapse();
    }
    function activate(index) {
        active = index;
        Array.from(list.children).forEach((item, position) => item.setAttribute('aria-selected', position === active ? 'true' : 'false'));
        const item = list.children[active];
        if (item) {
            input.setAttribute('aria-activedescendant', item.id);
            item.scrollIntoView?.({block: 'nearest'});
        }
    }
    function choose(index) {
        if (!matches[index]) return;
        select.value = matches[index].value;
        select.dispatchEvent(new Event('change', {bubbles:true}));
        input.focus(); collapse();
    }
    function render(all = false) {
        const query = all ? '' : input.value.trim().toLocaleLowerCase();
        const allMatches = Array.from(select.options).filter(option => option.value && !option.disabled && option.text.toLocaleLowerCase().includes(query));
        matches = allMatches.slice(0, 30);
        list.replaceChildren(); active = -1;
        matches.forEach((option, index) => {
            const item = document.createElement('li');
            item.id = select.id + '-option-' + index; item.role = 'option';
            item.textContent = option.text; item.setAttribute('aria-selected', 'false');
            item.addEventListener('mousedown', event => event.preventDefault());
            item.addEventListener('click', () => choose(index)); list.append(item);
        });
        if (!matches.length) {
            const item = document.createElement('li'); item.textContent = root.dataset.empty;
            item.setAttribute('aria-disabled', 'true'); list.append(item);
        }
        status.textContent = allMatches.length > 30 ? root.dataset.limited : matches.length ? root.dataset.count + ': ' + matches.length : root.dataset.empty;
        list.hidden = false; input.setAttribute('aria-expanded', 'true');
        input.removeAttribute('aria-activedescendant');
    }
    input.addEventListener('input', () => {
        editing = true; select.value = ''; select.dispatchEvent(new Event('change', {bubbles:true})); editing = false; render();
    });
    input.addEventListener('focus', () => render(true));
    input.addEventListener('blur', collapse);
    input.addEventListener('keydown', event => {
        if (event.key === 'Escape') { event.preventDefault(); collapse(); }
        else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault(); if (list.hidden) render(true);
            if (matches.length) activate(event.key === 'ArrowDown' ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1));
        } else if (event.key === 'Enter' && !list.hidden) { event.preventDefault(); choose(active < 0 ? 0 : active); }
        else if (event.key === 'Tab') collapse();
    });
    select.addEventListener('change', synchronize);
    toggle.addEventListener('click', () => {
        const native = select.hidden;
        select.hidden = !native; enhanced.hidden = native;
        pointLabels(native);
        toggle.textContent = native ? root.dataset.search : root.dataset.native;
        (native ? select : input).focus();
    });
    select.hidden = true; enhanced.hidden = false;
    pointLabels(false);
    synchronize();
    // Display the empty option as an empty query rather than placeholder dashes.
    if (!select.value) input.value = '';
    return {render, collapse};
}

function updateEntryStock(document) {
    const data = document.getElementById('material-stock-options');
    if (!data) return;
    let stocks = JSON.parse(data.textContent);
    document.addEventListener("entry-price-updated", () => { stocks = JSON.parse(data.textContent); update(); });
    const select = document.getElementById('id_material');
    const quantity = document.getElementById('id_quantity');
    const current = document.getElementById('current-stock');
    const estimate = document.getElementById('estimated-stock');
    const price = document.getElementById('current-material-price');
    function update() {
        const stock = stocks.find(item => String(item.id) === select.value);
        current.textContent = stock ? stock.stock_quantity + ' ' + stock.unit : '\u2014';
        if (price) {
            price.textContent = !stock ? '\u2014' : stock.unit_price == null
                ? price.dataset.unknown : stock.unit_price + ' ' + (stock.currency || '');
        }
        const raw = quantity.value.trim().replace(',', '.');
        const valid = /^(?:[0-9]+)(?:\.[0-9]{1,2})?$/.test(raw);
        const received = valid ? Math.round(Number(raw) * 100) : 0;
        const balance = stock ? Math.round(Number(stock.stock_quantity) * 100) : 0;
        estimate.textContent = stock && received > 0 ? ((balance + received) / 100).toFixed(2) + ' ' + stock.unit : '\u2014';
    }
    select.addEventListener('change', update); quantity.addEventListener('input', update); update();
}
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {enhanceEntrySelect, updateEntryStock};
} else {
    document.querySelectorAll('[data-search-select]').forEach(root => enhanceEntrySelect(root, document));
    updateEntryStock(document);
}
