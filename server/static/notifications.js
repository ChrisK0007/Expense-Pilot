'use strict';
const Notifications=(()=>{
 let cached=null,loadedAt=0,cacheRevision=0;
 const year=()=>Number(today().slice(0,4))-(Number(today().slice(5,7))<7?1:0);
 function markup(){return `<button type="button" class="notification-trigger ghost" aria-label="Notifications" aria-expanded="false" aria-controls="notification-panel"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span class="notification-count" hidden></span></button><div id="notification-panel" class="notification-panel" popover><h2>Notifications</h2><p class="footnote">Items needing attention · FY ${year()}–${year()+1}</p><div id="notification-items">Loading…</div><a href="#/attention" class="button-link secondary">View all / change year</a></div>`;}

 async function mount(){
  const root=$('#notification-bell');
  if(!root||!owner())return;
  root.innerHTML=markup();
  const trigger=root.querySelector('.notification-trigger'),panel=root.querySelector('[popover]');
  const list=panel.querySelector('#notification-items'),count=root.querySelector('.notification-count');
  let loadRevision=0;

  trigger.onclick=()=>{
   if(panel.matches(':popover-open')){panel.hidePopover();return;}
   list.textContent='Loading…';
   panel.showPopover();
   const anchor=trigger.getBoundingClientRect();
   panel.style.left=Math.max(8,Math.min(innerWidth-panel.offsetWidth-8,anchor.right-panel.offsetWidth))+'px';
   panel.style.top=Math.min(anchor.bottom+8,innerHeight-100)+'px';
   load(true);
  };
  panel.addEventListener('toggle',event=>{
   trigger.setAttribute('aria-expanded',String(event.newState==='open'));
   if(event.newState==='closed')list.replaceChildren();
  });

  async function load(force=false){
   const revision=++loadRevision,startedAt=cacheRevision;
   try{
    const mustLoad=force||!cached||Date.now()-loadedAt>30000;
    const data=mustLoad?await listItems(year()):cached;
    if(revision!==loadRevision||startedAt!==cacheRevision||!trigger.isConnected)return;
    if(mustLoad){cached=data;loadedAt=Date.now();}
    const items=data.items;
    count.hidden=!items.length;
    count.textContent=items.length>99?'99+':items.length;
    trigger.setAttribute('aria-label',`Notifications, ${items.length} items needing attention`);
    if(!panel.matches(':popover-open'))return;

    list.innerHTML=items.length?items.slice(0,8).map((item,index)=>`<div class="notification-row">
     <button type="button" class="notification-item" data-notification="${index}"><strong>${esc(item.title)}</strong><span>${esc(item.detail)}</span></button>
     ${item.dismiss_key?`<button type="button" class="ghost notification-dismiss" data-dismiss-notification="${index}" aria-label="Dismiss ${esc(item.title)}">Dismiss</button>`:''}
    </div>`).join(''):'<p class="empty">You’re all caught up.</p>';
    list.querySelectorAll('[data-notification]').forEach(button=>button.onclick=()=>{
     panel.hidePopover();
     open(items[Number(button.dataset.notification)]).catch(error=>toast(error.message));
    });
    list.querySelectorAll('[data-dismiss-notification]').forEach(button=>button.onclick=async()=>{
     const restoreFocus=document.activeElement===button;
     button.disabled=true;
     try{
      await dismiss(items[Number(button.dataset.dismissNotification)]);
      await load(true);
      if(restoreFocus&&panel.matches(':popover-open')){
       (list.querySelector('.notification-dismiss')||list.querySelector('.notification-item')||panel.querySelector('a')).focus();
      }
     }catch(error){toast(error.message);}
     finally{if(button.isConnected)button.disabled=false;}
    });
   }catch(error){
    if(revision===loadRevision&&startedAt===cacheRevision&&trigger.isConnected)list.textContent=error.message;
   }
  }
  await load();
 }

 async function listItems(fy){
  const [review,events,prefs]=await Promise.all([api('workflows/attention/'+fy),api('workspace-notifications'),api('workspace-preferences')]);
  const reviewItems=review.items.filter(i=>{const kind=i.kind==='bank'?'bank':['receipt','expense'].includes(i.kind)?'receipts':null;return !kind||prefs.notifications[kind].bell;});
  const extras=events.items.filter(e=>e.kind!=='receipts').map(e=>({...e,notification:true,detail:e.details,date:'',amount_cents:0,page:e.screen}));
  return {...review,items:[...extras,...reviewItems]};
 }

 async function dismiss(item){
  await api('workspace-notifications/dismiss',{key:item.dismiss_key});
 }

 async function open(item){
  if(!item.notification)return Workflows.openAttention(item);
  if(['invoice','quote'].includes(item.screen)){
   await navigate(item.screen==='quote'?'quotes':'invoices');
   await Billing.view(Number(item.item));
  }else{
   await navigate(item.screen==='bank'?'banks':item.screen);
  }
  if(item.dismiss_key){
   await dismiss(item);
   await mount();
  }
 }

 function invalidate(){cached=null;loadedAt=0;cacheRevision++;}
 return {mount,invalidate,items:listItems,open,dismiss};
})();
