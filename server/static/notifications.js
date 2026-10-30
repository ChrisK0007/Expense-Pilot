'use strict';
const Notifications=(()=>{
 let cached=null,loadedAt=0;
 const year=()=>Number(today().slice(0,4))-(Number(today().slice(5,7))<7?1:0);
 function markup(){return `<button type="button" class="notification-trigger ghost" aria-label="Notifications" aria-expanded="false" aria-controls="notification-panel"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span class="notification-count" hidden></span></button><div id="notification-panel" class="notification-panel" popover><h2>Notifications</h2><p class="footnote">Items needing attention · FY ${year()}–${year()+1}</p><div id="notification-items">Loading…</div><a href="#/attention" class="button-link secondary">View all / change year</a></div>`;}
 async function mount(){
  const root=$('#notification-bell');if(!root||!owner())return;root.innerHTML=markup();const trigger=root.querySelector('button'),panel=root.querySelector('[popover]');
  trigger.onclick=()=>{if(panel.matches(':popover-open'))panel.hidePopover();else{root.querySelector('#notification-items').textContent='Loading…';panel.showPopover();const r=trigger.getBoundingClientRect();panel.style.left=Math.max(8,Math.min(innerWidth-panel.offsetWidth-8,r.right-panel.offsetWidth))+'px';panel.style.top=Math.min(r.bottom+8,innerHeight-100)+'px';load(true);}};
  panel.addEventListener('toggle',e=>{trigger.setAttribute('aria-expanded',String(e.newState==='open'));if(e.newState==='closed')root.querySelector('#notification-items').replaceChildren();});
  async function load(force=false){try{if(force||!cached||Date.now()-loadedAt>30000){cached=await api('workflows/attention/'+year());loadedAt=Date.now();}if(!root.isConnected)return;const items=cached.items,count=root.querySelector('.notification-count');count.hidden=!items.length;count.textContent=items.length>99?'99+':items.length;trigger.setAttribute('aria-label',`Notifications, ${items.length} items needing attention`);if(!panel.matches(':popover-open')){root.querySelector('#notification-items').replaceChildren();return;}root.querySelector('#notification-items').innerHTML=items.length?items.slice(0,8).map((i,n)=>`<button class="notification-item" data-notification="${n}"><strong>${esc(i.title)}</strong><span>${esc(i.detail)}</span></button>`).join(''):'<p class="empty">You’re all caught up.</p>';root.querySelectorAll('[data-notification]').forEach(b=>b.onclick=()=>{panel.hidePopover();Workflows.openAttention(items[Number(b.dataset.notification)]).catch(e=>toast(e.message));});}catch(e){if(root.isConnected)root.querySelector('#notification-items').textContent=e.message;}}
  await load();
 }
 function invalidate(){cached=null;loadedAt=0;}
 return {mount,invalidate};
})();
