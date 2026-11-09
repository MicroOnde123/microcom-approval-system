/* Real Edge checks of Django-rendered picker fixtures; synthetic search transport.
 * Run render_agent_picker.py first. No application database or user session is used.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {spawn} = require('node:child_process');
const root = path.resolve(__dirname, '../../local_artifacts/agent_multiselect_tests/browser');
const profile = fs.mkdtempSync(path.join(root, 'edge-'));
const edge = process.env.EDGE_BINARY || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const results = [];
let socket, child;
const pending = new Map();
let next = 0;
const server = http.createServer((req,res) => {
    const name = req.url.split('?')[0].split('/').pop();
    if (!['en.html','fr.html','draft.html','legacy.html','invalid.html','agent_picker.js','agent_picker.css'].includes(name)) {
        res.writeHead(404); return res.end();
    }
    res.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html; charset=utf-8');
    res.end(fs.readFileSync(path.join(root,name)));
});
function send(method, params={}, sessionId) {
    return new Promise((resolve,reject) => {
        const id = ++next;
        pending.set(id,{resolve,reject});
        socket.send(JSON.stringify({id,method,params,sessionId}));
    });
}
(async () => {
    await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
    const port = server.address().port;
    child = spawn(edge, ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
        '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],
        {windowsHide:true, stdio:'ignore'});
    const activePort = path.join(profile,'DevToolsActivePort');
    for(let i=0;!fs.existsSync(activePort);i++) { if(i>100) throw Error('Edge startup timeout'); await pause(100); }
    const [debugPort, endpoint] = fs.readFileSync(activePort,'utf8').trim().split(/\r?\n/);
    socket = new WebSocket('ws://127.0.0.1:'+debugPort+endpoint);
    socket.addEventListener('message', event => {
        const message = JSON.parse(event.data);
        if(message.id) {
            const item = pending.get(message.id);
            if(item) { pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result); }
        }
    });
    await new Promise((resolve,reject) => {socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
    const {targetId} = await send('Target.createTarget',{url:'about:blank'});
    const {sessionId} = await send('Target.attachToTarget',{targetId,flatten:true});
    const evaluate = async expression => {
        const answer = await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sessionId);
        if(answer.exceptionDetails) throw Error(JSON.stringify(answer.exceptionDetails));
        return answer.result.value;
    };
    const until = async expression => {
        for(let i=0;i<100;i++) {if(await evaluate(expression)) return; await pause(50);}
        throw Error('Timed out: '+expression);
    };
    await send('Page.enable',{},sessionId);
    await send('Page.addScriptToEvaluateOnNewDocument',{source:`
        window.errors=[];addEventListener('error',e=>errors.push(e.message));
        window.confirmCalls=0;window.allowDuplicate=false;
        window.confirm=()=>{confirmCalls++;return allowDuplicate;};
        window.searchMode='normal';
        window.fetch=async url=>{
            await new Promise(r=>setTimeout(r,50));
            if(searchMode==='error') return {ok:false};
            const u=new URL(url);const q=u.searchParams.get('q')||'';const page=Number(u.searchParams.get('page')||1);
            const all=Array.from({length:25},(_,i)=>({id:i+1,name:'Registered Person '+(i+1)}));
            const matches=all.filter(p=>p.name.toLowerCase().includes(q.toLowerCase()));
            return {ok:true,json:async()=>({results:matches.slice((page-1)*20,page*20),more:matches.length>page*20})};
        };
    `},sessionId);
    for(const language of ['en','fr']) for(const [device,width,height] of [['mobile',390,844],['tablet',768,1024],['tablet-landscape',1024,768],['desktop',1365,1000]]) {
        await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:device==='mobile'},sessionId);
        await send('Page.navigate',{url:'http://127.0.0.1:'+port+'/'+language+'.html'},sessionId);
        await until(`document.querySelector('[data-agent-picker]')?.dataset.ready==='1'`);
        assert.equal(await evaluate(`document.querySelector('[data-manual]').textContent.trim()`),language==='fr'?'Autre personne — Ajouter manuellement':'Other person — Add manually');
        assert.equal(await evaluate(`document.querySelector('#agent-search').placeholder`),language==='fr'?'Rechercher un agent par nom...':'Search employees by name...');
        assert.equal(await evaluate(`document.querySelectorAll('label[for=agent-search]').length`),1);
        const compact = await evaluate(`(()=>{
            const q=s=>document.querySelector(s),rect=s=>q(s).getBoundingClientRect();
            const label=rect('.agent-field-heading>label'),counter=rect('[data-counter]'),search=rect('#agent-search'),icon=rect('.agent-search-wrap>svg');
            return {counterAligned:Math.abs((label.top+label.height/2)-(counter.top+counter.height/2))<2,
                counterRight:counter.right>label.right, iconInside:icon.left>search.left&&icon.right<search.right&&icon.top>=search.top&&icon.bottom<=search.bottom,
                manualHidden:q('[data-manual-form]').hidden,manualBelow:rect('[data-manual]').top>=search.bottom,
                height:rect('[data-agent-picker]').height,columns:getComputedStyle(q('[data-preview-grid]')).gridTemplateColumns.split(' ').length};
        })()`);
        assert.ok(compact.counterAligned&&compact.counterRight&&compact.iconInside&&compact.manualHidden&&compact.manualBelow,JSON.stringify(compact));
        assert.ok(compact.height<=110,'Empty picker should remain compact: '+compact.height);
        assert.equal(compact.columns,width<=800?1:2,'Existing application form breakpoint');
        const emptyScreenshot=await send('Page.captureScreenshot',{format:'png'},sessionId);
        fs.writeFileSync(path.join(root,language+'_'+device+'_compact_empty.png'),Buffer.from(emptyScreenshot.data,'base64'));
        // Information disclosure: native mouse/touch, Enter/Space, Escape and outside dismissal.
        const initialSelection = await evaluate(`document.querySelector('[name=agent_selections]').value`);
        assert.equal(await evaluate(`document.querySelector('[data-agent-info-content]').hidden`),true);
        assert.equal(await evaluate(`document.querySelector('[data-agent-info-toggle]').previousElementSibling.tagName`),'LABEL');
        const infoPoint = await evaluate(`(()=>{const r=document.querySelector('[data-agent-info-toggle]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
        if(device==='mobile') {
            await send('Emulation.setTouchEmulationEnabled',{enabled:true},sessionId);
            await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[infoPoint]},sessionId);
            await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]},sessionId);
        } else {
            await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...infoPoint},sessionId);
            await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...infoPoint},sessionId);
        }
        await until(`document.querySelector('[data-agent-info-toggle]').getAttribute('aria-expanded')==='true'`);
        assert.equal(await evaluate(`document.querySelector('[data-agent-info-content]').textContent.trim()`),language==='fr'
            ? "Recherchez et sélectionnez les agents dans la liste. Si une personne n'y figure pas, choisissez « Autre personne » pour saisir son nom et son prénom. Maximum : 10 personnes au total."
            : "Search and select employees from the list. If someone is not listed, choose 'Other person' to enter their first name and surname. Maximum: 10 people in total.");
        assert.ok(await evaluate(`(()=>{const r=document.querySelector('[data-agent-info-content]').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()`));
        const infoScreenshot=await send('Page.captureScreenshot',{format:'png'},sessionId);
        fs.writeFileSync(path.join(root,language+'_'+device+'_info.png'),Buffer.from(infoScreenshot.data,'base64'));
        await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'},sessionId);
        assert.equal(await evaluate(`document.querySelector('[data-agent-info-content]').hidden`),true);
        assert.equal(await evaluate(`document.activeElement===document.querySelector('[data-agent-info-toggle]')`),true);
        for(const [key,code] of [['Enter','Enter'],[' ','Space']]) {
            const virtualKey = code==='Enter' ? 13 : 32;
            await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:virtualKey,nativeVirtualKeyCode:virtualKey,text:code==='Enter'?'\r':' '},sessionId);
            await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:virtualKey,nativeVirtualKeyCode:virtualKey},sessionId);
            assert.equal(await evaluate(`document.querySelector('[data-agent-info-content]').hidden`),false,'Native '+code+' activation');
            await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,x:1,y:1},sessionId);
            await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:1,y:1},sessionId);
            assert.equal(await evaluate(`document.querySelector('[data-agent-info-toggle]').getAttribute('aria-expanded')`),'false');
            await evaluate(`document.querySelector('[data-agent-info-toggle]').focus()`);
        }
        assert.equal(await evaluate(`document.querySelector('[name=agent_selections]').value`),initialSelection);
        await evaluate(`document.querySelector('#agent-search').focus();document.querySelector('#agent-search').click()`);
        await until(`document.querySelectorAll('[role=option]').length===20`);
        await evaluate(`document.querySelector('[data-more]').click()`);
        await until(`document.querySelectorAll('[role=option]').length===25`);
        // Dispatch real keyboard events through the browser input subsystem.
        for(const key of ['ArrowDown','Enter']) {
            await send('Input.dispatchKeyEvent',{type:'keyDown',key,code:key},sessionId);
            await send('Input.dispatchKeyEvent',{type:'keyUp',key,code:key},sessionId);
        }
        await until(`JSON.parse(document.querySelector('[name=agent_selections]').value).length===1`);
        await evaluate(`document.querySelector('#agent-search').focus();document.querySelector('#agent-search').click()`);
        await until(`document.querySelectorAll('[role=option]').length===20`);
        await evaluate(`document.querySelector('[role=option]').click()`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value).length`),1);
        assert.ok(await evaluate(`document.querySelector('[data-status]').textContent.includes(document.querySelector('[data-agent-picker]').dataset.duplicate)`));
        // Manual required fields, addition, editing, removal and deliberate same-name entries.
        await evaluate(`document.querySelector('[data-manual]').click();document.querySelector('[data-add]').click()`);
        assert.equal(await evaluate(`document.activeElement.id`),'agent-first');
        await evaluate(`document.querySelector('#agent-first').value='Marie Anne';document.querySelector('#agent-surname').value='Test';document.querySelector('[data-add]').click()`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value)[1].full_name`),'Marie Anne Test');
        assert.ok(await evaluate(`(()=>{const tags=document.querySelector('[data-tags]').getBoundingClientRect(),input=document.querySelector('#agent-search').getBoundingClientRect();return tags.bottom<=input.top&&input.top-tags.bottom<=8;})()`));
        await until(`document.querySelector('[role=listbox]').getAttribute('aria-busy')!=='true'`);
        assert.ok(await evaluate(`(()=>{const action=document.querySelector('[data-manual]'),r=action.getBoundingClientRect();return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)===action;})()`),'Manual action remains clickable while results are open');
        await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'},sessionId);
        const selectedScreenshot=await send('Page.captureScreenshot',{format:'png'},sessionId);
        fs.writeFileSync(path.join(root,language+'_'+device+'_compact_selected.png'),Buffer.from(selectedScreenshot.data,'base64'));
        await evaluate(`document.querySelectorAll('.agent-tag')[1].querySelector('button').click();document.querySelector('#agent-surname').value='Edited';document.querySelector('[data-add]').click()`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value)[1].surname`),'Edited');
        await evaluate(`document.querySelectorAll('.agent-tag')[1].querySelector('button').click();document.querySelector('#agent-surname').value='Test';document.querySelector('[data-add]').click()`);
        await evaluate(`document.querySelector('[data-manual]').click();document.querySelector('#agent-first').value='Marie Anne';document.querySelector('#agent-surname').value='Test';document.querySelector('[data-add]').click()`);
        assert.equal(await evaluate(`confirmCalls`),1);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value).length`),2);
        await evaluate(`allowDuplicate=true;document.querySelector('[data-add]').click()`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value).length`),3);
        await evaluate(`document.querySelectorAll('.agent-tag')[2].querySelector('button:last-child').click()`);
        // Mix registered and manual people to reach the combined limit.
        await evaluate(`for(let i=0;i<8;i++){document.querySelector('[data-manual]').click();document.querySelector('#agent-first').value='Manual '+i;document.querySelector('#agent-surname').value='Person';document.querySelector('[data-add]').click();}`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value).length`),10);
        assert.equal(await evaluate(`document.querySelector('[data-manual]').disabled`),true);
        assert.ok(await evaluate(`document.querySelector('[data-counter]').textContent.startsWith('10 / 10')`));
        await evaluate(`document.querySelector('#agent-search').focus();document.querySelector('#agent-search').click()`);
        await until(`document.querySelectorAll('[role=option]').length===20`);
        await evaluate(`document.querySelectorAll('[role=option]')[1].click()`);
        assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value).length`),10);
        assert.ok(await evaluate(`document.querySelector('[data-status]').textContent.includes(document.querySelector('[data-agent-picker]').dataset.max)`));
        await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'},sessionId);
        assert.equal(await evaluate(`document.querySelector('[role=combobox]').getAttribute('aria-expanded')`),'false');
        const dimensions = await evaluate(`({width:innerWidth,scroll:document.documentElement.scrollWidth})`);
        assert.ok(dimensions.scroll<=dimensions.width,language+' '+device+' overflow');
        const screenshot=await send('Page.captureScreenshot',{format:'png'},sessionId);
        fs.writeFileSync(path.join(root,language+'_'+device+'.png'),Buffer.from(screenshot.data,'base64'));
        // Empty and failed searches leave the manual path usable.
        await evaluate(`document.querySelector('.agent-tag button:last-child').click();const input=document.querySelector('#agent-search');input.value='no such user';input.dispatchEvent(new Event('input'));`);
        await until(`document.querySelector('[data-status]').textContent===document.querySelector('[data-agent-picker]').dataset.empty`);
        assert.equal(await evaluate(`document.querySelector('[data-manual]').disabled`),false);
        await evaluate(`searchMode='error';document.querySelector('#agent-search').dispatchEvent(new Event('input'))`);
        await until(`document.querySelector('[data-status]').textContent===document.querySelector('[data-agent-picker]').dataset.failed`);
        assert.deepEqual(await evaluate(`errors`),[]);
        results.push({language,device,...dimensions,...compact,checks:'compact-layout,two-column-form,information-control,mouse,touch,Enter,Space,Escape,outside-dismissal,keyboard,search,pagination,duplicate,manual,edit,remove,limit,empty,error,bilingual'});
    }
    for(const scenario of ['draft','legacy','invalid']) {
        await send('Page.navigate',{url:'http://127.0.0.1:'+port+'/'+scenario+'.html'},sessionId);
        await until(`document.querySelector('[data-agent-picker]')?.dataset.ready==='1'`);
        if(scenario==='draft') {
            assert.equal(await evaluate(`document.querySelectorAll('.agent-tag').length`),2);
            assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value)[0].user_id`),12);
            assert.equal(await evaluate(`JSON.parse(document.querySelector('[name=agent_selections]').value)[1].key`),'saved-person');
        } else if(scenario==='legacy') {
            assert.equal(await evaluate(`document.querySelector('[name=agent_selections]').value`),'');
            assert.equal(await evaluate(`document.querySelector('[data-picker-controls]').hidden`),true);
            await evaluate(`document.querySelector('[data-replace]').click()`);
            assert.equal(await evaluate(`document.querySelector('[data-picker-controls]').hidden`),false);
            assert.equal(await evaluate(`document.querySelector('[name=agent_selections]').value`),'[]');
        } else {
            assert.equal(await evaluate(`document.querySelector('[data-status]').textContent===document.querySelector('[data-agent-picker]').dataset.invalid`),true);
        }
        assert.deepEqual(await evaluate(`errors`),[]);
        results.push({scenario,checks:'rehydration,legacy-preservation,invalid-input-safety'});
    }
    fs.writeFileSync(path.join(root,'browser_results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify({browser:'Microsoft Edge',scenarios:results.length,passed:true}));
    await send('Browser.close');socket.close();server.close();
})().catch(async error => {
    console.error(error.stack);process.exitCode=1;
    if(socket?.readyState===1){try{await send('Browser.close');}catch{}socket.close();}
    if(child && !child.killed) child.kill();
    server.close();
});
