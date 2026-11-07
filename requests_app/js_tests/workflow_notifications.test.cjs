const {test}=require('node:test');
const assert=require('node:assert/strict');
const {start,INTERVAL}=require('../../static/js/workflow_notifications.js');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture() {
 const listeners={}, timers=new Map(), window={location:{href:'http://localhost/approvals/pending/'},
  setTimeout(fn,ms){const key=Symbol();timers.set(key,{fn,ms});return key;},clearTimeout(key){timers.delete(key);}};
 const element=()=>({textContent:'',innerHTML:'',style:{},hidden:false,contains(){return false;},listeners:{},addEventListener(n,fn){this.listeners[n]=fn;}});
 const nodes=Object.fromEntries(['workflow-notification-menu','recent-notification-filter','notification-live-status','notification-unread-count','pending-approval-count','returned-request-count','recent-notification-items'].map(id=>[id,element()]));
 nodes['recent-notification-filter'].value='all';
 const fieldset={}, handled=element(), approval={dataset:{liveApprovalId:'7'},querySelector(){return fieldset;}};
 let updates=0;
 const document={hidden:false,activeElement:null,getElementById:id=>nodes[id],querySelector:selector=>selector==='[data-live-approval-id]'?approval:handled,
  querySelectorAll:()=>[{dispatchEvent(){updates++;}}],addEventListener(name,fn){(listeners[name]??=[]).push(fn);}};
 const calls=[]; let data={unread:2,pending:1,returned:0,html:'safe server markup',approval_active:true};
 const fetcher=async(url,options)=>{calls.push({url,options});return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>data};};
 const config={url:'/notifications/live/',error:'Refresh failed',handled:'Already handled'};
 const api=start(document,window,fetcher,config);
 return {api,document,window,nodes,listeners,timers,calls,fieldset,handled,config,fetcher,get updates(){return updates;},set data(value){data=value;}};
}
test('one five-second loop updates unread and actionable counts separately without marking read',async()=>{
 const f=fixture();await settle();assert.equal(INTERVAL,5000);
 assert.equal(f.nodes['notification-unread-count'].textContent,'2');assert.equal(f.nodes['pending-approval-count'].textContent,'1');
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].options.method,undefined);
 assert.equal(f.timers.size,1);assert.equal([...f.timers.values()][0].ms,5000);
 assert.equal(start(f.document,f.window,f.fetcher,f.config),f.api);assert.equal(f.calls.length,1);
 assert.equal(f.listeners.visibilitychange.length,1);assert.equal(f.listeners.submit.length,1);
});
test('hidden tabs pause and becoming visible refreshes immediately; shared decisions disable actions',async()=>{
 const f=fixture();await settle();f.document.hidden=true;f.listeners.visibilitychange[0]();assert.equal(f.timers.size,0);
 f.data={unread:2,pending:0,returned:0,html:'Already handled',approval_active:false};
 f.document.hidden=false;f.listeners.visibilitychange[0]();await settle();
 assert.equal(f.calls.length,2);assert.equal(f.fieldset.disabled,true);assert.equal(f.handled.textContent,'Already handled');
 assert.equal(f.nodes['notification-unread-count'].textContent,'2');assert.equal(f.nodes['pending-approval-count'].hidden,true);
 assert.equal(f.updates,2);
});
test('opening the menu and filtering are GET-only and preserve focused notification controls',async()=>{
 const f=fixture();await settle();f.nodes['recent-notification-items'].contains=()=>true;
 f.nodes['recent-notification-items'].innerHTML='focused';f.nodes['workflow-notification-menu'].open=true;
 f.nodes['workflow-notification-menu'].listeners.toggle();await settle();
 assert.equal(f.nodes['recent-notification-items'].innerHTML,'focused');
 f.nodes['recent-notification-filter'].value='unread';f.nodes['recent-notification-filter'].listeners.change();await settle();
 assert.match(f.calls.at(-1).url,/filter=unread/);assert(f.calls.every(call=>!call.options.method));
});

test('request detail review links are hidden when their approval is resolved',async()=>{
 const f=fixture();await settle();f.fieldset.tagName='A';
 f.data={unread:1,pending:0,returned:0,html:'handled',approval_active:false};
 await f.api.poll();assert.equal(f.fieldset.hidden,true);assert.equal(f.handled.hidden,false);
});

test('focused notification controls stay in place while shared-step state still updates',async()=>{
 const f=fixture();await settle();const label={textContent:'Awaiting your decision'};
 f.nodes['recent-notification-items'].contains=()=>true;
 f.nodes['recent-notification-items'].querySelector=()=>label;
 f.data={unread:2,pending:0,returned:0,html:'new',states:[{id:7,state:'Already handled'}]};
 await f.api.poll();assert.equal(label.textContent,'Already handled');
});
