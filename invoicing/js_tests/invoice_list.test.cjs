const {test}=require('node:test');
const assert=require('node:assert/strict');
Object.assign(global, require('../../static/js/entry_dates.js'));
const {normalizeInvoiceDates,synchronizeInvoicePrintFilters}=require('../../static/js/invoice_list.js');
test('restored ISO dates are localized for French and preserved for English',()=>{
 for(const language of ['en','fr']) {
  const input={value:'2026-11-07'};
  const root={dataset:{language},querySelector:()=>input};
  normalizeInvoiceDates({querySelectorAll:()=>[root]});
  assert.equal(input.value,language==='fr'?'07/11/2026':'2026-11-07');
  input.value='invalid'; normalizeInvoiceDates({querySelectorAll:()=>[root]}); assert.equal(input.value,'invalid');
 }
});
test('printing synchronizes ISO dates and invoice filters without candidate selection or page',()=>{
 const original=global.FormData;
 const values=new original();
 for(const [key,value] of Object.entries({date_from:'01/11/2026',date_to:'07/11/2026',q:'FAC',status:'FINALIZED',candidate_q:'private-selection',page:'2'})) values.set(key,value);
 global.FormData=class {constructor(){return values;}};
 try {
  const target={items:[],replaceChildren(){this.items=[];},appendChild(node){this.items.push(node);}};
  synchronizeInvoicePrintFilters({},target,{createElement:()=>({})});
  assert.deepEqual(Object.fromEntries(target.items.map(x=>[x.name,x.value])),{date_from:'2026-11-01',date_to:'2026-11-07',q:'FAC',status:'FINALIZED'});
 } finally {global.FormData=original;}
});
