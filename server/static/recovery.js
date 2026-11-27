'use strict';
const Recovery=(()=>{
 let token='';
 function capture(){
  if(!location.hash.startsWith('#/reset-password?'))return;
  const value=new URLSearchParams(location.hash.split('?')[1]).get('token')||'';
  token=/^[A-Za-z0-9_-]{43}$/.test(value)?value:'';
  history.replaceState(null,'',location.pathname+location.search);
  if(!token)toast('This reset link is invalid. Request a new link.');
 }
 function reset(){
  $('#root').innerHTML=`<div class="security-gate"><section class="card"><h1>Reset your password</h1><p>Use a new password. If two-factor authentication is enabled, enter your authenticator code or an unused recovery code. Existing signed-in devices will be signed out.</p><form id="reset-password-form">${field('New password','reset_password','password','','required minlength="12" maxlength="256" autocomplete="new-password"')}${field('Confirm new password','reset_confirm','password','','required minlength="12" maxlength="256" autocomplete="new-password"')}${field('Authenticator or recovery code (if enabled)','reset_factor','text','','autocomplete="one-time-code" maxlength="40"')}<button type="submit">Reset password</button><button type="button" class="secondary" id="reset-cancel">Back to sign in</button></form></section></div>`;
  bind('#reset-cancel',()=>{token='';boot();});
  formHandler('#reset-password-form',async d=>{if(d.reset_password!==d.reset_confirm)throw Error('The new passwords do not match.');await api('password-reset/confirm',{token,password:d.reset_password,code:d.reset_factor});token='';await boot();toast('Password reset. Sign in with your new password.');});
 }
 function request(){
  modal('Forgot your password?',`<form id="recovery-request"><p>A reset link is available only for a verified mailbox with email delivery configured. Two-factor authentication remains required. Otherwise, ask the server owner to use terminal recovery.</p>${field('Account email address','recovery_email','email','','required autocomplete="email" maxlength="200"')}<button type="submit">Send reset link</button></form>`);
  formHandler('#recovery-request',async d=>{const r=await api('password-reset/request',{email:d.recovery_email});$('#modal').close();$('#modal').innerHTML='';toast(r.message);});
 }
 function reauthenticate(title,description,action){
  modal(title,`<p>${description}</p><form id="recovery-reauth">${field('Your current password','reauth_password','password','','required autocomplete="current-password"')}${S.user.totp_enabled?field('Your authenticator or recovery code','reauth_factor','text','','required autocomplete="one-time-code" maxlength="40"'):''}<button type="submit">Confirm</button></form>`);
  formHandler('#recovery-reauth',async d=>{await action({password:d.reauth_password,code:d.reauth_factor});$('#modal').close();$('#modal').innerHTML='';});
 }
 function agent(user){reauthenticate('Send password reset link',`Send a recovery link to ${esc(user.name)}’s verified mailbox. Their MFA, roles and current sessions remain unchanged until they complete the reset.`,async data=>{const r=await api('users/'+user.id+'/password-reset',data);toast(r.message);});}
 async function intrusion(){
  if(!owner())return;
  const r=await api('security/intrusion');if(page!=='settings')return;
  $('#security-settings').insertAdjacentHTML('beforeend',`<h3>Intrusion monitoring</h3><p>Records requests to fixed unused decoy paths. Ordinary navigation and missing pages do not trigger blocks. Signed-in users and sign-in/recovery stay accessible.</p><form id="intrusion-policy">${select('Intrusion protection','intrusion_mode',[['off','Off'],['monitor','Monitor only'],['block','Temporary source blocks']],r.mode)}<button type="submit">Save protection mode</button></form><p class="footnote">Temporary blocks last 15 minutes after five decoy requests within 10 minutes. Shared networks can affect several visitors. Only configure trusted proxies you control. Source IDs are private fingerprints, not raw IP addresses.</p><button type="button" class="secondary" id="intrusion-refresh">Refresh events</button><h4>Temporary blocks</h4>${r.blocks.length?'<ul>'+r.blocks.map(b=>`<li>${esc(b.key.slice(0,12))} · until ${esc(WorkspaceTime.stamp(b.blocked_until*1000))} <button type="button" class="secondary intrusion-unblock" data-source="${esc(b.key)}">Unblock</button></li>`).join('')+'</ul>':'<p>No active blocks.</p>'}<h4>Recent decoy events</h4>${r.events.length?'<div class="table-wrap"><table><thead><tr><th>Time</th><th>Source ID</th><th>Decoy</th><th>Action</th></tr></thead><tbody>'+r.events.map(e=>`<tr><td>${esc(WorkspaceTime.stamp(e.at*1000))}</td><td>${esc(e.source_key.slice(0,12))}</td><td>${esc(e.kind)}</td><td>${esc(e.action)}</td></tr>`).join('')+'</tbody></table></div>':'<p>No recorded events.</p>'}`);
  formHandler('#intrusion-policy',async d=>{reauthenticate('Change intrusion protection','Confirm this owner-only security setting.',async auth=>{await api('security/intrusion',{...auth,mode:d.intrusion_mode},'PUT');await Security.settings();toast('Intrusion protection updated.');});});
  bind('#intrusion-refresh',()=>Security.settings());
  document.querySelectorAll('.intrusion-unblock').forEach(b=>b.onclick=()=>reauthenticate('Unblock source','Remove this temporary block and its request count.',async auth=>{await api('security/intrusion/unblock',{...auth,source_key:b.dataset.source});await Security.settings();toast('Source unblocked.');}));
 }
 return {capture,pending:()=>!!token,reset,request,agent,intrusion};
})();
