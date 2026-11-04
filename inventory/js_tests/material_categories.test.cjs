const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../../static/js/material_categories.js'), 'utf8');

function setup(fetchRequest) {
    const nodes = new Map();
    const document = {getElementById: id => nodes.get(id), createElement: tag => element(tag)};
    function element(id, value = '') {
        const result = {id, value, textContent: '', hidden: false, disabled: false, attributes: {}, children: [], listeners: {},
            addEventListener(type, callback) { this.listeners[type] = callback; },
            dispatchEvent(event) { return this.listeners[event.type]?.(event); },
            setAttribute(key, value) { this.attributes[key] = value; },
            removeAttribute(key) { delete this.attributes[key]; },
            append(child) { this.children.push(child); },
            replaceChildren() { this.children = []; },
            focus() { document.activeElement = this; }
        };
        nodes.set(id, result); return result;
    }
    for (const id of ['new-category', 'category-save', 'category-fields', 'category-errors', 'category-progress', 'category-created']) element(id);
    const dialog = element('category-dialog');
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => { dialog.open = false; dialog.listeners.close?.(); };
    const close = element('cancel-category'); dialog.querySelectorAll = () => [close];
    const form = element('category-form');
    const inputs = new Map();
    for (const [name, value] of [['name', 'Cables'], ['code', 'CABLES'], ['description', 'Network'], ['csrfmiddlewaretoken', 'csrf-token']]) {
        const key = name === 'csrfmiddlewaretoken' ? name : 'category-' + name;
        inputs.set(key, element('id_' + key, value));
        element('id_' + key + '-errors');
    }
    form.elements = {namedItem: key => inputs.get(key)};
    form.action = '/materials/categories/create/';
    form.dataset = {failure: 'Please retry', saving: 'Saving', success: 'Created and selected'};
    form.reset = () => { for (const input of inputs.values()) input.value = ''; };
    const select = element('id_category'); select.options = [];
    select.add = option => select.options.push(option);
    // These model the separate material/stock form and must survive every dialog operation.
    const main = {};
    for (const [name, value] of Object.entries({name: 'Cable', code: 'CAB', unit: 'm', description: 'Cable description', minimum_stock_level: '3', unit_price: '9.50', currency: 'EUR', is_active: 'on', quantity: '12.50', received_on: '2026-11-03', supplier: 'Vendor', delivery_reference: 'DEL-1', notes: 'Keep me', token: 'receipt-token'})) {
        main[name] = element('id_' + name, value);
    }
    class FormData {
        constructor(target) {
            assert.equal(target, form, 'Only the category form may be submitted');
            this.values = Object.fromEntries([...inputs].map(([key, input]) => [key, input.value]));
        }
    }
    const module = {exports: {}};
    vm.runInNewContext(source, {module, FormData, Option: function(text, value) { this.text = text; this.value = value; }, Event});
    module.exports.initMaterialCategories(document, fetchRequest);
    const click = target => target.listeners.click();
    const submit = () => form.listeners.submit({preventDefault() {}});
    const snapshot = () => Object.fromEntries(Object.entries(main).map(([key, input]) => [key, input.value]));
    return {nodes, document, form, dialog, select, inputs, click, submit, snapshot, close};
}
const success = (id = 7, name = 'Cables') => ({ok: true, json: async () => ({category: {id, name}})});

test('creation selects the new category while preserving all material and stock values', async () => {
    let request;
    const page = setup(async (url, options) => { request = {url, options}; return success(); });
    const before = page.snapshot();
    page.click(page.nodes.get('new-category'));
    assert.equal(page.dialog.open, true);
    assert.equal(page.document.activeElement, page.inputs.get('category-name'));
    await page.submit();
    assert.equal(page.select.value, '7');
    assert.equal(page.select.options.length, 1);
    assert.equal(page.dialog.open, false);
    assert.deepEqual(page.snapshot(), before);
    assert.equal(request.options.method, 'POST');
    assert.equal(request.options.body.values.csrfmiddlewaretoken, 'csrf-token');
    assert.equal(request.options.body.values.quantity, undefined);
    assert.equal(page.nodes.get('category-created').textContent, 'Created and selected');
});

test('repeated clicks produce one in-flight request and retries do not duplicate dropdown options', async () => {
    let resolve, calls = 0;
    const page = setup(() => { calls++; return new Promise(done => { resolve = done; }); });
    const first = page.submit();
    assert.equal(page.nodes.get('category-save').disabled, true);
    await page.submit(); assert.equal(calls, 1);
    resolve(success()); await first;
    const retry = page.submit(); resolve(success()); await retry;
    assert.equal(page.select.options.length, 1);
    assert.equal(page.nodes.get('category-save').disabled, false);
});

test('field errors stay visible and focused without losing either form', async () => {
    const page = setup(async () => ({ok: false, json: async () => ({errors: {code: ['Code already exists']}})}));
    const before = page.snapshot();
    page.click(page.nodes.get('new-category')); await page.submit();
    const input = page.inputs.get('category-code');
    assert.equal(page.dialog.open, true);
    assert.equal(input.attributes['aria-invalid'], 'true');
    assert.equal(page.document.activeElement, input);
    assert.equal(page.nodes.get(input.id + '-errors').children[0].textContent, 'Code already exists');
    assert.equal(page.inputs.get('category-name').value, 'Cables');
    assert.deepEqual(page.snapshot(), before);
    assert.equal(page.nodes.get('category-fields').disabled, false);
});

test('network failures permit retry, and category names are inserted as text', async () => {
    let calls = 0;
    const page = setup(async () => { if (++calls === 1) throw Error('offline'); return success(9, '<img onerror=alert(1)>'); });
    const before = page.snapshot(); await page.submit();
    assert.equal(page.nodes.get('category-errors').textContent, 'Please retry');
    assert.equal(page.nodes.get('category-save').disabled, false);
    assert.equal(page.inputs.get('category-code').value, 'CABLES');
    await page.submit();
    assert.equal(page.select.options[0].text, '<img onerror=alert(1)>');
    assert.deepEqual(page.snapshot(), before);
});

test('cancel restores trigger focus and preserves unfinished category and material values', () => {
    const page = setup(() => { throw Error('No request expected'); });
    const before = page.snapshot();
    page.click(page.nodes.get('new-category')); page.click(page.close);
    assert.equal(page.dialog.open, false);
    assert.equal(page.document.activeElement, page.nodes.get('new-category'));
    page.click(page.nodes.get('new-category'));
    assert.equal(page.inputs.get('category-code').value, 'CABLES');
    assert.deepEqual(page.snapshot(), before);
});
