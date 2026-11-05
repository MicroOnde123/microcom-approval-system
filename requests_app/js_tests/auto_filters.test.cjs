/* Dependency-free contract tests. Fake DOM tests do not replace browser testing. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../../static/js/auto_filters.js', 'utf8');

class Element {
    constructor() { this.listeners = {}; this.dataset = {}; this.attrs = {}; this.children = []; this.hidden = false; }
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
    dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    appendChild(node) { this.children.push(node); }
    querySelector() { return null; }
    querySelectorAll() { return []; }
    contains() { return false; }
}
function fixture() {
    const form = new Element(), results = new Element(), input = new Element(), select = new Element();
    form.method = 'get'; form.action = '/list/'; form.dataset.searchingLabel = 'Recherche';
    form.dataset.updatedLabel = 'Actualisé'; form.dataset.errorLabel = 'Réessayer';
    Object.assign(input, {name:'q', type:'search', tagName:'INPUT', value:''});
    Object.assign(select, {name:'status', type:'select-one', tagName:'SELECT', value:''});
    form.elements = [input, select];
    form.querySelectorAll = selector => selector.includes('input:not') ? form.elements : [];
    const document = new Element(), action = new Element(), button = new Element();
    button.disabled = false;
    action.querySelectorAll = () => [button];
    document.createElement = () => new Element();
    document.getElementById = id => id === 'live-filter-results' ? results : null;
    document.querySelectorAll = selector => selector.startsWith('form[') ? [form] : selector === '[data-filter-dependent]' ? [action] : [];
    const window = new Element(); window.location = new URL('https://example.invalid/list/');
    const history = [];
    window.history = Object.fromEntries(['pushState','replaceState'].map(method => [method, (state, unused, url) => {
        history.push({method,url}); window.location = new URL(url, window.location);
    }]));
    let assigned; window.location.assign = url => { assigned = url; };
    const requests = [], timers = new Map(); let timerID = 0;
    const fetch = (url, options) => new Promise((resolve, reject) => requests.push({url,options,resolve,reject}));
    class Parser {
        parseFromString(html) { return {getElementById: () => html === 'missing' ? null : {innerHTML:html,querySelector:()=>html==='validation'?{}:null}, querySelector:() => null}; }
    }
    class FormData { constructor() { this.values = form.elements.map(c => [c.name,c.value]); } [Symbol.iterator]() { return this.values[Symbol.iterator](); } }
    vm.runInNewContext(source, {document,window,fetch,URL,URLSearchParams,FormData,DOMParser:Parser,AbortController,
        CustomEvent:class {constructor(type, options) {this.type=type;Object.assign(this, options);}},
        setTimeout:fn => {timers.set(++timerID,fn);return timerID;},clearTimeout:id => timers.delete(id)});
    document.dispatchEvent({type:'DOMContentLoaded'});
    const emit = (node,type,extras={}) => {const event={type,preventDefault(){this.prevented=true;},...extras};node.dispatchEvent(event);return event;};
    const respond = async (index, html='new', extras={}) => {
        requests[index].resolve({ok:true,url:requests[index].url,redirected:false,headers:{get:()=> 'text/html'},text:async()=>html,...extras});
        await new Promise(resolve => setImmediate(resolve));
    };
    return {form,results,input,select,document,window,button,requests,timers,history,emit,respond,
        flush(){for(const fn of [...timers.values()])fn();timers.clear();},assigned:()=>assigned};
}
test('debounce coalesces typing and replaces history', async () => {
    const f=fixture();f.input.value='a';f.emit(f.input,'input');f.input.value='ab';f.emit(f.input,'input');
    assert.equal(f.timers.size,1);assert.equal(f.requests.length,0);f.flush();
    assert.equal(f.requests.length,1);await f.respond(0);assert.equal(f.history[0].method,'replaceState');
    assert.match(f.history[0].url,/q=ab/);assert.equal(f.results.attrs['aria-busy'],undefined);
});
test('stale response cannot replace the latest results', async () => {
    const f=fixture();f.emit(f.select,'change');f.select.value='APPROVED';f.emit(f.select,'change');
    assert.equal(f.requests[0].options.signal.aborted,true);await f.respond(1,'latest');await f.respond(0,'old');
    assert.equal(f.results.innerHTML,'latest');assert.equal(f.history.length,1);
});
test('typing invalidates a request before debounce fires', async () => {
    const f=fixture();f.emit(f.select,'change');f.input.value='new';f.emit(f.input,'input');await f.respond(0,'old');
    assert.notEqual(f.results.innerHTML,'old');f.flush();await f.respond(1,'new');assert.equal(f.results.innerHTML,'new');
});
test('back navigation cancels old debounce and restores controls', async () => {
    const f=fixture();f.input.value='old';f.emit(f.input,'input');f.window.location=new URL('https://example.invalid/list/?q=restored&page=2');
    f.emit(f.window,'popstate');assert.equal(f.timers.size,0);assert.equal(f.input.value,'restored');
    await f.respond(0);assert.equal(f.history.length,0);assert.match(f.requests[0].url,/page=2/);
});
for (const failure of ['http','json','missing','network']) test(failure+' failure hides stale results and enables normal GET fallback', async () => {
    const f=fixture();f.emit(f.select,'change');
    if(failure==='network'){f.requests[0].reject(new Error('offline'));await new Promise(r=>setImmediate(r));}
    else await f.respond(0,failure==='missing'?'missing':'new',failure==='http'?{ok:false}:failure==='json'?{headers:{get:()=> 'application/json'}}:{});
    assert.equal(f.results.hidden,true);assert.equal(f.form.children[0].textContent,'Réessayer');
    assert.equal(f.emit(f.form,'submit').prevented,undefined);assert.equal(f.results.attrs['aria-busy'],undefined);
});
test('pagination keeps filters and respects modified clicks', async () => {
    const f=fixture(), link={href:'https://example.invalid/list/?q=kept&page=2'};
    assert.equal(f.emit(f.results,'click',{ctrlKey:true,target:{closest:()=>link}}).prevented,undefined);
    f.emit(f.results,'click',{target:{closest:()=>link}});await f.respond(0);
    assert.match(f.requests[0].url,/q=kept&page=2/);assert.equal(f.history[0].method,'pushState');
});

test('shared history region refreshes archived attempts and preserves archived-page filters', async () => {
    const f=fixture();
    f.results.innerHTML='<table>current</table><section>old archived decisions</section>';
    f.input.value='no-match';f.emit(f.input,'input');f.flush();
    await f.respond(0,'<table>No approval history</table>');
    assert.doesNotMatch(f.results.innerHTML,/old archived decisions/);
    const link={href:'https://example.invalid/list/?q=kept&action=RETURNED&page=2&attempt_page=3'};
    f.emit(f.results,'click',{target:{closest:selector=>selector==='.request-list-pagination a'?link:null}});
    await f.respond(1,'<table>current</table><section>filtered archived page 3</section>');
    assert.match(f.results.innerHTML,/filtered archived page 3/);
    const url=new URL(f.requests[1].url);
    assert.equal(url.searchParams.get('q'),'kept');
    assert.equal(url.searchParams.get('action'),'RETURNED');
    assert.equal(url.searchParams.get('page'),'2');
    assert.equal(url.searchParams.get('attempt_page'),'3');
});
test('clear resets controls and uses unfiltered URL', async () => {
    const f=fixture();f.input.value='old';f.emit(f.form,'click',{target:{closest:selector=>selector==='[data-filter-reset]'?{href:'https://example.invalid/list/'}:null}});
    assert.equal(f.input.value,'');await f.respond(0);assert.equal(new URL(f.requests[0].url).search,'');
});
test('duplicate initialization does not duplicate listeners', () => {
    const f=fixture();f.document.dispatchEvent({type:'DOMContentLoaded'});f.emit(f.select,'change');assert.equal(f.requests.length,1);
});
test('IME input waits until composition finishes', () => {
    const f=fixture();f.emit(f.input,'input',{isComposing:true});assert.equal(f.timers.size,0);
    f.emit(f.input,'compositionend');assert.equal(f.timers.size,1);
});
test('bulk actions disabled while stale and restored after success', async () => {
    const f=fixture();f.emit(f.select,'change');assert.equal(f.button.disabled,true);
    await f.respond(0);assert.equal(f.button.disabled,false);
});
test('already-disabled bulk actions are not granted by a refresh', async () => {
    const f=fixture();f.button.disabled=true;f.emit(f.select,'change');await f.respond(0);
    assert.equal(f.button.disabled,true);
});
test('bulk actions remain disabled after a failed update', async () => {
    const f=fixture();f.emit(f.select,'change');await f.respond(0,'new',{ok:false});
    assert.equal(f.button.disabled,true);
});
test('server validation remains visible and keeps bulk actions disabled', async () => {
    const f=fixture();f.form.dataset.validationLabel='Review filters';f.emit(f.select,'change');await f.respond(0,'validation');
    assert.equal(f.results.hidden,false);assert.equal(f.button.disabled,true);
    assert.equal(f.form.children[0].textContent,'Review filters');
});
test('old redirects cannot navigate away after a newer request', async () => {
    const f=fixture();f.emit(f.select,'change');f.emit(f.select,'change');
    await f.respond(0,'login',{redirected:true,url:'https://example.invalid/login/'});
    assert.equal(f.assigned(),undefined);await f.respond(1);
});
test('keyboard pagination moves focus to the refreshed table', async () => {
    const f=fixture();let focused=false;f.results.contains=()=>true;
    f.results.querySelector=()=>({focus(){focused=true;}});
    f.emit(f.results,'click',{target:{closest:()=>({href:'https://example.invalid/list/?page=2'})}});
    await f.respond(0);assert.equal(focused,true);
});
function inlineScript(template) {
    const html=fs.readFileSync(__dirname+'/../../templates/'+template,'utf8');
    return [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match=>match[1]).join('\n');
}
test('material Select All uses the newly replaced checkboxes', () => {
    const document=new Element(),bulk=new Element();let boxes=[{checked:false},{checked:false}];
    let all={id:'select-all',checked:true,classList:{contains:()=>false}};
    bulk.contains=()=>true;bulk.querySelectorAll=()=>boxes;bulk.querySelector=()=>all;
    document.getElementById=()=>bulk;
    vm.runInNewContext(inlineScript('requests_app/material_reports.html'),{document});
    document.dispatchEvent({type:'change',target:all});assert.ok(boxes.every(box=>box.checked));
    boxes=[{checked:false},{checked:false},{checked:false}];all={id:'select-all',checked:true,classList:{contains:()=>false}};
    document.dispatchEvent({type:'change',target:all});assert.ok(boxes.every(box=>box.checked));
    assert.equal(document.listeners.change.length,1);
});
test('invoice print hidden fields track current filters and never page', () => {
    const document=new Element(),form=new Element(),print=new Element(),hidden=new Element(),window=new Element();
    let values=[['q','first'],['date_from','2026-10-01'],['date_to','2026-10-31'],['page','2']];
    hidden.replaceChildren=()=>{hidden.children=[];};
    document.getElementById=id=>({'invoice-filter-form':form,'invoice-bulk-print-form':print,'invoice-print-filters':hidden}[id]);
    document.createElement=()=>new Element();window.setTimeout=fn=>fn();
    class FormData {entries(){return values.values();}}
    vm.runInNewContext(inlineScript('invoicing/list.html'),{document,window,FormData});
    document.dispatchEvent({type:'DOMContentLoaded'});
    assert.equal(hidden.children.some(c=>c.name==='page'),false);
    values[0]=['q','restored'];form.dispatchEvent({type:'auto-filters:updated'});
    assert.equal(hidden.children.find(c=>c.name==='q').value,'restored');
    values[0]=['q','latest'];print.dispatchEvent({type:'submit'});
    assert.equal(hidden.children.find(c=>c.name==='q').value,'latest');
});
test('material exports and bulk return URL use visible filters after updates', () => {
    const document=new Element(),form=new Element(),bulk=new Element(),next={},window=new Element();
    const csv={href:'https://example.invalid/export.csv'},excel={href:'https://example.invalid/export.xlsx'};
    let values=[['q','first'],['date_from','2026-10-01']];
    document.getElementById=id=>({'material-bulk-print-form':bulk,'material-export-csv':csv,'material-export-excel':excel}[id]);
    document.querySelector=()=>form;bulk.querySelector=()=>next;
    window.location=new URL('https://example.invalid/materials/?q=old');window.setTimeout=fn=>fn();
    class FormData {[Symbol.iterator](){return values.values();}}
    vm.runInNewContext(inlineScript('requests_app/material_reports.html'),{document,window,FormData,URL,URLSearchParams});
    document.dispatchEvent({type:'DOMContentLoaded'});
    values[0]=['q','new'];form.dispatchEvent({type:'auto-filters:updated'});
    assert.match(csv.href,/q=new/);assert.match(excel.href,/date_from=2026-10-01/);
    assert.equal(next.value,'/materials/?q=new&date_from=2026-10-01');
});
