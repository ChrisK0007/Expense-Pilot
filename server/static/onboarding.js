'use strict';
const Onboarding=(()=>{
 const switches=[
  ['employment','Employment'],['business','Business'],['banks','Bank accounts'],
  ['trips','Overnight spending'],['vehicles','Vehicles and drives'],
  ['home_office','Home office'],['tax','Tax forecast']
 ];
 const releaseLink=()=>'<button type="button" class="text-button" id="whats-new">What’s new</button>';
 function showNotes(notes){
  modal('What’s new',`<p class="muted">Expense Pilot v${esc(notes.version)}</p>
   ${notes.changes.length?`<ul class="release-changes">${notes.changes.map(change=>`<li>${esc(change)}</li>`).join('')}</ul>`:'<p>No release notes for this version.</p>'}
   <div class="modal-footer"><button type="button" id="release-notes-done">Got it</button></div>`);
  bind('#release-notes-done',()=>$('#modal').close());
 }
 function bindReleaseLink(){
  bind('#whats-new',async()=>{
   try{showNotes(await api('release-notes'));}catch(e){toast(e.message);}
  });
 }
 async function afterSignIn(){
  const user=S.user?.id;
  if(owner()){
   const state=await api('setup/guide');
   if(S.user?.id!==user)return;
   if(state.pending&&!$('#modal').open){drawGuide(state.step);return;}
  }
  if(!user||$('#modal').open)return;
  const notes=await api('release-notes',{},'POST');
  if(S.user?.id===user&&notes.first&&!$('#modal').open)showNotes(notes);
 }
 const progress=(step,pending=false)=>api('setup/guide',{step,pending},'PUT');
 async function openGuide(){
  const {step}=await api('setup/guide');
  drawGuide(step===5?0:step);
 }
 function drawGuide(step){
  const steps=[
   {name:'Set up your workspace',description:'Choose how Expense Pilot organises your records.',
    fields:field('Workspace name (optional)','guide_name','text',S.workspace_name,'maxlength="100"')+
     WorkspaceTime.fieldHTML(WorkspaceTime.zone())+`<fieldset><legend>Features to show</legend>${switches.map(([key,label])=>
      `<label class="check"><input type="checkbox" name="${key}" ${Features.enabled(key)?'checked':''}> ${label}</label>`).join('')}</fieldset>`},
   {name:'Choose how to capture expenses',description:'Enter details yourself or use receipt AI to read an uploaded document.',
    actions:[['Configure receipt AI',PublicRelease.aiForm],['Add an expense',()=>expenseModal()],['Capture a document',async()=>{await navigate('receipts');Receipts.capture();}]]},
   {name:'Connect your banking',description:'Add a bank account to import a CSV or link a PocketSmith feed.',
    actions:Features.enabled('banks')?[['Open bank accounts',()=>navigate('bank_accounts')],['Configure PocketSmith',BankFeeds.settings]]:[]},
   {name:'Set up client invoices',description:'If you invoice clients, enter your business details and payment information.',
    actions:Features.enabled('business')?[['Set business details',Billing.businessDetails]]:[]},
   {name:'Protect your workspace',description:'Set up two-factor authentication and review how your server backs up your records.',
    actions:[...(S.user.totp_enabled?[]:[['Set up two-factor authentication',Security.setup]]),
     ['Download a backup',PublicRelease.backupForm],['Review backup settings',async()=>{await navigate('settings');$('#settings-data')?.scrollIntoView();}]]}
  ];
  const current=steps[step];
  const later=async()=>{
   try{await progress(step);$('#modal').close();}catch(e){toast(e.message);}
  };
  modal('Setup guide',`<p class="muted">Step ${step+1} of ${steps.length}</p><h3>${current.name}</h3><p>${current.description}</p>
   <form id="setup-guide-form">${current.fields||''}
   ${current.actions?.length?`<div class="settings-options">${current.actions.map(([label],i)=>`<button type="button" class="secondary" data-guide-action="${i}">${label}</button>`).join('')}</div><p class="footnote">You can resume this step from Settings → Workspace setup.</p>`:''}
   <div class="modal-footer"><button class="ghost" type="button" id="guide-later">Finish later</button>
   ${step?'<button type="button" class="secondary" id="guide-back">Back</button>':''}
   <button type="submit">${step===4?'Finish setup':'Continue'}</button></div></form>`,{beforeClose:()=>{later();return false;}});
  if(step===0)WorkspaceTime.loadChoices();
  bind('#guide-later',later);
  bind('#guide-back',async()=>{try{await progress(step-1,true);drawGuide(step-1);}catch(e){toast(e.message);}});
  document.querySelectorAll('[data-guide-action]').forEach(button=>button.onclick=async()=>{
   button.disabled=true;
   try{await progress(step);$('#modal').close();await current.actions[Number(button.dataset.guideAction)][1]();}
   catch(e){toast(e.message);}
   finally{button.disabled=false;}
  });
  formHandler('#setup-guide-form',async(data,form)=>{
   if(step===0){
    const features=Object.fromEntries(switches.map(([key])=>[key,form.elements[key].checked]));
    if(!features.employment&&!features.business)throw Error('Keep employment or business tracking enabled.');
    await api('workspace/settings',{timezone:data.timezone,name:data.guide_name},'PUT');
    S.features=await api('features',features,'PUT');
    S.timezone=data.timezone;S.workspace_name=data.guide_name.trim();
    await render();
   }
   await progress(step+1,step<4);
   if(step<4)drawGuide(step+1);
   else{$('#modal').close();await navigate('dashboard');}
  });
 }
 return {afterSignIn,openGuide,releaseLink,bindReleaseLink};
})();
