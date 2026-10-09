'use strict';
const Security=(()=>{
 function gate(title,description,body){
  $('#root').innerHTML=`<div class="security-gate"><div class="card"><div class="brand"><img class="brandmark" src="/static/expense-pilot-logo.png" alt="">expense pilot</div><h1>${title}</h1><p class="muted">${description}</p>${body}<button class="ghost" id="cancel-signin">Back to sign in</button></div></div>`;
  bind('#cancel-signin',async()=>{await api('logout',{});await boot();});
 }
 function challenge(){
  gate('Verify your sign-in','Enter the code from your authenticator app, or one of your saved recovery codes.',`<form id="factor-form">${field('Authenticator or recovery code','code','text','','required autocomplete="one-time-code" maxlength="40" autofocus')}<button type="submit">Verify and sign in</button></form>`);
  formHandler('#factor-form',async d=>{await api('login/2fa',d);await boot();});
 }
 function changeRequired(){
  gate('Choose your own password','Replace your temporary password before opening the workspace.',`<form id="first-password">${field('Temporary password','current','password','','required autocomplete="current-password"')}${field('New password','password','password','','required minlength="12" maxlength="256" autocomplete="new-password"')}${field('Confirm new password','confirm','password','','required minlength="12" maxlength="256" autocomplete="new-password"')}<button type="submit">Save new password</button></form>`);
  formHandler('#first-password',async d=>{if(d.password!==d.confirm)throw Error('The new passwords do not match.');await api('password',d);toast('Password saved. Sign in with your new password.');await boot();});
 }
 async function settings(){
  const data=await api('security');if(page!=='settings')return;
  $('#security-settings').innerHTML=`<h2>Two-factor authentication</h2>${!data.secure_cookies?'<p class="notice">Secure-only cookies are disabled. When using HTTPS, set COOKIE_SECURE=true on your server.</p>':''}<p>${data.enabled?'Enabled — sign-in requires a code from your authenticator.':'Add an authenticator code to protect your account.'}</p>${data.enabled?`<p class="footnote">${data.recovery_remaining} unused recovery codes remaining.</p><button class="secondary" id="disable-2fa">Turn off 2FA</button>`:'<button id="enable-2fa">Set up authenticator</button>'}`;
  bind('#enable-2fa',setup);bind('#disable-2fa',disable);
  if(owner()){
   const config=await api('security/invitations');if(page!=='settings')return;
   $('#invitation-settings').innerHTML=`<h2>Account invitations</h2><p>Invited tax agents receive an email with an automatically generated password. They must replace it on their first sign-in.</p><form id="invitation-config">${field('Expense Pilot login address','login_url','url',config.login_url,'required placeholder="https://expenses.example.com"')}<p class="footnote">Use the address your invited people can reach. ${config.smtp_configured?'Email delivery is configured.':'Configure Email delivery & templates below before inviting people.'}</p><button type="submit">Save invitation settings</button></form>`;
   formHandler('#invitation-config',async d=>{await api('security/invitations',d,'PUT');toast('Invitation settings saved.');});
  }
 }
 function setup(){
  modal('Set up two-factor authentication',`<form id="auth-start">${field('Current password','mfa_password','password','','required autocomplete="current-password"')}<button type="submit">Show authenticator QR code</button></form>`);
  formHandler('#auth-start',async d=>{
   const setup=await api('security/2fa/setup',{password:d.mfa_password});
   modal('Scan with your authenticator',`<p>Open your authenticator app, add an account and scan this QR code.</p><img class="auth-qr" src="${setup.qr}" alt="Authenticator setup QR code"><details><summary>Cannot scan? Enter the setup key manually</summary><p class="auth-secret">${esc(setup.secret)}</p><p>Time-based code · 6 digits · 30 seconds</p></details><form id="auth-confirm">${field('Six-digit authenticator code','setup_code','text','','required inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="one-time-code"')}<p class="footnote">Setup expires in 10 minutes. 2FA starts after your code is verified.</p><button type="submit">Verify and enable 2FA</button></form>`);
   formHandler('#auth-confirm',async d=>{
    const result=await api('security/2fa/confirm',{code:d.setup_code});S.csrf=result.csrf;S.user.totp_enabled=1;
    modal('Save your recovery codes',`<p>2FA is enabled. Keep these codes somewhere safe so you can sign in if you lose your phone. Each code works once; they are shown only now.</p><div class="recovery-codes">${result.recovery_codes.map(c=>`<code>${esc(c)}</code>`).join('')}</div><div class="modal-footer"><button type="button" class="secondary" id="download-recovery">Download recovery codes</button><button type="button" id="recovery-done">I have saved my codes</button></div>`);
    bind('#download-recovery',()=>{const content=`Expense Pilot recovery codes\nAccount: ${S.user.email}\nKeep these private. Each code works once.\n\n${result.recovery_codes.join('\n')}\n`;const url=URL.createObjectURL(new Blob([content],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download='expense-pilot-recovery-codes.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
    bind('#recovery-done',()=>{$('#modal').close();$('#modal').innerHTML='';render();});
   });
  });
 }
 function disable(){
  modal('Turn off two-factor authentication',`<form id="auth-disable">${field('Current password','disable_password','password','','required autocomplete="current-password"')}${field('Authenticator or recovery code','disable_code','text','','required autocomplete="one-time-code" maxlength="40"')}<button type="submit" class="danger">Turn off 2FA</button></form>`);
  formHandler('#auth-disable',async d=>{const result=await api('security/2fa/disable',{password:d.disable_password,code:d.disable_code});S.csrf=result.csrf;S.user.totp_enabled=0;$('#modal').close();$('#modal').innerHTML='';render();toast('Two-factor authentication disabled.');});
 }
 return {challenge,changeRequired,settings};
})();
