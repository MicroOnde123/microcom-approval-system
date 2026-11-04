const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseEntryDate, isoEntryDate, formatEntryDate, shiftEntryMonth, enhanceEntryDate} = require('../../static/js/entry_dates.js');

test('ISO and French dates round-trip without timezone or language ambiguity', () => {
    for (const value of ['2024-02-29', '29/02/2024']) {
        const date = parseEntryDate(value);
        assert.equal(isoEntryDate(date), '2024-02-29');
        assert.equal(formatEntryDate(date, 'fr'), '29/02/2024');
        assert.equal(formatEntryDate(date, 'en'), '2024-02-29');
    }
    assert.equal(isoEntryDate(parseEntryDate('0001-01-01')), '0001-01-01');
    for (const value of ['', 'bad', '31/02/2026', '2025-02-29', '2026-13-01', '0000-01-01', '2026-01-00']) {
        assert.equal(parseEntryDate(value), null, value);
    }
});

test('calendar month navigation clamps month-end and handles leap years', () => {
    assert.equal(isoEntryDate(shiftEntryMonth(parseEntryDate('2024-01-31'), 1)), '2024-02-29');
    assert.equal(isoEntryDate(shiftEntryMonth(parseEntryDate('2026-03-31'), -1)), '2026-02-28');
    assert.equal(isoEntryDate(shiftEntryMonth(parseEntryDate('2026-12-31'), 1)), '2027-01-31');
});

function fixture(language='fr') {
    const document = {activeElement: null};
    function element() {
        return {value:'', children:[], dataset:{}, attributes:{}, listeners:{}, hidden:true,
            addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
            dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); },
            setAttribute(key, value) { this.attributes[key] = value; if (key === 'tabindex') this.tabIndex = Number(value); },
            append(child) { this.children.push(child); }, replaceChildren() { this.children = []; },
            querySelector() { return this.children.find(child => child.tabIndex === 0); },
            focus() { document.activeElement = this; },
            click() { this.dispatchEvent({type:'click'}); }};
    }
    document.createElement = element;
    const input=element(), dialog=element(), open=element(), days=element(), label=element(), close=element();
    const previous=element(), next=element(), form=element();
    previous.dataset.month='-1'; next.dataset.month='1';
    input.value=language === 'fr' ? '03/11/2026' : '2026-11-03'; input.form=form; input.name='received_on';
    dialog.showModal=()=>{dialog.open=true;};
    dialog.close=()=>{dialog.open=false;dialog.dispatchEvent({type:'close'});};
    const root={dataset:{language}, querySelector:selector=>({input,dialog,'.entry-calendar-open':open,'.entry-calendar-days':days,'[data-month-label]':label,'[data-calendar-close]':close})[selector], querySelectorAll:()=>[previous,next]};
    enhanceEntryDate(root,document);
    return {document,input,dialog,open,days,label,close,previous,next,form};
}

function key(element, key) {
    let prevented = false;
    element.dispatchEvent({type:'keydown',key,preventDefault(){prevented=true;}});
    assert.equal(prevented, true);
}

test('calendar supports arrow keys, month navigation, selection and focus return', () => {
    const f=fixture(); f.open.click();
    assert.equal(f.dialog.open,true);
    assert.equal(f.document.activeElement.dataset.day,'3');
    key(f.document.activeElement,'ArrowRight');
    assert.equal(f.document.activeElement.dataset.day,'4');
    key(f.document.activeElement,'ArrowDown');
    assert.equal(f.document.activeElement.dataset.day,'11');
    key(f.document.activeElement,'PageUp');
    assert.match(f.label.textContent,/octobre/);
    key(f.document.activeElement,'Home');
    assert.equal(f.document.activeElement.dataset.day,'5');
    key(f.document.activeElement,'End');
    assert.equal(f.document.activeElement.dataset.day,'11');
    f.document.activeElement.click();
    assert.equal(f.input.value,'11/10/2026');
    assert.equal(f.dialog.open,false);
    assert.equal(f.document.activeElement,f.input);
    f.open.click(); f.close.click();
    assert.equal(f.document.activeElement,f.open);
});

test('submission uses ISO while leaving visible and invalid entered values intact', () => {
    for(const language of ['en','fr']) {
        const f=fixture(language), data=new Map();
        const original=f.input.value;
        f.form.dispatchEvent({type:'formdata',formData:data});
        assert.equal(data.get('received_on'),'2026-11-03');
        assert.equal(f.input.value,original);
        f.input.value='31/02/2026';data.set('received_on',f.input.value);
        f.form.dispatchEvent({type:'formdata',formData:data});
        assert.equal(data.get('received_on'),'31/02/2026');
    }
});
