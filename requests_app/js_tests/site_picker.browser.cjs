const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {open}=require('./browser_session.cjs');
const root=path.resolve(__dirname,'../../local_artifacts/agent_multiselect_tests/browser');
(async()=>{
    const documents=['short','long','legacy'].flatMap(kind=>['en','fr'].map(lang=>'print_'+kind+'_'+lang+'.html'));
    const browser=await open(root,['en_sites.html','fr_sites.html','sites_draft.html','sites_legacy.html','agent_picker.js','site_picker.js','agent_picker.css',...documents]);
    const {evaluate:ev,until}=browser,results=[];
    try{
        await browser.init(`
            window.errors=[];addEventListener('error',event=>errors.push(event.message));
            window.allowDuplicate=false;window.confirmCalls=0;window.confirm=()=>{confirmCalls++;return allowDuplicate;};
            window.searchMode='normal';
            window.fetch=async url=>{await new Promise(resolve=>setTimeout(resolve,30));if(searchMode==='error')return {ok:false};
                const parsed=new URL(url),page=Number(parsed.searchParams.get('page')||1),query=(parsed.searchParams.get('q')||'').toLowerCase();
                const label=parsed.pathname.includes('site-directory')?'Directory Site ':'Registered Employee ';
                const all=Array.from({length:25},(_,i)=>({id:i+1,name:label+(i+1)})).filter(row=>row.name.toLowerCase().includes(query));
                return {ok:true,json:async()=>({results:all.slice((page-1)*20,page*20),more:all.length>page*20})};};
        `);
        for(const lang of ['en','fr'])for(const [device,width,height] of [['mobile',390,844],['tablet',768,1024],['tablet_landscape',1024,768],['desktop',1365,1000]]){
            await browser.viewport(width,height);await browser.navigate(lang+'_sites.html');
            await until(`document.querySelector('[data-site-picker]')?.dataset.ready==='1'&&document.querySelector('[data-agent-picker]')?.dataset.ready==='1'`);
            await ev(`window.s=document.querySelector('[data-site-picker]');window.a=document.querySelector('[data-agent-picker]');window.sq=selector=>s.querySelector(selector);window.aq=selector=>a.querySelector(selector);`);
            assert.equal(await ev(`new Set([...document.querySelectorAll('[id]')].map(e=>e.id)).size===document.querySelectorAll('[id]').length`),true);
            assert.equal(await ev(`sq('#site-search').placeholder`),lang==='fr'?'Rechercher un site par nom...':'Search sites by name...');
            assert.equal(await ev(`sq('[data-site-manual-form]').hidden`),true);
            assert.equal(await ev(`sq('[data-site-counter]').textContent`),'0 / 5');
            const point=await ev(`(()=>{const r=sq('[data-site-info-toggle]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
            if(device==='mobile'){
                await browser.send('Emulation.setTouchEmulationEnabled',{enabled:true});
                await browser.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
                await browser.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
            }else{
                await browser.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
                await browser.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
            }
            await until(`sq('[data-site-info-toggle]').getAttribute('aria-expanded')==='true'`);
            await browser.key('Escape');
            await browser.screenshot('sites_'+lang+'_'+device+'_empty.png');
            await ev(`sq('#site-search').focus();sq('#site-search').click()`);
            await until(`sq('[role=listbox]').children.length===20`);
            await ev(`sq('[data-site-more]').click()`);await until(`sq('[role=listbox]').children.length===25`);
            await browser.key('ArrowDown');await browser.key('Enter');
            assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value)[0].site_id`),1);
            assert.equal(await ev(`JSON.parse(aq('[name=agent_selections]').value).length`),0);
            await ev(`aq('#agent-search').focus();aq('#agent-search').click()`);await until(`aq('[role=listbox]').children.length===20`);
            await browser.key('ArrowDown');await browser.key('Enter');
            assert.equal(await ev(`JSON.parse(aq('[name=agent_selections]').value)[0].user_id`),1);
            const originalAgents=await ev(`aq('[name=agent_selections]').value`);
            await ev(`sq('#site-search').focus();sq('#site-search').click()`);await until(`sq('[role=listbox]').children.length===20`);
            await ev(`sq('[role=option]').click()`);assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value).length`),1);
            assert.equal(await ev(`sq('[data-site-status]').textContent===s.dataset.duplicate`),true);
            await ev(`sq('[data-site-manual]').click();sq('[data-site-add]').click()`);
            assert.equal(await ev(`document.activeElement.id`),'site-manual-name');
            await browser.key('Escape');
            assert.equal(await ev(`document.activeElement.id`),'site-search');
            assert.equal(await ev(`sq('[data-site-manual-form]').hidden`),true);
            await ev(`sq('[data-site-manual]').click()`);
            await ev(`sq('#site-manual-name').value='Manual remote';sq('[data-site-add]').click()`);
            await ev(`sq('[data-site-tags]').children[1].querySelector('button').click();sq('#site-manual-name').value='Edited remote';sq('[data-site-add]').click()`);
            assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value)[1].name`),'Edited remote');
            await ev(`sq('[data-site-manual]').click();sq('#site-manual-name').value='Edited remote';sq('[data-site-add]').click()`);
            assert.equal(await ev(`confirmCalls`),1);assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value).length`),2);
            await ev(`allowDuplicate=true;sq('[data-site-add]').click()`);
            assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value).length`),3);
            await ev(`sq('[data-site-tags]').children[2].querySelector('button:last-child').click()`);
            await ev(`for(let i=0;i<3;i++){sq('[data-site-manual]').click();sq('#site-manual-name').value='Manual site '+i;sq('[data-site-add]').click();}`);
            assert.equal(await ev(`sq('[data-site-counter]').textContent`),'5 / 5');assert.equal(await ev(`sq('[data-site-manual]').disabled`),true);
            await ev(`sq('#site-search').focus();sq('#site-search').click()`);await until(`sq('[role=listbox]').children.length===20`);
            await ev(`sq('[role=listbox]').children[1].click()`);
            assert.equal(await ev(`sq('[data-site-status]').textContent===s.dataset.max`),true);
            assert.equal(await ev(`JSON.parse(sq('[name=site_selections]').value).length`),5);
            await browser.key('Escape');
            await ev(`sq('[data-site-info-toggle]').focus()`);await browser.key('Enter');
            assert.equal(await ev(`sq('[data-site-info-content]').hidden`),false);
            assert.equal(await ev(`aq('[data-agent-info-content]').hidden`),true);
            await browser.key('Escape');assert.equal(await ev(`document.activeElement===sq('[data-site-info-toggle]')`),true);
            assert.equal(await ev(`aq('[name=agent_selections]').value`),originalAgents);
            assert.equal(await ev(`document.documentElement.scrollWidth<=innerWidth`),true);
            await browser.screenshot('sites_'+lang+'_'+device+'_selected.png');
            await ev(`sq('[data-site-tags]').children[4].querySelector('button:last-child').click();sq('#site-search').value='no such place';sq('#site-search').dispatchEvent(new Event('input'));`);
            await until(`sq('[data-site-status]').textContent===s.dataset.empty`);
            assert.equal(await ev(`sq('[data-site-manual]').disabled`),false);
            await ev(`searchMode='error';sq('#site-search').dispatchEvent(new Event('input'))`);
            await until(`sq('[data-site-status]').textContent===s.dataset.failed`);
            assert.deepEqual(await ev(`errors`),[]);
            results.push({lang,device,width,checks:'both-pickers,unique-IDs,keyboard,manual,duplicate-warning,limit,edit,remove,info,search,pagination,empty,error'});
        }
        for(const scenario of ['draft','legacy']){
            await browser.navigate('sites_'+scenario+'.html');await until(`document.querySelector('[data-site-picker]')?.dataset.ready==='1'`);
            if(scenario==='draft'){
                assert.equal(await ev(`JSON.parse(document.querySelector('[name=site_selections]').value)[0].site_id`),12);
                assert.equal(await ev(`JSON.parse(document.querySelector('[name=agent_selections]').value)[0].user_id`),12);
            }else{
                assert.equal(await ev(`document.querySelector('[name=site_selections]').value`),'');
                await ev(`document.querySelector('[data-site-replace]').click()`);
                assert.equal(await ev(`document.querySelector('[name=site_selections]').value`),'[]');
            }
            results.push({scenario,passed:true});
        }
        for(const name of documents){
            await browser.navigate(name);await browser.send('Emulation.setEmulatedMedia',{media:'print'});
            assert.equal(await ev(`getComputedStyle(document.querySelector('.half-copy')).overflow`),'visible');
            assert.equal(await ev(`document.documentElement.lang`),name.endsWith('_fr.html')?'fr':'en');
            assert.ok(await ev(`[...document.querySelectorAll('.half-copy')].every(copy=>copy.scrollHeight<=copy.clientHeight+2)`),'Print copy must grow to contain all content');
            assert.ok(await ev(`[...document.querySelectorAll('.half-copy')].every(copy=>copy.scrollWidth<=copy.clientWidth+2)`),'Print content must fit A4 width without horizontal clipping');
            await browser.pdf(name.replace('.html','.pdf'));
            const footer=await ev(`document.querySelector('.signature-area .approval-note:last-child').textContent.trim()`);
            fs.writeFileSync(path.join(root,name.replace('.html','.footer.txt')),footer);
            await browser.send('Emulation.setEmulatedMedia',{media:''});
        }
        fs.writeFileSync(path.join(root,'site_browser_results.json'),JSON.stringify(results,null,2));
        console.log(JSON.stringify({browser:'Microsoft Edge',site_scenarios:results.length,pdfs:documents.length,passed:true}));
    }finally{await browser.close();}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
