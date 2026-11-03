'use strict';
const RefinedSettings=(()=>{
 let topic='workspace';
 function bind(){
  const buttons=[...document.querySelectorAll('[data-settings-jump]')];
  if(!buttons.some(b=>b.dataset.settingsJump===topic))topic='workspace';
  function show(id){topic=id;document.querySelectorAll('.settings-group').forEach(s=>s.hidden=s.id!=='settings-'+id);buttons.forEach(b=>{const selected=b.dataset.settingsJump===id;b.classList.toggle('selected',selected);b.setAttribute('aria-current',selected?'page':'false');});}
  buttons.forEach(b=>b.onclick=()=>show(b.dataset.settingsJump));show(topic);
 }
 async function notifications(){
  const box=$('#settings-notifications-cards');if(!box)return;let prefs=await api('workspace-preferences');if(!box.isConnected)return;
  const kinds=[['invoicePaid','Invoice marked paid'],['invoiceOverdue','Invoice overdue'],['emailFailure','Email delivery failed or uncertain'],['receipts','Documents ready for review'],['bank','Bank feed connection issues'],['budgets','Budget thresholds']];
  box.innerHTML=`<form id="notification-preferences"><div class="notification-options"><div class="notification-option heading-row"><span>Activity</span><strong>Bell</strong><strong>Email</strong></div>${kinds.map(([key,label])=>`<div class="notification-option"><span>${label}</span>${['bell','email'].map(channel=>`<label><input type="checkbox" name="${key}_${channel}" ${prefs.notifications[key][channel]?'checked':''} aria-label="${label}: ${channel}"></label>`).join('')}</div>`).join('')}</div><p class="footnote">Email applies to new events after you enable it. These are updates for your account; customer reminders and security sign-in alerts have their own settings. Mobile push preferences remain in the phone app.</p>${prefs.smtp_configured?'':'<p class="notice">Configure Email → Email delivery before email updates can be sent.</p>'}<button type="submit">Save notification preferences</button></form>`;
  formHandler('#notification-preferences',async(_,form)=>{const notifications=Object.fromEntries(kinds.map(([key])=>[key,Object.fromEntries(['bell','email'].map(channel=>[channel,form.elements[key+'_'+channel].checked]))]));prefs=await api('workspace-preferences',{...prefs,notifications},'PUT');Notifications.invalidate();await Notifications.mount();toast('Notification preferences saved.');});
 }
 async function dashboard(prefs,done){
  const panels=[['chart','Monthly comparison'],['incoming','Incoming money'],['income','Business income'],['expenses','Expense categories'],['tax','Financial-year forecast'],['invoices','Recent invoices'],['allocation','Work & business allocation']];
  modal('Customise dashboard',`<form id="dashboard-preferences"><p>Show the sections you use. Your choices are saved to your account.</p>${panels.map(([key,label])=>`<label class="check"><input type="checkbox" name="panel_${key}" ${prefs.dashboard.hidden.includes(key)?'':'checked'}>${label}</label>`).join('')}<div class="modal-footer"><button type="submit">Save dashboard</button></div></form>`);
  formHandler('#dashboard-preferences',async(_,form)=>{await api('workspace-preferences',{...prefs,dashboard:{...prefs.dashboard,hidden:panels.filter(([key])=>!form.elements['panel_'+key].checked).map(([key])=>key)}},'PUT');$('#modal').close();await done();});
 }
 return {bind,notifications,dashboard};
})();
