/* Minimal dependency-free Edge/CDP harness. Serves only explicitly allowed fixtures. */
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
exports.open=async(root,allowed)=>{
    const server=http.createServer((req,res)=>{
        const file=req.url.split('?')[0].split('/').pop();
        if(!allowed.includes(file)){res.writeHead(404);return res.end();}
        res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html; charset=utf-8');
        res.end(fs.readFileSync(path.join(root,file)));
    });
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const profile=fs.mkdtempSync(path.join(root,'site-edge-'));
    const child=spawn(process.env.EDGE_BINARY||'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
        ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
    let socket;
    const close=async()=>{
        if(socket?.readyState===1){try{await send('Browser.close');}catch{}socket.close();}
        if(!child.killed)child.kill();server.close();
    };
    const pending=new Map();let id=0,sessionId;
    function send(method,params={},session=sessionId){return new Promise((resolve,reject)=>{
        const key=++id;pending.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params,sessionId:session}));
    });}
    try{
        const active=path.join(profile,'DevToolsActivePort');
        for(let i=0;!fs.existsSync(active);i++){if(i>100)throw Error('Edge startup timeout');await pause(100);}
        const [port,endpoint]=fs.readFileSync(active,'utf8').trim().split(/\r?\n/);
        socket=new WebSocket('ws://127.0.0.1:'+port+endpoint);
        socket.addEventListener('message',event=>{const msg=JSON.parse(event.data),item=pending.get(msg.id);if(item){pending.delete(msg.id);msg.error?item.reject(Error(msg.error.message)):item.resolve(msg.result);}});
        await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
        const target=await send('Target.createTarget',{url:'about:blank'},undefined);
        sessionId=(await send('Target.attachToTarget',{targetId:target.targetId,flatten:true},undefined)).sessionId;
        await send('Page.enable');
        const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
        const until=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await pause(50);}throw Error('Timeout: '+expression);};
        return {send,evaluate,until,close,
            init:source=>send('Page.addScriptToEvaluateOnNewDocument',{source}),
            navigate:async file=>{await send('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'+file});await until('document.readyState==="complete"');},
            viewport:(width,height)=>send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500}),
            key:async(key,code=key)=>{const vk=key==='Enter'?13:key==='Escape'?27:key==='ArrowDown'?40:key===' '?32:0;await send('Input.dispatchKeyEvent',{type:'keyDown',key,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk,...(key==='Enter'?{text:'\r'}:{})});await send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:vk,nativeVirtualKeyCode:vk});},
            screenshot:async file=>{const result=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(root,file),Buffer.from(result.data,'base64'));},
            pdf:async file=>{const result=await send('Page.printToPDF',{preferCSSPageSize:true,printBackground:true});fs.writeFileSync(path.join(root,file),Buffer.from(result.data,'base64'));}
        };
    }catch(error){await close();throw error;}
};
