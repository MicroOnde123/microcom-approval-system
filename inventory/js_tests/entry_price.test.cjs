const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup() {
    let focused, requests = [], events = [];
    function element(value='') { return {value, textContent:'', disabled:false, listeners:{}, children:[],
        addEventListener(name, fn){this.listeners[name]=fn;},
        focus(){focused=this;}, setAttribute(){}, removeAttribute(){},
        replaceChildren(){this.children=[];}, append(child){this.children.push(child);}}; }
    const names=['entry-price-form','entry-price-dialog','modify-material-price','id_material',
        'entry-price-fields','entry-price-save','entry-price-errors','entry-price-progress',
        'entry-price-cancel','dialog-current-price','material-stock-options','price-saved'];
    const nodes=Object.fromEntries(names.map(name=>[name,element()]));
    const form=nodes['entry-price-form'];
    form.dataset={url:'/materials/entries/prices/0/',failure:'Save failed',loading:'Loading',unknown:'Unknown'};
    form.elements={price:element(),currency:element(),reason:element(),revision:element()};
    form.elements.namedItem=name=>form.elements[name];
    form.querySelectorAll=()=>[];
    form.reset=()=>Object.values(form.elements).forEach(item=>{if(typeof item==='object')item.value='';});
    const dialog=nodes['entry-price-dialog'];
    dialog.showModal=()=>{dialog.open=true;};
    dialog.close=()=>{dialog.open=false;dialog.listeners.close();};
    nodes.id_material.value='1';
    nodes['material-stock-options'].textContent=JSON.stringify([{id:1,unit_price:'2.00',currency:'USD'}]);
    const document={getElementById:id=>nodes[id],createElement:()=>element(),dispatchEvent:event=>events.push(event.type)};
    let respond=async (url,options)=>({ok:true,json:async()=>options?.method==='POST'?
        {price:'3.00',currency:'EUR',message:'Price saved'}:{price:'2.00',currency:'USD',revision:'signed-revision'}});
    class FormData {constructor(form){this.values=Object.fromEntries(Object.entries(form.elements).filter(([,v])=>typeof v==='object').map(([k,v])=>[k,v.value]));}}
    const context={document,Event,FormData,fetch:async(url,options)=>{requests.push({url,options});return respond(url,options);}};
    vm.runInNewContext(fs.readFileSync('static/js/entry_price.js','utf8'),context);
    return {nodes,form,requests,events,get focused(){return focused;},set respond(value){respond=value;}};
}
test('independent price save preserves entered receipt values and updates authoritative display', async()=>{
    const s=setup(), receipt={quantity:'5',supplier:'Supplier',reference:'REF',notes:'Unfinished',draft_id:'42',version:'3'};
    const before=JSON.stringify(receipt);
    await s.nodes['modify-material-price'].listeners.click();
    assert.equal(s.focused,s.form.elements.price);
    assert.equal(s.form.elements.revision.value,'signed-revision');
    s.form.elements.price.value='3';s.form.elements.currency.value='EUR';s.form.elements.reason.value='Correction';
    await s.form.listeners.submit({preventDefault(){}});
    assert.equal(s.requests.length,2);
    const post=s.requests[1];assert.equal(post.url,'/materials/entries/prices/1/');
    assert.deepEqual(Object.keys(post.options.body.values).sort(),['currency','price','reason','revision']);
    assert.equal(JSON.stringify(receipt),before);
    assert.equal(s.nodes['entry-price-dialog'].open,false);
    assert.equal(s.focused,s.nodes['modify-material-price']);
    assert.equal(s.nodes['price-saved'].textContent,'Price saved');
    assert.deepEqual(s.events,['entry-price-updated']);
    assert.equal(JSON.parse(s.nodes['material-stock-options'].textContent)[0].unit_price,'3.00');
});
test('cancel and Escape support; missing selection disables edit',async()=>{
    const s=setup();s.nodes.id_material.value='';s.nodes.id_material.listeners.change();
    assert.equal(s.nodes['modify-material-price'].disabled,true);
    s.nodes.id_material.value='1';s.nodes.id_material.listeners.change();
    await s.nodes['modify-material-price'].listeners.click();
    s.nodes['entry-price-cancel'].listeners.click();
    assert.equal(s.nodes['entry-price-dialog'].open,false);
    assert.equal(s.requests.length,1);
    let prevented=false;s.nodes['entry-price-dialog'].listeners.cancel({preventDefault(){prevented=true;}});
    assert.equal(prevented,false);
});
test('repeated submit is blocked while saving and validation errors stay visible',async()=>{
    const s=setup();await s.nodes['modify-material-price'].listeners.click();
    let finish;s.respond=()=>new Promise(resolve=>{finish=resolve;});
    const first=s.form.listeners.submit({preventDefault(){}});
    await s.form.listeners.submit({preventDefault(){}});
    assert.equal(s.requests.length,2);
    let prevented=false;s.nodes['entry-price-dialog'].listeners.cancel({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);
    finish({ok:false,json:async()=>({errors:{reason:['Reason required']}})});await first;
    assert.equal(s.nodes['entry-price-dialog'].open,true);
    assert.equal(s.nodes['entry-price-errors'].children[0].textContent,'Reason required');
    assert.equal(s.focused,s.nodes['entry-price-errors']);
    assert.equal(s.nodes['entry-price-save'].disabled,false);
});
