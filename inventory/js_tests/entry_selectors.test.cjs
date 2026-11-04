const {test} = require('node:test');
const assert = require('node:assert/strict');
const {enhanceEntrySelect, updateEntryStock} = require('../../static/js/entry_selectors.js');
function setup(id = 'id_material') {
    const document = {activeElement:null, querySelectorAll:()=>[]};
    function element() {
        return {children:[], hidden:false, attributes:{}, listeners:{}, value:'',
            addEventListener(type, fn) { this.listeners[type] = fn; },
            dispatchEvent(event) { this.listeners[event.type]?.(event); },
            setAttribute(name, value) { this.attributes[name] = value; },
            getAttribute(name) { return this.attributes[name] || null; },
            removeAttribute(name) { delete this.attributes[name]; },
            append(item) { this.children.push(item); }, replaceChildren() { this.children = []; },
            focus() { document.activeElement=this; }, scrollIntoView() {}}
    }
    document.createElement = element;
    const select=element(), input=element(), list=element(), status=element(), root=element(), enhanced=element();
    select.id=id; select.required=true; select.labels=[{htmlFor:id}];
    select.options=[{value:'',text:'--------'}, {value:'1',text:'Cable (CAB-1) - 10.00 m'}, {value:'2',text:'Bolts (BOLT-2) - 4.00 pcs'}];
    Object.defineProperty(select,'selectedOptions',{get() { return select.options.filter(item=>item.value===select.value); }});
    root.dataset={selectId:id,empty:'No matching results.',count:'Matching results',native:'Standard',search:'Search'};
    root.querySelector=()=>enhanced;
    enhanced.querySelector=selector=>selector==='input'?input:selector==='[role="listbox"]'?list:status;
    document.getElementById=()=>select;
    enhanceEntrySelect(root,document);
    const key=key=>input.listeners.keydown({key,preventDefault(){}});
    const search=value=>{input.value=value;input.listeners.input();};
    return {document,root,enhanced,select,input,list,status,key,search};
}
test('searches material name or code and selects with ArrowDown/Enter',()=>{
    const p=setup();p.search('CAB-1');
    assert.equal(p.list.children.length,1);
    p.key('ArrowDown');
    assert.equal(p.input.attributes['aria-activedescendant'],'id_material-option-0');
    p.key('Enter');assert.equal(p.select.value,'1');
    assert.match(p.input.value,/Cable/);assert.equal(p.list.hidden,true);
    p.search('Bolts');p.key('ArrowDown');p.key('Enter');assert.equal(p.select.value,'2');
});
test('ArrowUp wraps, Escape and Tab dismiss, and no-result selection is empty',()=>{
    const p=setup();p.input.listeners.focus();p.key('ArrowUp');p.key('Enter');assert.equal(p.select.value,'2');
    p.search('missing');assert.equal(p.select.value,'');assert.equal(p.status.textContent,'No matching results.');
    p.key('Enter');assert.equal(p.select.value,'');p.key('Escape');assert.equal(p.list.hidden,true);
    p.search('Cable');p.key('Tab');assert.equal(p.list.hidden,true);
});
test('native fallback is keyboard accessible and reflects selection',()=>{
    const p=setup();assert.equal(p.select.hidden,true);
    const toggle=p.root.children[0];toggle.listeners.click();
    assert.equal(p.select.hidden,false);assert.equal(p.enhanced.hidden,true);
    assert.equal(p.document.activeElement,p.select);
    p.select.value='2';p.select.dispatchEvent(new Event('change'));toggle.listeners.click();
    assert.equal(p.enhanced.hidden,false);assert.match(p.input.value,/Bolts/);
});
test('newly created categories are immediately searchable and selected without resetting other fields',()=>{
    const p=setup('id_category');
    p.select.options.push({value:'3',text:'Network equipment'});
    p.select.value='3';p.select.dispatchEvent(new Event('change'));
    assert.equal(p.input.value,'Network equipment');
    p.search('network');p.key('ArrowDown');p.key('Enter');assert.equal(p.select.value,'3');
});
test('stock previews use hundredths and clear invalid or absent quantities',()=>{
    const select={value:'1',addEventListener(type,fn){this.change=fn;}};
    const quantity={value:'0.20',addEventListener(type,fn){this.input=fn;}};
    const current={},estimate={};
    const nodes={'material-stock-options':{textContent:JSON.stringify([{id:1,stock_quantity:'0.10',unit:'m'}])},id_material:select,id_quantity:quantity,'current-stock':current,'estimated-stock':estimate};
    updateEntryStock({getElementById:id=>nodes[id]});
    assert.equal(current.textContent,'0.10 m');assert.equal(estimate.textContent,'0.30 m');
    quantity.value='-1';quantity.input();assert.equal(estimate.textContent,'\u2014');
    quantity.value='1.001';quantity.input();assert.equal(estimate.textContent,'\u2014');
    select.value='';select.change();assert.equal(current.textContent,'\u2014');
});
