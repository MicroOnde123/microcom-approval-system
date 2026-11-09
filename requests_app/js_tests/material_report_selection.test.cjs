const {test} = require('node:test');
const assert = require('node:assert/strict');
const {reportSelectionState,initializeReportSelection} = require('../../static/js/material_report_selection.js');
const scope='q=&date_from=&date_to=&department=&status=';
function storage(){const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)};}
function ui(store=storage(), labels={}) {
    const oldFormData=global.FormData;
    global.FormData=class {constructor(form){this.fields=form.fields;}get(name){return this.fields[name]||'';}};
    function element(){return {listeners:{},children:[],dataset:{},textContent:'',addEventListener(n,fn){this.listeners[n]=fn;},replaceChildren(){this.children=[];},append(item){this.children.push(item);}};}
    const bulk=element(),filter=element(),marker=element(),counter=element(),notice=element(),hidden=element(),clear=element(),all={id:'select-all',checked:false};
    let boxes=[];
    marker.dataset={context:'session-A',scope};counter.dataset.label='%(count)s requests selected';notice.dataset.cleared='Selection cleared';filter.fields={};
    Object.assign(counter.dataset, labels);
    const nodes={'material-bulk-print-form':bulk,'report-selection-context':marker,'report-selection-count':counter,'report-selection-notice':notice,'report-selected-inputs':hidden,'report-clear-selection':clear};
    const document={getElementById:id=>nodes[id],querySelector:()=>filter,createElement:()=>element()};
    bulk.querySelectorAll=()=>boxes;bulk.querySelector=()=>all;
    const window=element();window.sessionStorage=store;window.location={search:''};
    const state=initializeReportSelection(document,window);
    function page(ids){boxes=ids.map(id=>({value:String(id),checked:false,classList:{contains:n=>n==='request-checkbox'}}));filter.listeners['auto-filters:updated']({detail:{phase:'success'}});}
    function select(id,checked=true){const target=boxes.find(b=>b.value===String(id));target.checked=checked;bulk.listeners.change({target});}
    return {state,bulk,filter,window,counter,notice,hidden,all,clear,marker,page,select,get boxes(){return boxes;},cleanup(){global.FormData=oldFormData;}};
}
test('selection persists over three pages, returns, deselection and explicit deduplicated submission',()=>{
    const u=ui();try{
        u.page([1,2]);u.select(1);u.page([26,27]);u.select(26);u.page([51,52]);u.select(51);
        assert.equal(u.counter.textContent,'3 requests selected');
        u.page([1,2]);assert.equal(u.boxes[0].checked,true);u.select(1,false);
        assert.deepEqual(u.state.values(),['26','51']);
        u.page([26,27]);u.select(26);u.bulk.listeners.submit({preventDefault(){throw Error('Unexpected block');}});
        assert.deepEqual(u.hidden.children.map(c=>c.value),['51']);
        assert.equal(u.boxes[0].checked,true);
    }finally{u.cleanup();}
});
test('Select All affects current page only; Clear Selection empties every page',()=>{
    const u=ui();try{
        u.page([1,2]);u.all.checked=true;u.bulk.listeners.change({target:u.all});
        u.page([26,27]);assert.equal(u.all.checked,false);assert.equal(u.counter.textContent,'2 requests selected');
        u.select(26);u.page([1,2]);assert.equal(u.all.checked,true);
        u.clear.listeners.click();assert.deepEqual(u.state.values(),[]);assert.equal(u.all.checked,false);
    }finally{u.cleanup();}
});
test('filter edits clear selection immediately and announce; stale results cannot be submitted',()=>{
    const u=ui();try{
        u.page([1]);u.select(1);u.filter.fields.q='Cable';u.filter.listeners.input();
        assert.equal(u.counter.textContent,'0 requests selected');assert.equal(u.notice.textContent,'Selection cleared');
        u.filter.listeners['auto-filters:updated']({detail:{phase:'loading'}});
        let prevented=false;u.bulk.listeners.submit({preventDefault(){prevented=true;}});assert.equal(prevented,true);
        u.marker.dataset.scope='q=Cable&date_from=&date_to=&department=&status=';
        u.page([26]);assert.equal(u.boxes[0].checked,false);
    }finally{u.cleanup();}
});
test('Back/Forward within scope restores checkbox state; another filter scope clears it',()=>{
    const u=ui();try{
        u.page([1]);u.select(1);u.page([26]);u.select(26);
        u.window.location.search='?page=1';u.window.listeners.popstate();u.page([1]);assert.equal(u.boxes[0].checked,true);
        u.window.location.search='?page=2';u.window.listeners.popstate();u.page([26]);assert.equal(u.boxes[0].checked,true);
        u.window.location.search='?q=Other';u.window.listeners.popstate();assert.equal(u.state.values().length,0);
    }finally{u.cleanup();}
});
test('reload/BFCache restoration is scoped to login context and tab storage',()=>{
    const store=storage();let state=reportSelectionState(store,'session-A',scope);state.set('1',true);state.set('1',true);
    state=reportSelectionState(store,'session-A',scope);assert.deepEqual(state.values(),['1']);
    assert.deepEqual(reportSelectionState(storage(),'session-A',scope).values(),[]);
    assert.deepEqual(reportSelectionState(store,'session-B',scope).values(),[]);
    state.set('2',true);assert.deepEqual(reportSelectionState(store,'session-A','q=Other').values(),[]);
});
test('date/status/department scope changes clear IDs and corrupt storage is ignored',()=>{
    const store=storage();for(const next of ['date_from=2026-01-01','date_to=2026-02-01','status=APPROVED','department=2']){
        const state=reportSelectionState(store,'session-A',scope);state.set('1',true);assert.equal(state.changeScope(next),true);assert.deepEqual(state.values(),[]);
    }
    store.setItem('microcom.materialReportSelection','invalid');assert.deepEqual(reportSelectionState(store,'session-A',scope).values(),[]);
});

test('a new tab with cloned sessionStorage does not inherit the original selection',()=>{
    const firstStore=storage();const a=ui(firstStore);
    try{
        a.page([1]);a.select(1);
        const cloned=storage();cloned.setItem('microcom.materialReportSelection',firstStore.getItem('microcom.materialReportSelection'));
        const b=ui(cloned);try{b.page([1]);assert.equal(b.boxes[0].checked,false);assert.equal(b.state.values().length,0);assert.deepEqual(a.state.values(),['1']);}finally{b.cleanup();}
    }finally{a.cleanup();}
});

if (process.env.REPORT_COUNTER_TRANSLATION) test('rendered Django counter labels support zero, one and multiple selections',()=>{
    const {labels,expected}=JSON.parse(process.env.REPORT_COUNTER_TRANSLATION);
    const u=ui(storage(),labels);
    try {
        assert.equal(u.counter.textContent,expected[0]);
        u.page([1,2,3]);u.select(1);assert.equal(u.counter.textContent,expected[1]);
        u.select(2);u.select(3);assert.equal(u.counter.textContent,expected[2]);
        u.clear.listeners.click();assert.equal(u.counter.textContent,expected[0]);
    } finally {u.cleanup();}
});
