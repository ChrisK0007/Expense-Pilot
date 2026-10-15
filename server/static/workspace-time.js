'use strict';
const WorkspaceTime=(()=>{
 const zone=()=>S.timezone||'Australia/Brisbane';
 const suggested=()=>Intl.DateTimeFormat().resolvedOptions().timeZone||'Australia/Brisbane';
 function parts(value){return Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:zone(),year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value)).map(p=>[p.type,p.value]));}
 function day(value=new Date()){const p=parts(value);return `${p.year}-${p.month}-${p.day}`;}
 function local(value=new Date()){const p=parts(value);return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;}
 function stamp(value){return new Date(value).toLocaleString('en-AU',{timeZone:zone(),timeZoneName:'short'});}
 function fieldHTML(value){return field('Workspace timezone','timezone','text',value,'required list="workspace-timezones" maxlength="100" autocomplete="off"')+'<datalist id="workspace-timezones"></datalist><p class="footnote">Used for dates, reminders and trip tracking across all devices. Daylight saving is automatic. Saved record dates stay unchanged.</p>';}
 async function loadChoices(){try{const r=await api('timezones');const list=$('#workspace-timezones');if(list)list.innerHTML=r.timezones.map(z=>`<option value="${esc(z)}"></option>`).join('');}catch(e){toast(e.message);}}
 async function settings(){
  const c=await api('workspace/settings');
  modal('Workspace timezone',`<form id="timezone-form">${fieldHTML(c.timezone)}<button type="submit">Save timezone</button></form>`);
  await loadChoices();
  formHandler('#timezone-form',async d=>{await api('workspace/settings',{timezone:d.timezone},'PUT');S=await api('session');$('#modal').close();render();toast('Workspace timezone saved. Refresh other connected devices to apply it there.');});
 }
 return {zone,suggested,day,local,stamp,fieldHTML,loadChoices,settings};
})();
