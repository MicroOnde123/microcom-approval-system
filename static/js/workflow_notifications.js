/* One visible-tab polling loop; all authorization and transitions remain server-side. */
(function () {
 'use strict';
 const INTERVAL = 5000;
 function start(document, window, fetcher, config) {
  if (window.microcomNotifications) return window.microcomNotifications;
  let timer = null, controller = null, stopped = false, again = false;
  const menu = document.getElementById('workflow-notification-menu');
  const filter = document.getElementById('recent-notification-filter');
  const live = document.getElementById('notification-live-status');
  const form = document.querySelector('[data-live-approval-id]');
  function schedule() {
   window.clearTimeout(timer);
   if (!document.hidden && !stopped) timer = window.setTimeout(poll, INTERVAL);
  }
  async function poll() {
   window.clearTimeout(timer);
   if (document.hidden || stopped) return;
   if (controller) {again=true; return;}
   controller = new AbortController();
   try {
    const url = new URL(config.url, window.location.href);
    url.searchParams.set('filter', filter?.value || 'all');
    if (form) url.searchParams.set('approval',form.dataset.liveApprovalId);
    const response = await fetcher(url.toString(), {credentials:'same-origin', cache:'no-store', signal:controller.signal});
    if (response.redirected || response.status === 401 || response.status === 403) { stopped = true; return; }
    if (!response.ok || !(response.headers.get('Content-Type') || '').includes('application/json')) throw new Error('refresh');
    const data = await response.json();
    for (const [id,key] of [['notification-unread-count','unread'],['pending-approval-count','pending'],['returned-request-count','returned']]) {
     const badge = document.getElementById(id);
     if (badge) { const value = Number(data[key]) || 0; badge.textContent=String(value); badge.hidden=value===0; badge.style.display=value===0?'none':''; }
    }
    const items = document.getElementById('recent-notification-items');
    // Never replace a focused action; the next poll updates it after focus leaves.
    if (items && !items.contains(document.activeElement)) items.innerHTML=data.html;
    else if (items) for(const state of data.states || []) {
     const label=items.querySelector?.('[data-notice-id="'+Number(state.id)+'"] .workflow-notification-state');
     if(label) label.textContent=state.state;
    }
    if (form && data.approval_active === false) {
     const controls=form.querySelector('[data-approval-controls]');
     if (controls) {controls.disabled=true; if(controls.tagName !== 'FIELDSET') controls.hidden=true;}
     const notice = document.querySelector('[data-approval-handled]');
     notice.hidden=false; notice.textContent=config.handled;
    }
    document.querySelectorAll('form[data-workflow-live]').forEach(node => node.dispatchEvent(new Event('workflow:refresh')));
    if (live) live.textContent='';
   } catch (error) {
    if (error.name !== 'AbortError' && live) live.textContent=config.error;
   } finally {controller=null; if(again && !document.hidden && !stopped) {again=false; timer=window.setTimeout(poll,0);} else schedule();}
  }
  document.addEventListener('visibilitychange', () => {
   window.clearTimeout(timer);
   if (document.hidden) controller?.abort(); else poll();
  });
  menu?.addEventListener('toggle', () => {if (menu.open) poll();});
  filter?.addEventListener('change', poll);
  menu?.addEventListener('keydown', event => {if (event.key === 'Escape') {menu.open=false; menu.querySelector('summary').focus();}});
  document.addEventListener('click', event => {
    if (menu?.open && !menu.contains(event.target)) {
        menu.open = false;
    }
  });
  document.addEventListener('submit', async event => {
   const readForm = event.target.closest('form[data-notice-read]');
   if (!readForm) return;
   event.preventDefault();
   const button=readForm.querySelector('button'); if (button.disabled) return;
   button.disabled=true;
   try {
    const response=await fetcher(readForm.action,{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'},body:new FormData(readForm)});
    if (!response.ok || response.redirected) throw new Error('read');
    const row=readForm.closest('[data-notice-id]');
    row?.classList.remove('is-unread');
    row?.querySelector('.workflow-notification-unread')?.remove();
    readForm.hidden=true;
    row?.querySelector('[data-notice-view] button')?.focus();
    await poll();
   } catch (_) {if(live) live.textContent=config.error;}
   finally {button.disabled=false;}
  });
  window.microcomNotifications = {poll};
  poll();
  return window.microcomNotifications;
 }
 if (typeof module !== 'undefined') module.exports={start,INTERVAL};
 if (typeof document !== 'undefined') {
  const script=document.currentScript;
  document.addEventListener('DOMContentLoaded',()=>start(document,window,window.fetch.bind(window),{
   url:script.dataset.liveUrl,error:script.dataset.refreshError,handled:script.dataset.handled}));
 }
})();
