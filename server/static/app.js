'use strict';
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function themeControl(id){
 return typeof Theme==='undefined'?'':Theme.control(id);
}
const money=c=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format((c||0)/100),today=()=>WorkspaceTime.day();
let S={},E=[],T=[],A=[],U=[],V=[],page='dashboard',filters={scopes:['work','business','personal'],status:'all',search:'',fy:'all'};
const role=()=>S.user?.role,owner=()=>role()==='owner',bookkeeper=()=>owner()||(role()==='tax_agent'&&S.user.permission==='read_write'),editor=()=>bookkeeper();
const pageTitles={attention:'Needs attention',reconciliation:'Bank reconciliation',bank_accounts:'Accounts & feeds',bank_transfers:'Transfers',recurring_expenses:'Recurring expenses',rules:'Categorisation rules',payslip_checks:'Payslip checks',receipt_items:'Receipt items',drive_review:'Drive review',equipment:'Deductions',adviser_questions:'Adviser questions',annual_handover:'Annual handover',documents:'Documents',home_office:'Home office',budgets:'Category budgets',dashboard:'Overview',expenses:'Expenses',receipts:'Inbox',employment:'Employment income',tax:'Tax forecast',trips:'Trips & meals',vehicles:'Vehicles',banks:'Bank accounts',reports:'Expense reports',team:'Settings / Tax agent access',settings:'Settings',invoices:'Invoices',quotes:'Quotes',clients:'Clients',time:'Billable time',recurring:'Recurring invoices',services:'Services & prices',income:'Income report'};
const pageParents={reconciliation:'banks',bank_accounts:'banks',bank_transfers:'banks',budgets:'expenses',recurring_expenses:'expenses',rules:'expenses',payslip_checks:'employment',receipt_items:'expenses',drive_review:'vehicles',adviser_questions:'reports',annual_handover:'reports'};
let routesReady=false;
function pageFromURL(){const path=location.hash.startsWith('#/')?location.hash.slice(2):'';return path==='settings/tax-agent-access'?'team':path||'dashboard';}
function allowedPage(key){
 if(role()==='tax_agent')return TaxAgent.allowed(key);
 if(key==='review_tools')key='banks';
 if(pageParents[key]&&allowedPage(pageParents[key])!==pageParents[key])return 'dashboard';
 if(!Object.hasOwn(pageTitles,key))return 'dashboard';
 if(key==='team'&&!owner())return 'settings';
 const business=['invoices','quotes','clients','time','recurring','services','income'];
 const feature=business.includes(key)?'business':key;
 if((business.includes(key)||['employment','trips','vehicles','banks','tax','home_office'].includes(key))&&!Features.enabled(feature))return 'dashboard';
 if(role()==='employee'&&[...business,'employment','banks','tax','reports','home_office','documents'].includes(key))return 'dashboard';
 return key;
}
function pageURL(key){return '#/'+(key==='team'?'settings/tax-agent-access':key);}
async function navigate(key,{replace=false}={}){
 if(typeof BillingWorkspace!=='undefined'&&BillingWorkspace.active()){try{await BillingWorkspace.leave();}catch(e){toast(e.message);return;}}
 if(!routesReady)return;
 if(!Receipts.canLeaveReview()){
  if(location.hash!==pageURL(page))history.replaceState(null,'',pageURL(page));
  return;
 }
 page=allowedPage(key);const hash=pageURL(page);
 if(location.hash!==hash)history[replace?'replaceState':'pushState'](null,'',hash);
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());
 return render();
}
function restorePage(){if(routesReady&&((typeof BillingWorkspace!=='undefined'&&BillingWorkspace.active())||pageFromURL()!==page||location.hash!==pageURL(page)))navigate(pageFromURL(),{replace:true});}
window.addEventListener('popstate',restorePage);
window.addEventListener('hashchange',restorePage);
const scopeName=s=>({work:'Employment',business:'Business',personal:'Personal',split:'Split'}[s]||s);
const allocated=(e,scope='all')=>{const a=Splits.amounts(e);return scope==='work'?a.work:scope==='business'?a.business:scope==='personal'?0:a.work+a.business;};
let toastTimer;
function toast(t){clearTimeout(toastTimer);const element=$('#toast');element.textContent=t;element.style.display='block';toastTimer=setTimeout(()=>{element.style.display='none';toastTimer=null;},5500)}
const apiRequests=new Set();
let signingOut=false;
async function api(path,body,method='POST',options={}){
 if(signingOut)throw Error('Signing out. Please wait.');
 const logout=path==='logout';
 if(logout){
  signingOut=true;
  // Finish responses carrying the old session cookie before revoking it.
  // Chained background requests must not race the new sign-in session either.
  await Promise.allSettled([...apiRequests]);
 }
 const request=apiRequest(path,body,method,options);apiRequests.add(request);
 try{return await request;}finally{apiRequests.delete(request);if(logout)signingOut=false;}
}
async function apiRequest(path,body,method='POST',{timeoutMs=0}={}){
 const controller=new AbortController(),init={method:body===undefined?'GET':method,headers:{'X-CSRF-Token':S.csrf||''},signal:controller.signal};
 if(body!==undefined){if(body instanceof FormData)init.body=body;else{init.headers['Content-Type']='application/json';init.body=JSON.stringify(body);}}
 const timer=timeoutMs?setTimeout(()=>controller.abort(),timeoutMs):null;
 try{
  const r=await fetch('/api/'+path,init),raw=await r.text();let d;
  try{d=JSON.parse(raw);}catch{
   const recovery=path==='receipts'||path.startsWith('receipts/')?'Check the saved document in Document inbox before retrying.':'Check whether your changes were saved before retrying.';
   const message=[408,504,524].includes(r.status)?'The connection timed out. '+recovery:r.status===413?'The server rejected the upload size. Use a smaller file.':`The server returned an unexpected response (HTTP ${r.status}). ${recovery}`;
   const error=Error(message);error.status=r.status;error.transient=[408,502,503,504,520,522,524].includes(r.status);throw error;
  }
  if(!r.ok){const error=Error(typeof d?.error==='string'?d.error:`Request failed (HTTP ${r.status}).`);error.status=r.status;error.transient=[408,502,503,504,520,522,524].includes(r.status);throw error;}
  if(body!==undefined&&typeof Notifications!=='undefined')Notifications.invalidate();
  return d;
 }catch(error){
  if(error.name==='AbortError'||error instanceof TypeError){const connection=Error('Connection interrupted. Check whether the request completed before trying again.');connection.status=0;connection.transient=true;throw connection;}
  throw error;
 }finally{if(timer)clearTimeout(timer);}
}
async function readDocument(rid){
 let job=await api('receipts/'+rid+'/extract',{unfiled_only:true,background:true},'POST',{timeoutMs:20000});
 // A cached client/server pair may still use the synchronous endpoint during an update.
 if(!job.job_id)return job;
 const jobId=job.job_id,deadline=Date.now()+10*60*1000;let failures=0;
 while(job.status==='reading'){
  if(Date.now()>=deadline)throw Error('Reading is taking longer than expected. The original is saved; check Document inbox shortly.');
  await new Promise(resolve=>setTimeout(resolve,1500));
  try{job=await api('receipts/'+rid+'/extract?job='+encodeURIComponent(jobId),undefined,'GET',{timeoutMs:20000});failures=0;}
  catch(error){if(error.transient&&++failures<=3)continue;throw error;}
 }
 if(job.status==='failed'){const error=Error(job.error||'Document reading failed. Retry from Document inbox or enter the figures manually.');error.status=job.error_status;throw error;}
 if(job.status!=='complete')throw Error('Reading progress was interrupted. Check the saved draft in Document inbox before retrying.');
 return job.result;
}
function bind(id,fn){const el=$(id);if(el)el.addEventListener('click',fn)}
function dateAU(value){return String(value??'').replace(/^(\d{4})-(\d{2})-(\d{2})/, '$3/$2/$1');}
function dateISO(value){
 const text=String(value??'').trim();if(!text)return '';
 let y,m,d,match;
 if((match=/^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text))){[,y,m,d]=match;}
 else {
  if(/^(\d{6}|\d{8})$/.test(text)){d=text.slice(0,2);m=text.slice(2,4);y=text.slice(4);}
  else if((match=/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(text))){[,d,m,y]=match;}
  else throw Error('Enter a valid date, for example 8/10/2026 or 081026.');
  if(y.length===2)y='20'+y;
 }
 const iso=`${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`,parsed=new Date(iso+'T12:00:00Z');
 if(!Number(y)||!Number.isFinite(parsed.getTime())||parsed.toISOString().slice(0,10)!==iso)throw Error('Enter a real calendar date as DD/MM/YYYY.');
 return iso;
}
function normaliseDateInput(input){
 try{const iso=dateValue(input);input.value=dateAU(iso);input.setCustomValidity('');input.removeAttribute('aria-invalid');}
 catch(error){input.setCustomValidity(error.message);input.setAttribute('aria-invalid','true');}
}
document.addEventListener('focusout',event=>{if(event.target.matches('[data-date=au]'))normaliseDateInput(event.target);});
document.addEventListener('change',event=>{if(event.target.matches('[data-date=au]'))normaliseDateInput(event.target);},true);
document.addEventListener('input',event=>{if(event.target.matches('[data-date=au]')){event.target.setCustomValidity('');event.target.removeAttribute('aria-invalid');}});
function dateValue(input){const iso=dateISO(input.value);if(iso&&((input.dataset.min&&iso<input.dataset.min)||(input.dataset.max&&iso>input.dataset.max)))throw Error(`Date must be ${input.dataset.min?'on or after '+dateAU(input.dataset.min):''}${input.dataset.min&&input.dataset.max?' and ':''}${input.dataset.max?'on or before '+dateAU(input.dataset.max):''}.`);return iso;}
function field(label,name,type='text',value='',extra=''){if(type==='date'){type='text';value=dateAU(value);extra=extra.replace(/\b(min|max)=/g,'data-$1=')+' data-date="au" inputmode="numeric" placeholder="DD/MM/YYYY" maxlength="10"';}return `<div class="field"><label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`}
function select(label,name,options,value=''){return `<div class="field"><label for="${name}">${label}</label><select id="${name}" name="${name}">${options.map(([v,t])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(t)}</option>`).join('')}</select></div>`}
function formData(form){const data=Object.fromEntries(new FormData(form));form.querySelectorAll('[data-date=au]').forEach(input=>{if(!input.disabled)data[input.name]=dateValue(input);});return data;}
function undockModal(){
 const dialog=$('#modal');
 if(!dialog.classList.contains('receipt-docked'))return;
 if(dialog.open)dialog.close();
 dialog.classList.remove('receipt-docked');
 dialog.onclose=null;
 document.body.append(dialog);
}
function modal(title,html,{host=null,beforeClose=null}={}){
 const dialog=$('#modal');
 if(!host)undockModal();
 else if(dialog.parentElement!==host){
  if(dialog.open)dialog.close();
  host.append(dialog);
  dialog.classList.add('receipt-docked');
 }
 dialog.classList.remove('billing-dialog');
 dialog.setAttribute('aria-labelledby','modal-heading');
 dialog.innerHTML=`<div class="modal-title"><h2 id="modal-heading">${title}</h2><button type="button" class="ghost" id="close-modal" aria-label="Close">✕</button></div>${html}`;
 if(!dialog.open){if(host)dialog.show();else dialog.showModal();}
 bind('#close-modal',()=>{if(!beforeClose||beforeClose())dialog.close();});
}
function formHandler(id,fn){
 $(id).addEventListener('submit',async ev=>{
  ev.preventDefault();
  const form=ev.target;
  if(form.dataset.submitting)return;
  form.dataset.submitting='true';
  const buttons=[...document.querySelectorAll('button')].filter(b=>b.type==='submit'&&b.form===form);
  const disabled=buttons.map(b=>b.disabled);
  buttons.forEach(b=>b.disabled=true);
  try{await fn(formData(form),form,ev.submitter);}
  catch(err){
   let el=form.querySelector('.error');
   if(!el){el=document.createElement('div');el.className='error';form.append(el);}
   el.textContent=err.message;el.scrollIntoView({block:'nearest'});
  }finally{
   delete form.dataset.submitting;
   buttons.forEach((b,i)=>b.disabled=disabled[i]);
  }
 });
}
async function boot(){routesReady=false;undockModal();try{const previous=S.user?.id;S=await api('session');if(!S.user||S.user.id!==previous){document.querySelectorAll('#document-viewer,#home-office-import,#equipment-profile-dialog').forEach(d=>d.close());E=[];T=[];A=[];U=[];V=[];page='dashboard';$('#modal').close();$('#modal').innerHTML='';}if(S.mfa_required)return Security.challenge();if(!S.user)return login();if(S.user.must_change_password)return Security.changeRequired();await refresh();routesReady=true;navigate(pageFromURL(),{replace:true})}catch(e){$('#root').textContent=e.message}}
async function refresh(){if(role()==='tax_agent'){E=[];T=[];V=[];A=[];U=[];return;}[E,T,V]=await Promise.all([api('expenses'),api('trips'),api('vehicles')]);if(role()!=='employee')A=await api('accounts');if(owner())U=await api('users')}
function login(){const setup=S.setup;$('#root').innerHTML=`<div class="login"><div class="login-aside"><div class="brand"><img class="brandmark" src="/static/expense-pilot-logo.png" alt="">expense pilot</div><h1>a clearer view of<br>every dollar</h1><p>Expense tracking for sole traders and people claiming employment expenses.</p><div class="login-tag">YOUR EXPENSES. YOUR SERVER.</div></div><div class="login-main"><form class="login-form" id="login-form"><h2>${setup?'Make yourself at home.':'Good to see you.'}</h2><p>${setup?'Create your owner account to get started.':'Sign in to your expense workspace.'}</p>${setup?(S.setup_token_required?field('Setup token','token','password','','required'):'')+field('Your name','name','text','','required')+WorkspaceTime.fieldHTML(WorkspaceTime.suggested()):''}${field('Email address','email','email','','required autocomplete="username"')}${field('Password','password','password','','required autocomplete="'+(setup?'new-password':'current-password')+'" '+(setup?'minlength="12"':''))}${location.protocol!=='https:'?'<p class="notice">This connection is not encrypted. Use your HTTPS address or a trusted VPN before entering financial details.</p>':''}<button type="submit">${setup?'Create workspace':'Sign in'} →</button><p class="footnote">Expense Pilot v${esc(S.version)} · Self-hosted expense manager · <a href="/privacy" target="_blank">Privacy & data</a> · <a href="/about" target="_blank" rel="noopener">Source & licences</a></p></form></div></div>`;if(setup)WorkspaceTime.loadChoices();formHandler('#login-form',async d=>{await api(setup?'setup':'login',d);if(setup)toast('Owner account created. Sign in to continue.');await boot()})}
function navItem(key,icon,label){return `<button data-page="${key}" class="${page===key||pageParents[page]===key||page==='team'&&key==='settings'?'active':''}"><span class="nav-icon">${icon}</span>${label}</button>`}
function render(){
 undockModal();
 if(role()==='tax_agent'){page=allowedPage(page);if(location.hash!==pageURL(page))history.replaceState(null,'',pageURL(page));TaxAgent.render();return;}
 page=allowedPage(page);
 if(location.hash!==pageURL(page))history.replaceState(null,'',pageURL(page));
 const title=pageTitles[page];
 document.title=title+' · Expense Pilot';
 $('#root').innerHTML=`<div class="shell pilot-shell">
  <aside class="sidebar">
   <div class="brand"><img class="brandmark" src="/static/expense-pilot-logo.png" alt=""><div>Expense Pilot<small>A clearer view of every dollar</small></div></div>
   <nav class="workspace-navigation" aria-label="Main navigation">${WorkspaceUI.navigation()}
    <button type="button" id="workspace-more" class="workspace-more" aria-haspopup="dialog" aria-expanded="false" aria-controls="workspace-more-menu">${WorkspaceUI.icon('dots')}<span>More</span></button>
   </nav>
   <div class="sidebar-bottom">
    <div class="workspace"><span class="avatar">${esc(S.user.name.split(' ').map(n=>n[0]).slice(0,2).join(''))}</span><div><strong>${esc(S.user.name)}</strong><small id="workspace-business">${Features.enabled('business')?esc(S.business_name||'Your workspace'):'Employment expenses'}</small></div></div>
    ${themeControl()}<button id="logout" class="ghost wide">Sign out ↪</button>
    <small>Expense Pilot · v${esc(S.version)} · <a href="/about" target="_blank" rel="noopener">Source & licences</a></small>
   </div>
  </aside>
  <main class="main"><div class="topline"><span class="workspace-breadcrumb">Workspace ${WorkspaceUI.icon('chev')} <strong>${title}</strong></span>
   <span class="mobile-brand"><img src="/static/expense-pilot-logo.png" alt="">Expense Pilot</span>
   <span class="mobile-theme">${themeControl('mobile-theme-choice')}</span><div class="topline-actions"><span class="desktop-private">AUD</span><div id="notification-bell"></div></div></div>
   <div id="content" data-workspace-page="${page}"></div>
  </main>
  ${WorkspaceUI.moreMenu()}
 </div>`;
 WorkspaceUI.mountRecords();
 Notifications.mount();
 const logout=async()=>{
  if(!Receipts.canLeaveReview())return;
  await api('logout',{});
  history.replaceState(null,'',pageURL('dashboard'));
  await boot();
 };
 WorkspaceUI.bindNavigation(logout);
 bind('#logout',logout);
 return ({attention:Workflows.attention,reconciliation:()=>Workflows.page('reconciliation'),rules:()=>Workflows.page('rules'),payslip_checks:()=>Workflows.page('income'),receipt_items:()=>Workflows.page('items'),drive_review:()=>Workflows.page('journeys'),equipment:()=>Workflows.page('equipment'),adviser_questions:()=>Workflows.page('questions'),annual_handover:()=>Workflows.page('handover'),documents:Documents.page,home_office:HomeOffice.page,budgets:Planning.budgets,dashboard:Workspace.dashboard,expenses:expensePage,receipts:Receipts.page,employment:Finance.employment,tax:Finance.tax,trips:tripPage,vehicles:Tracking.vehicles,banks:bankPage,bank_accounts:bankPage,bank_transfers:ExpenseReview.transfers,recurring_expenses:ExpenseReview.recurring,reports:Workspace.reports,team:teamPage,settings:settingsPage,invoices:()=>Billing.documents('invoice'),quotes:()=>Billing.documents('quote'),clients:Billing.clients,time:Billing.time,recurring:Billing.recurring,services:Billing.services,income:Billing.income}[page])();
}
let menuNumber=0;
function actionMenu(label,contents){const id='actions-'+(++menuNumber);return `<span class="action-menu"><button type="button" class="ghost menu-trigger" popovertarget="${id}" aria-label="${esc(label)}" aria-haspopup="true" aria-expanded="false">⋯</button><span class="action-popup" id="${id}" popover>${contents}</span></span>`;}
document.addEventListener('toggle',event=>{const menu=event.target;if(!menu.classList?.contains('action-popup'))return;document.querySelector(`[popovertarget="${menu.id}"]`)?.setAttribute('aria-expanded',String(event.newState==='open'));},true);
document.addEventListener('click',event=>{
 const trigger=event.target.closest('.menu-trigger');
 if(trigger){event.preventDefault();const menu=document.getElementById(trigger.getAttribute('popovertarget'));if(menu.matches(':popover-open')){menu.hidePopover();return;}const r=trigger.getBoundingClientRect();menu.showPopover();const width=menu.getBoundingClientRect().width,height=menu.getBoundingClientRect().height;menu.style.left=Math.max(8,Math.min(innerWidth-width-8,(menu.classList.contains('nav-popup')&&innerWidth>760?r.right+12:r.right-width)))+'px';menu.style.top=Math.max(8,Math.min(innerHeight-height-8,r.bottom+6))+'px';menu.querySelector('button,a')?.focus({preventScroll:true});return;}
 const menu=event.target.closest('.action-popup');if(menu&&event.target.closest('button,a')&&menu.matches(':popover-open'))menu.hidePopover();
});
document.addEventListener('keydown',event=>{const menu=event.target.closest('.action-popup');if(!menu||!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;const items=[...menu.querySelectorAll('button:not(:disabled),a')],i=items.indexOf(document.activeElement);event.preventDefault();items[event.key==='Home'?0:event.key==='End'?items.length-1:(i+(event.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();});
function heading(title,sub,action=''){return `<div class="heading"><div><h1>${title}</h1><p>${sub}</p></div><div class="actions">${action}</div></div>`}
function fyBounds(v){const y=Number(v);return [y+'-07-01',(y+1)+'-06-30']}
function fyOptions(){const yrs=new Set(E.map(e=>{let y=Number(e.date.slice(0,4));return Number(e.date.slice(5,7))>=7?y:y-1}));const now=today();let y=Number(now.slice(0,4))-(Number(now.slice(5,7))<7?1:0);yrs.add(y);return [['all','All financial years'],...[...yrs].sort((a,b)=>b-a).map(y=>[y,`FY ${y}–${String(y+1).slice(-2)}`])]}
function categoryLabel(key){return S?.category_labels&&Object.hasOwn(S.category_labels,key)?S.category_labels[key]:key;}
let expenseSort={key:'date',direction:-1};
function sortedExpenses(data){const key=expenseSort.key,dir=expenseSort.direction;return [...data].sort((a,b)=>{const value=e=>key==='category'?categoryLabel(e.category):key==='workspace'?[e.work_percent?'Employment':'',e.business_percent?'Business':'',e.work_percent+e.business_percent<100?'Personal':''].filter(Boolean).join(' + '):e[key];const x=value(a),y=value(b);return (typeof x==='number'&&typeof y==='number'?x-y:String(x??'').localeCompare(String(y??''),'en-AU',{numeric:true,sensitivity:'base'}))*dir||(Number(b.id)-Number(a.id));});}
function expenseHeading(label,key,right=false){const active=expenseSort.key===key;return `<th ${right?'class="right"':''} aria-sort="${active?(expenseSort.direction===1?'ascending':'descending'):'none'}"><button type="button" class="sort-expenses" data-sort="${key}" aria-label="Sort by ${label}">${label} <span aria-hidden="true">${active?(expenseSort.direction===1?'↑':'↓'):'↕'}</span></button></th>`;}
function filtered(){return E.filter(e=>!Overnights.isOvernight(e)&&filters.scopes.some(scope=>Splits.matches(e,scope))&&(filters.status==='all'||e.status===filters.status)&&(!filters.search||(e.merchant+' '+categoryLabel(e.category)+' '+e.notes).toLowerCase().includes(filters.search.toLowerCase()))&&(filters.fy==='all'||(e.date>=fyBounds(filters.fy)[0]&&e.date<=fyBounds(filters.fy)[1])))}
function table(data,limit,sortable=false){const ordered=sortable?sortedExpenses(data):data,r=limit?ordered.slice(0,limit):ordered;return `<div class="table-wrap"><table><thead><tr>${sortable?[["Expense","merchant"],["Date","date"],["Allocation","workspace"],["Category","category"],["Status","status"],["Amount","amount_cents"]].map(([n,k])=>expenseHeading(n,k,k==="amount_cents")).join(''):'<th>Expense</th><th>Date</th><th>Workspace</th><th>Category</th><th>Status</th><th class="right">Amount</th>'}<th></th></tr></thead><tbody>${r.map(e=>`<tr><td><div class="merchant"><span class="merchant-icon">${esc(e.merchant.slice(0,1).toUpperCase())}</span><div><strong>${esc(e.merchant)}</strong><br><small>${esc(e.owner)} ${e.receipt_id?'· Receipt attached':''}</small></div></div></td><td>${esc(dateAU(e.date))}</td><td>${Splits.badges(e)}</td><td>${esc(categoryLabel(e.category))}</td><td><span class="pill ${e.status}">${e.status==='review'?'To review':'Reviewed'}</span></td><td class="right"><strong>${money(e.amount_cents)}</strong></td><td><button class="ghost edit-expense" data-id="${e.id}" aria-label="${editor()?'Edit':'View'} ${esc(e.merchant)}">${editor()?'Edit':'View'} ↗</button>${actionMenu('Expense actions for '+e.merchant,`<button class="edit-expense" data-id="${e.id}">${editor()?'Edit expense':'View details'}</button>${owner()&&Features.enabled('business')&&allocated(e,'business')>0?`<button class="billable-expense" data-id="${e.id}">Bill to client</button>`:''}${e.receipt_id?`<button class="row-view-receipt" data-rid="${e.receipt_id}">View receipt</button>`:''}`)}</td></tr>`).join('')}</tbody></table>${!r.length?`<div class="empty"><div class="bubble">▤</div><h2>No expenses here yet</h2><p>${editor()?'Add a receipt or enter your first expense.':'All workspace records will appear here.'}</p></div>`:''}</div>`}
function tableEvents(){document.querySelectorAll('.billable-expense').forEach(b=>b.onclick=()=>ExpenseReview.markBillable(E.find(e=>e.id===Number(b.dataset.id))).catch(e=>toast(e.message)));document.querySelectorAll('.sort-expenses').forEach(b=>b.onclick=()=>{expenseSort=expenseSort.key===b.dataset.sort?{key:b.dataset.sort,direction:-expenseSort.direction}:{key:b.dataset.sort,direction:1};$('#expense-table').innerHTML=table(filtered(),null,true);tableEvents();$('#expense-table [data-sort="'+expenseSort.key+'"]')?.focus();});document.querySelectorAll('.row-view-receipt').forEach(b=>b.onclick=()=>Receipts.preview(b.dataset.rid));document.querySelectorAll('.edit-expense').forEach(b=>b.onclick=()=>expenseModal(E.find(e=>e.id===Number(b.dataset.id))))}
function expenseChart(){const now=today(), start=new Date(now.slice(0,7)+'-01T00:00:00Z'), months=[];for(let i=5;i>=0;i--){const d=new Date(start);d.setUTCMonth(start.getUTCMonth()-i);const key=d.toISOString().slice(0,7);months.push({label:d.toLocaleDateString('en-AU',{month:'short',timeZone:'UTC'}),amount:E.filter(e=>!Overnights.isOvernight(e)&&e.date.startsWith(key)).reduce((s,e)=>s+allocated(e),0)});}const max=Math.max(...months.map(x=>Math.abs(x.amount)),1);return `<div class="monthly-chart">${months.map(m=>`<div class="month-col"><div class="month-amount">${money(m.amount)}</div><div class="chart-bar" data-height="${Math.max(2,Math.round(Math.abs(m.amount)/max*100))}"></div><small>${m.label}</small></div>`).join('')}</div><div class="chart-caption"><i></i> Employment + business · allocated amounts</div>`;}
function employeeDashboard(){const work=E.filter(e=>!Overnights.isOvernight(e)).reduce((s,e)=>s+allocated(e,'work'),0),business=E.filter(e=>!Overnights.isOvernight(e)).reduce((s,e)=>s+allocated(e,'business'),0),review=E.filter(e=>e.status==='review'&&!e.meal&&e.category!=='Meals').length,meals=E.filter(e=>e.meal).reduce((s,e)=>s+e.amount_cents,0);$('#content').innerHTML=heading(`Your expenses, in order.`,`${S.user.name.split(' ')[0]}, here’s the picture across your workspace.`,editor()?'<button class="secondary" id="quick-capture">▣ Capture documents</button><button id="add">+ Add expense</button>':'<span class="pill">Read-only access</span>')+`<div class="cards"><div class="card feature"><div class="label">Employment expenses</div><div class="metric">${money(work)}</div><small>Allocated amount · all dates</small></div><div class="card"><div class="label">Business expenses</div><div class="metric">${money(business)}</div><small>Allocated amount · all dates</small></div><div class="card"><div class="label">Overnight meals</div><div class="metric">${money(meals)}</div><small>Actual spend linked to trips</small></div><div class="card"><div class="label">Needs a little attention</div><div class="metric">${review}<span class="muted"> ↗</span></div><small>Expenses waiting for review</small></div></div><div class="section-grid"><section class="card"><div class="section-title"><h2>Expense activity</h2><span class="pill">Last 6 months</span></div>${expenseChart()}<p class="footnote">Use percentage applied. Personal and reimbursed expenses excluded.<br>Allocation is a recordkeeping figure, not a tax deduction decision.</p></section><section class="card"><div class="section-title"><h2>Stay on top of the details</h2><span>✧</span></div><div class="review-box"><div class="bubble">▤</div><div><strong>${review?`${review} expenses to check`:'You’re all caught up'}</strong><br><small>Review the details. Keep the evidence.</small></div></div><button class="secondary wide" id="review">Open expense inbox →</button></section></div><section class="panel"><div class="panel-header"><h2>Recent expenses</h2><button class="ghost" id="all">View all →</button></div>${table(E.filter(e=>!e.meal&&e.category!=='Meals'),6)}</section><p class="footnote">${role()==='tax_agent'?'All workspace financial records are visible to your tax-agent account.':'Amounts are in Australian dollars. All financial years are included in this overview.'}</p>`;document.querySelectorAll('[data-height]').forEach(b=>b.style.height=b.dataset.height+'px');document.querySelectorAll('[data-width]').forEach(b=>b.style.width=b.dataset.width+'%');bind('#add',()=>expenseModal());bind('#quick-capture',Receipts.capture);bind('#all',()=>{navigate('expenses')});bind('#review',()=>{filters.status='review';navigate('expenses')});tableEvents()}
function expensePage(){
 const bounds=filters.fy==='all'?['','']:fyBounds(filters.fy);
 const exportURL='/api/export?'+new URLSearchParams({start:bounds[0],end:bounds[1],ledger:'ordinary'});
 const actions=editor()?`<button type="button" class="secondary" id="quick-capture">${WorkspaceUI.icon('scan')} Capture documents</button><a class="button-link secondary" href="${esc(exportURL)}" title="Export all allocations for the selected financial year">${WorkspaceUI.icon('download')} Export CSV</a><button id="add">${WorkspaceUI.icon('plus')} Add expense</button>`:'';
 $('#content').innerHTML=heading('Expenses','Review and organise your ordinary expenses.',actions)+`
  ${Workflows.links('expenses')}
  <section class="panel expenses-ledger">
   <div class="toolbar expense-filters">
    <label class="expense-search">${WorkspaceUI.icon('search')}<input id="search" placeholder="Search merchant, category or notes…" aria-label="Search expenses" value="${esc(filters.search)}"></label>
    <details class="workspace-filter"><summary id="workspace-filter-label"></summary><fieldset aria-label="Workspaces"><legend>Show expenses allocated to</legend>
     ${[['work','Employment'],['business','Business'],['personal','Personal']].map(([value,label])=>`<label class="check"><input type="checkbox" name="expense-scope" value="${value}" ${filters.scopes.includes(value)?'checked':''}>${label}</label>`).join('')}
     <button type="button" class="ghost" id="all-workspaces">Select all</button></fieldset></details>
    <select id="status" aria-label="Review status"><option value="all">All statuses</option><option value="review">To review</option><option value="ready">Reviewed</option></select>
    <select id="fy" aria-label="Financial year">${fyOptions().map(([value,label])=>`<option value="${value}" ${String(value)===filters.fy?'selected':''}>${label}</option>`).join('')}</select>
   </div>
   <div id="expense-table"></div>
   <div class="expense-ledger-footer"><span id="count" aria-live="polite"></span><span>Total shown <strong id="expense-filter-total"></strong></span></div>
  </section>
  <p class="footnote">Mixed-use expenses appear once. Find meals and trip records in Overnight spending.</p>`;
 function redraw(){
  const records=filtered();
  $('#workspace-filter-label').textContent=filters.scopes.length===3?'All workspaces':filters.scopes.map(scopeName).join(' + ')||'No workspaces';
  $('#expense-table').innerHTML=table(records,null,true);
  $('#count').textContent=`${records.length} expenses`;
  $('#expense-filter-total').textContent=money(records.reduce((sum,record)=>sum+record.amount_cents,0));
  tableEvents();
 }
 $('#status').value=filters.status;
 document.querySelectorAll('[name=expense-scope]').forEach(input=>input.onchange=()=>{
  filters.scopes=[...document.querySelectorAll('[name=expense-scope]:checked')].map(el=>el.value);
  redraw();
 });
 bind('#all-workspaces',()=>{filters.scopes=['work','business','personal'];expensePage();});
 $('#status').onchange=e=>{filters.status=e.target.value;redraw();};
 $('#fy').onchange=e=>{filters.fy=e.target.value;expensePage();$('#fy').focus();};
 $('#search').oninput=e=>{filters.search=e.target.value;redraw();};
 bind('#add',()=>expenseModal());
 bind('#quick-capture',Receipts.capture);
 bind('#manage-expense-categories',()=>Tracking.categories());
 redraw();
}
function expenseModal(e,mealTrip=null,captured=null){if(!editor()){modal('Expense details',`<div class="grid2">${['merchant','date','scope','category','owner','meal','location','status','notes'].map(k=>`<div class="field"><label>${k}</label><p>${esc(k==='date'?dateAU(e[k]):e[k]||'—')}</p></div>`).join('')}<div><strong>${money(e.amount_cents)}</strong><p>${Splits.percentages(e).work}% employment · ${Splits.percentages(e).business}% business · ${100-e.percent}% personal · ${e.reimbursed?'Reimbursed':'Not reimbursed'}</p></div></div>${e.receipt_id?`<button id="view-receipt" data-rid="${e.receipt_id}">View receipt</button>`:''}`);bind('#view-receipt',()=>Receipts.preview(e.receipt_id));return}
const x=e||{date:mealTrip?mealTrip.start:today(),scope:mealTrip?mealTrip.scope:Features.defaultScope(),percent:100,amount_cents:0,status:'review',category:mealTrip?'Meals':'Other',trip_id:mealTrip?.id,meal:mealTrip?'Dinner':''};if(captured)Object.assign(x,captured);const isMeal=!!(mealTrip||x.meal||x.category==='Meals');let receiptId=x.receipt_id||null;
modal(isMeal?(e?'Edit meal':'Add overnight meal'):(e?'Edit expense':'Add an expense'),`<form id="expense-form"><div class="drop"><strong>Start with a receipt</strong><p>Attach a photo or PDF, then use AI to fill the details for your review.</p><input id="receipt-file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" aria-label="Receipt file"><div class="receipt-actions"><button type="button" class="secondary" id="extract" ${!receiptId||!S.ai_configured?'disabled':''}>✧ Read with AI</button><span id="receipt-status" class="muted">${receiptId?'Receipt attached':S.ai_configured?'AI enabled in configuration':'AI not configured · manual entry available'}</span></div>${receiptId?`<button type="button" class="ghost" id="view-receipt">View receipt</button>`:''}</div><div class="grid2">${field('Merchant / payee','merchant','text',x.merchant||'','required maxlength="200"')}${field('Date','date','date',x.date,'required')}${field('Amount paid (AUD)','amount','number',(e||captured)&&x.amount_cents!=null?(x.amount_cents/100).toFixed(2):'','required step="0.01"')}${select('Category','category',S.categories.filter(c=>isMeal?c==='Meals':c!=='Meals').map(c=>[c,categoryLabel(c)]),x.category)}${select('Vehicle (optional)','vehicle_id',[['','Not a vehicle expense'],...V.filter(v=>v.user_id===(e?e.user_id:V.find(v=>v.id===x.vehicle_id)?.user_id||S.user.id)).map(v=>[v.id,v.name])],x.vehicle_id)}${Splits.fields(x,'',role()==='employee'||U.find(u=>u.id===x.user_id)?.role==='employee')}${isMeal?`${select('Overnight trip','trip_id',[['','No trip'],...T.filter(t=>t.user_id===(e?e.user_id:mealTrip?mealTrip.user_id:owner()||role()==='employee'?S.user.id:t.user_id)).map(t=>[t.id,`${t.location} · ${esc(dateAU(t.start))} · ${scopeName(t.scope)}`])],x.trip_id)}${select('Meal type','meal',[['','Not an overnight meal'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],x.meal)}`:''}${bookkeeper()?select('Paid from','account_id',[['','Cash / other'],...A.map(a=>[a.id,a.name])],x.account_id):''}${select('Review status','expense_status',[['review','To review'],['ready','Reviewed']],x.status)}</div>${bookkeeper()&&!isMeal?'<button type="button" class="ghost" id="create-inline-category">+ Create expense category</button>':''}<div class="field"><label for="notes">Notes / business purpose</label><textarea id="notes" name="notes">${esc(x.notes||'')}</textarea></div><label class="check"><input type="checkbox" name="reimbursed" ${x.reimbursed?'checked':''}>Reimbursed — exclude from allocated amount</label><p class="footnote">Refund? Enter a negative amount. AI suggestions need checking; foreign-currency receipts must be converted to AUD before saving.</p><div class="modal-footer">${e?'<button type="button" class="danger" id="delete">Delete</button>':''}<button type="submit">Save expense</button></div></form>`);
const treatment=!isMeal?TaxTreatment.mount($('#expense-form'),()=>{const f=$('#expense-form'),d=Object.fromEntries(new FormData(f));return {...d,date:dateValue(f.elements.date),reimbursed:f.elements.reimbursed.checked};},x):null;
bind('#view-receipt',()=>Receipts.preview(receiptId));bind('#create-inline-category',()=>createInlineCategory('#category'));
$('#receipt-file').onchange=async()=>{const f=$('#receipt-file').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);if(mealTrip)fd.append('trip_id',mealTrip.id);if(e)fd.append('expense_id',e.id);const save=$('#expense-form [type=submit]');save.disabled=true;$('#receipt-status').textContent='Uploading…';try{const r=await api('receipts',fd);receiptId=r.id;$('#receipt-status').textContent=r.filename;$('#extract').disabled=!S.ai_configured}catch(err){toast(err.message);$('#receipt-status').textContent='Upload failed'}finally{save.disabled=false}};
Splits.bindFields();
if(!Features.enabled('vehicles')&&!x.vehicle_id)$('#expense-form #vehicle_id').closest('.field').hidden=true;
if(!Features.enabled('banks')&&!x.account_id)$('#expense-form #account_id')?.closest('.field').setAttribute('hidden','');
bind('#extract',async()=>{const b=$('#extract');b.disabled=true;b.textContent='Reading receipt…';try{const d=await api(`receipts/${receiptId}/extract`,{});for(const k of ['merchant','date','category','notes'])if(d[k]!=null&&(k!=='category'||isMeal||d[k]!=='Meals'))$('#expense-form').elements[k].value=k==='date'?dateAU(d[k]):d[k];if(d.amount!=null&&String(d.currency).toUpperCase()==='AUD'){$('#amount').value=d.amount;$('#amount').dispatchEvent(new Event('input'));}else if(d.amount!=null){$('#notes').value+=`\nReceipt total: ${d.amount} ${d.currency}. Convert to AUD.`;$('#amount').value=''}$('#receipt-status').textContent='AI draft ready — check every field.'}catch(err){toast(err.message)}finally{b.disabled=false;b.textContent='✧ Read with AI'}});
formHandler('#expense-form',async(d,f)=>{d.scope=Splits.scope(d,role()==='employee'||U.find(u=>u.id===x.user_id)?.role==='employee');d.status=d.expense_status;delete d.expense_status;d.reimbursed=f.elements.reimbursed.checked;d.shared=true;if(!isMeal){d.trip_id=x.trip_id||null;d.meal='';}else{d.category='Meals';}d.receipt_id=receiptId;if(!e&&x.bank_transaction_id)for(const k of ['bank_transaction_id','bank_transaction_version','bank_confirm_new','bank_confirm_refund'])d[k]=x[k];if(!bookkeeper())d.account_id=e?.account_id||null;const tax=await treatment?.payload();if(tax)d.tax_treatment=tax;await api(e?'expenses/'+e.id:'expenses',d,e?'PUT':'POST');$('#modal').close();await refresh();render();toast('Expense saved')});bind('#delete',async()=>{if(!confirm('Permanently delete this expense and its attached receipt? They will be removed from Expenses and Document inbox. This cannot be undone.'))return;await api('expenses/'+e.id,{},'DELETE');$('#modal').close();await refresh();render();toast('Expense deleted')})}

let tripFilters={search:'',scope:'all',meal:'all',from:'',to:''};
function allowanceField(cents=0){return `<details class="span2 allowance-details" ${cents?'open':''}><summary>Employer allowance (optional)</summary><p class="footnote">Only fill this in if your employer paid you an overnight travel allowance. It is kept for reference; it does not reduce meal costs or feed into the tax forecast. Leave blank if none was received.</p>${field('Allowance received (AUD)','allowance','number',cents?(cents/100).toFixed(2):'','step="0.01" min="0"')}</details>`;}
function tripPage(){
 $('#content').innerHTML=heading('Overnight spending','Meals, incidentals and trip receipts, separate from ordinary expense claims.',editor()?'<button id="add-trip">+ Add overnight trip</button>':'')+`<div class="toolbar trip-filters"><div class="field"><label for="trip-search">Search trips & meals</label><input id="trip-search" placeholder="Location, merchant or purpose…" value="${esc(tripFilters.search)}"></div>${select('Trip workspace','trip-scope',[['all','All workspaces'],...(role()==='employee'?[['business','Business']]:[['work','Employment'],['business','Business'],['personal','Personal']])],tripFilters.scope)}${select('Filter meal type','trip-meal',[['all','All meal types'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],tripFilters.meal)}${field('From date','trip-from','date',tripFilters.from)}${field('To date','trip-to','date',tripFilters.to)}<button class="secondary" id="clear-trip-filters">Clear filters</button><p class="error" id="trip-filter-error" role="status"></p></div><p class="footnote" id="trip-count" aria-live="polite"></p><div id="trip-results"></div>`;
 $('#trip-search').oninput=e=>{tripFilters.search=e.target.value;tripResults();};
 ['scope','meal'].forEach(k=>$('#trip-'+k).onchange=e=>{tripFilters[k]=e.target.value;tripResults();});
 ['from','to'].forEach(k=>$('#trip-'+k).onchange=()=>{try{const from=dateValue($('#trip-from')),to=dateValue($('#trip-to'));if(from&&to&&from>to)throw Error('From date must be on or before To date.');tripFilters.from=from;tripFilters.to=to;$('#trip-filter-error').textContent='';tripResults();}catch(e){$('#trip-filter-error').textContent=e.message;}});
 bind('#clear-trip-filters',()=>{tripFilters={search:'',scope:'all',meal:'all',from:'',to:''};tripPage();});tripResults();
}
function tripResults(){const f=tripFilters,q=f.search.trim().toLowerCase(),scope=x=>x.amount_cents!=null?Splits.matches(x,f.scope):f.scope==='all'||x.scope===f.scope,has=text=>!q||String(text).toLowerCase().includes(q),tripText=t=>[t.location,t.purpose,t.owner].join(' '),tripById=new Map(T.map(t=>[t.id,t]));
 const shownMeals=E.filter(e=>Overnights.isOvernight(e)&&scope(e)&&(f.meal==='all'||e.meal===f.meal)&&(!f.from||e.date>=f.from)&&(!f.to||e.date<=f.to)&&has([e.merchant,e.notes,e.meal,e.owner,tripText(tripById.get(e.trip_id)||{})].join(' ')));
 const shownTrips=T.filter(t=>scope(t)&&(!f.from||t.end>=f.from)&&(!f.to||t.start<=f.to)&&(f.meal==='all'?has(tripText(t))||shownMeals.some(e=>e.trip_id===t.id):shownMeals.some(e=>e.trip_id===t.id)));
 $('#trip-count').textContent=`${shownTrips.length} trips · ${shownMeals.length} matching meals`;
 $('#trip-results').innerHTML=`<div class="notice">Trip cards show all linked spending for each matching trip. Matching meals below follow your search and filters. Allowances are recorded separately. Review the trip before including eligible actual costs in your forecast.</div>${shownMeals.some(e=>!e.trip_id)?`<section class="panel"><div class="panel-header"><h2>Meals needing a trip</h2></div>${table(shownMeals.filter(e=>!e.trip_id))}</section>`:''}<div class="grid3">${shownTrips.map(t=>{const m=E.filter(e=>e.trip_id===t.id);return `<section class="card trip"><div class="section-title"><span class="bubble">☾</span><span class="pill ${t.scope}">${scopeName(t.scope)}</span></div><h2>${esc(t.location)}</h2><p class="dates">${esc(dateAU(t.start))} → ${esc(dateAU(t.end))} · ${Math.round((Date.parse(t.end)-Date.parse(t.start))/86400000)} night(s)</p><p>${esc(t.purpose)}</p><p class="footnote">${esc(t.owner||'')}${t.allowance_cents?' · Allowance received '+money(t.allowance_cents):''}</p><div class="trip-total"><span>${m.length} meal records</span><strong>${money(m.reduce((s,e)=>s+e.amount_cents,0))}</strong></div><button class="ghost trip-detail" data-id="${t.id}">View trip & meals →</button><button class="secondary overnight-compare" data-id="${t.id}">Spending & allowances</button>${editor()?`<button class="secondary add-meal" data-id="${t.id}">+ Add meal</button>${actionMenu('Trip actions for '+t.location,`<button class="edit-trip" data-id="${t.id}">Edit trip</button><button class="trip-detail" data-id="${t.id}">View trip & meals</button>`)}`:''}</section>`}).join('')}</div><section class="panel"><div class="panel-header"><h2>Matching meals</h2><span>${shownMeals.length} records</span></div>${shownMeals.length?table(shownMeals):'<p class="empty">No meals match these filters.</p>'}</section>${!shownTrips.length?'<div class="panel empty"><h2>No matching trips</h2><p>Adjust your search or filters, or add an overnight trip.</p></div>':''}`;tableEvents();document.querySelectorAll('.overnight-compare').forEach(b=>b.onclick=()=>Overnights.view(Number(b.dataset.id)).catch(e=>toast(e.message)));document.querySelectorAll('.add-meal').forEach(b=>b.onclick=()=>expenseModal(null,T.find(t=>t.id===Number(b.dataset.id))));document.querySelectorAll('.edit-trip').forEach(b=>b.onclick=()=>editTrip(T.find(t=>t.id===Number(b.dataset.id))));if($('#add-trip'))$('#add-trip').onclick=()=>{modal('Add overnight trip',`<form id="trip-form"><div class="grid2">${field('Location','location','text','','required')}${select('Workspace','scope',Features.scopes('',false),Features.defaultScope())}${field('Departure date','start','date',today(),'required')}${field('Return date','end','date','','required')}${allowanceField()}<div class="span2">${field('Work / business purpose','purpose','text','','required')}</div></div><div class="modal-footer"><button type="submit">Save trip</button></div></form>`);formHandler('#trip-form',async d=>{await api('trips',{...d,allowance:d.allowance||0});$('#modal').close();await refresh();render();toast('Overnight trip added')})};document.querySelectorAll('.trip-detail').forEach(b=>b.onclick=()=>{const t=T.find(t=>t.id===Number(b.dataset.id)),m=E.filter(e=>e.trip_id===t.id);modal(esc(t.location),`<p class="muted">${esc(dateAU(t.start))} → ${esc(dateAU(t.end))} · ${scopeName(t.scope)}</p><p>${esc(t.purpose)}</p><hr class="subtle-line"><div class="table-wrap"><table><thead><tr><th>Date</th><th>Meal / category</th><th>Merchant</th><th>Amount</th><th></th></tr></thead><tbody>${m.map(e=>`<tr><td>${esc(dateAU(e.date))}</td><td>${esc(categoryLabel(e.meal||e.category))}</td><td>${esc(e.merchant)}</td><td>${money(e.amount_cents)}</td><td><button class="ghost trip-expense" data-id="${e.id}">${editor()?'Edit':'View'}</button></td></tr>`).join('')}</tbody></table></div>${!m.length?'<p class="empty">No expenses linked yet. Use Add meal on this trip to record one.</p>':''}${t.allowance_cents?`<p class="footnote">Allowance recorded for reference: ${money(t.allowance_cents)}.</p>`:''}`);document.querySelectorAll('.trip-expense').forEach(b=>b.onclick=()=>expenseModal(E.find(e=>e.id===Number(b.dataset.id))))})}
function bankPage(){$('#content').innerHTML=heading('Bank accounts','Review bank feeds and statement imports, then decide where each expense belongs.',bookkeeper()?'<button class="secondary" id="new-account">+ Add account</button><button id="import">Import CSV</button>':'')+`${Workflows.bankLinks()}<section id="bank-account-overview" class="bank-page-view"><div class="notice">Connect PocketSmith or import a CSV statement. CSV debit imports start as Personal / To review; credits and zero amounts are skipped.</div><div class="grid3 bank-account-cards">${A.map(a=>`<section class="card"><div class="bank-badge ${a.bank}">${a.bank==='CommBank'?'◆':a.bank==='Macquarie'?'M':'AE'}</div><h2>${esc(a.name)}</h2><p class="muted">${esc(a.bank)}</p><hr class="subtle-line"><strong>${E.filter(e=>e.account_id===a.id).length} expense records</strong><p class="footnote">Expense Pilot account label</p></section>`).join('')}</div>${!A.length?'<div class="panel empty"><h2>Connect your records</h2><p>Add a CommBank, Macquarie or American Express account label to start importing.</p></div>':''}${owner()?'<div class="actions"><button type="button" class="secondary" id="bank-connection-settings">Connection settings</button></div>':''}</section><div id="bank-feeds" class="bank-page-view"></div>`;bind('#new-account',()=>{modal('Add bank account',`<form id="account-form">${select('Bank','bank',['CommBank','Macquarie','American Express','Other'].map(v=>[v,v]))}${field('Account label','name','text','','required placeholder="e.g. CommBank everyday · 1234"')}<p class="footnote">A label is enough. Do not enter online banking credentials.</p><div class="modal-footer"><button type="submit">Add account</button></div></form>`);formHandler('#account-form',async d=>{await api('accounts',d);$('#modal').close();await refresh();render()})});bind('#import',importModal);const accounts=page==='bank_accounts';$('#bank-account-overview').hidden=!accounts;$('#bank-feeds').hidden=accounts;bind('#bank-connection-settings',()=>BankFeeds.settings().catch(e=>toast(e.message)));if(!accounts)BankFeeds.mount().catch(e=>toast(e.message))}
function importModal(){if(!A.length)return toast('Add a bank account first.');modal('Import bank transactions',`<form id="import-form"><div class="notice">Choose an export with a header row. Review the preview, date format and debit sign before importing. All debit rows enter the review queue, including transfers.</div>${select('Bank account','account_id',A.map(a=>[a.id,`${a.bank} · ${a.name}`]))}<div class="field"><label for="csv">Bank statement CSV</label><input type="file" id="csv" accept=".csv,text/csv" required></div><div id="mapping"></div><div class="modal-footer"><button type="submit" id="import-submit" disabled>Import expenses</button></div></form>`);$('#csv').onchange=async()=>{const fd=new FormData();fd.append('file',$('#csv').files[0]);try{const p=await api('import/preview',fd);const options=p.headers.map((h,i)=>[i,h||`Column ${i+1}`]);$('#mapping').innerHTML=`<p class="status-line">${p.count} rows · first ${p.sample.length} shown</p><div class="table-wrap"><table><thead><tr>${p.headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${p.sample.map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><hr class="subtle-line"><div class="grid2">${select('Date column','date',options,Math.max(0,p.headers.findIndex(h=>/date/i.test(h))))}${select('Description column','merchant',options,Math.max(0,p.headers.findIndex(h=>/description|merchant|details/i.test(h))))}${select('Amount / debit column','amount',options,Math.max(0,p.headers.findIndex(h=>/amount|debit/i.test(h))))}${select('Debits appear as','sign',[['negative','Negative amounts (e.g. −25.00)'],['positive','Positive amounts (e.g. 25.00)']])}${select('Date format','date_format',[['%d/%m/%Y','DD/MM/YYYY'],['%d/%m/%y','DD/MM/YY'],['%Y-%m-%d','YYYY-MM-DD'],['%m/%d/%Y','MM/DD/YYYY']])}</div><p class="footnote">Separate debit/credit columns? Select the debit column and positive amounts. Exact repeat rows are detected using account, date, description, amount and occurrence count. Review overlapping exports with repeated identical purchases.</p>`;$('#import-submit').disabled=false}catch(e){toast(e.message);$('#import-submit').disabled=true}};formHandler('#import-form',async d=>{const fd=new FormData();fd.append('file',$('#csv').files[0]);fd.append('mapping',JSON.stringify(d));const r=await api('import',fd);$('#modal').close();await refresh();render();toast(`${r.added} imported · ${r.duplicates} duplicates · ${r.credits_skipped} credits/zero rows skipped`)})}
function reportPage(){$('#content').innerHTML=heading('Ready for a better tax time.','Export the detail, with employment and business kept clearly labelled.')+`<section class="card report-preview"><h2>Expense report</h2><p class="muted">AUD · Australian financial year</p><hr class="subtle-line"><form id="report-form">${select('Financial year','report_fy',fyOptions())}<div class="grid2">${field('From (optional)','start','date')}${field('To (optional)','end','date')}</div><div class="notice">All records are included, including personal and unreviewed entries. Scope, use percentage, reimbursement and review status are included for assessment.</div><button type="submit">↓ Download CSV report</button></form><p class="footnote">Receipts can be downloaded from each expense. Allocated amounts are not a determination of deductibility. This version does not lodge returns or calculate GST/BAS.</p></section>`;$('#report_fy').onchange=ev=>{const v=ev.target.value;const [s,e]=v==='all'?['','']:fyBounds(v);$('#start').value=dateAU(s);$('#end').value=dateAU(e)};$('#report-form').onsubmit=ev=>{ev.preventDefault();const d=formData(ev.target);if(d.start&&d.end&&d.end<d.start)return toast('End date must follow start date.');location.href='/api/export?'+new URLSearchParams({start:d.start,end:d.end})}}
function teamPage(){
if(!owner()){navigate('settings');return;}
$('#content').innerHTML=heading('Tax agent access','Invite your tax agent and manage their access.','<button class="secondary" id="back-to-settings">Back to Settings</button><button id="add-user">+ Invite tax agent</button>')+`<div class="notice">Tax agents see only the financial years and evidence you share. Read & write permits tax classification and annual equipment adjustments. Existing accounts need sharing configured before records are visible.</div><div class="panel table-wrap"><table><thead><tr><th>Person</th><th>Role</th><th>Permission</th><th>Security</th><th>Access</th></tr></thead><tbody>${U.map(u=>`<tr><td><strong>${esc(u.name)}</strong><br><small>${esc(u.email)}</small></td><td>${esc(u.role.replace('_',' '))}</td><td>${u.role==='tax_agent'?`<select class="agent-permission" data-id="${u.id}" aria-label="Permission for ${esc(u.name)}"><option value="read_only" ${u.permission==='read_only'?'selected':''}>Read only</option><option value="read_write" ${u.permission==='read_write'?'selected':''}>Read & write</option></select>`:u.role==='owner'?'Full control':'Own business records'}</td><td>${u.totp_enabled?'2FA enabled':'2FA not enabled'}${u.must_change_password?`<br><small>${u.invite_expires*1000<Date.now()?'Invitation expired':({'sent':'Invited · password change pending','failed':'Invitation email failed','unknown':'Email delivery unconfirmed','sending':'Invitation sending'}[u.invite_status]||'Password change pending')}</small>${u.active?`<br><button class="ghost resend-invite" data-id="${u.id}">Resend invitation</button>`:''}`:''}</td><td>${u.role!=='owner'?`<button class="secondary access" data-id="${u.id}" data-active="${u.active}">${u.active?'Disable':'Enable'}</button><button class="secondary agent-sharing" data-id="${u.id}">Sharing</button><button class="danger agent-remove" data-id="${u.id}">Remove account</button>`:'Active'}</td></tr>`).join('')}</tbody></table></div>`;
bind('#back-to-settings',()=>{navigate('settings');});
document.querySelectorAll('.agent-sharing').forEach(b=>b.onclick=()=>TaxAgent.sharing(U.find(u=>u.id===Number(b.dataset.id))).catch(e=>toast(e.message)));
document.querySelectorAll('.agent-remove').forEach(b=>b.onclick=()=>TaxAgent.remove(U.find(u=>u.id===Number(b.dataset.id))));
bind('#add-user',()=>{modal('Invite your tax agent',`<form id="user-form">${field('Name','name','text','','required')}${field('Email (login name)','email','email','','required')}<input type="hidden" name="role" value="tax_agent">${select('Tax-agent permission','permission',[['read_only','Read only'],['read_write','Read & write']])}<p class="notice">An invitation email will include a generated temporary password, valid for 48 hours. The person must change it before accessing records.</p><p class="footnote">Set your login address and email delivery in Settings first.</p><div class="modal-footer"><button type="submit">Create account & send invitation</button></div></form>`);formHandler('#user-form',async d=>{const result=await api('users',d);$('#modal').close();await refresh();render();if(result.invitation_status==='sent')toast('Invitation sent.');else modal('Invitation needs attention',`<p>${esc(result.message)}</p><p>The person is listed in Tax agent access. Use Resend invitation after checking email delivery.</p>`);});});
document.querySelectorAll('.agent-permission').forEach(el=>el.onchange=async()=>{el.disabled=true;try{await api('users/'+el.dataset.id+'/permission',{permission:el.value},'PUT');toast('Permission updated.');}catch(e){toast(e.message);}finally{await refresh();render();}});
document.querySelectorAll('.access').forEach(b=>b.onclick=async()=>{try{await api('users/'+b.dataset.id+'/access',{active:b.dataset.active!=='1'});await refresh();render();}catch(e){toast(e.message);}});
document.querySelectorAll('.resend-invite').forEach(b=>b.onclick=async()=>{if(!confirm('Email a new temporary password? The previous invitation password will stop working.'))return;b.disabled=true;try{const result=await api('users/'+b.dataset.id+'/invite',{});await refresh();render();toast(result.message);}catch(e){toast(e.message);b.disabled=false;}});
}
function accountSettingsPage(){
 const groups=[
  ['Account',[
   ['security','Access & security','Protect your login'+(owner()?' and manage tax agent access.':'.'),'shield'],
  ]],
  ['Workspace',[
   ['workspace','Workspace features','Choose the tools available in your workspace.','filter'],
   ...(owner()?[['notifications','Overview & alerts','Choose which updates you receive.','bell']]:[]),
  ]],
  ['This browser',[
   ['appearance','Appearance','Choose light, dark or your device preference.','screen'],
  ]],
  ['Server administration',[
   ['receipts','Receipts & AI','Set up receipt entry, categories and overnight sorting.','sparkle'],
   ...(owner()?[
    ['business','Business & invoices','Manage business details, invoice defaults and design.','file'],
    ['email','Email delivery','Manage delivery, signatures, client wording and reminders.','mail'],
    ['connections','Bank feeds','Connect external accounts and review imported transactions.','bank'],
   ]:[]),
   ['data','Backups & data','Export records, manage backups and control workspace data.','server'],
  ]],
 ];
 const topics=groups.flatMap(([,items])=>items);
 $('#content').innerHTML=heading('Settings','Manage your account, workspace and server.')+
  `<div class="settings-layout"><nav class="settings-nav panel" aria-label="Settings sections">${groups.map(([label,items])=>`
   <div class="settings-nav-group"><p class="nav-group-label">${label}</p>
    ${items.map(([id,title,,glyph])=>`<button type="button" class="secondary" data-settings-jump="${id}">${WorkspaceUI.icon(glyph)} ${title}</button>`).join('')}
    ${owner()&&label==='Server administration'?'<button type="button" class="secondary" id="settings-tax-agent">Tax agent access</button>':''}
   </div>`).join('')}</nav><div class="settings-content">
   ${topics.map(([id,title,description])=>`<section class="settings-group" id="settings-${id}" aria-labelledby="settings-title-${id}"><header><h2 id="settings-title-${id}" tabindex="-1">${title}</h2><p class="muted">${description}</p></header><div class="settings-grid" id="settings-${id}-cards"></div></section>`).join('')}
  </div></div><footer class="settings-footer"><span>Expense Pilot ${esc(S.version)} · ${esc(S.user.email)}</span><button class="secondary" id="signout">Sign out</button></footer>`;
 RefinedSettings.bind();
 bind('#settings-tax-agent',()=>navigate('team'));
 const displayControl=themeControl('settings-theme-choice');
 $('#settings-appearance-cards').innerHTML=`<section class="card appearance-settings"><h3>Display</h3>${displayControl?`<p class="muted">Saved in this browser.</p>${displayControl}`:'<p class="muted">Display controls are temporarily unavailable. Reload to try again.</p>'}</section>`;
 $('#settings-security-cards').innerHTML=`<section class="card"><h3>Change password</h3><p class="muted">Update the password for your own login.</p><form id="password-form">${field('Current password','current','password','','required autocomplete="current-password"')}${field('New password','password','password','','required minlength="12" autocomplete="new-password"')}${S.user.totp_enabled?field('Authenticator or recovery code','code','text','','required autocomplete="one-time-code" maxlength="40"'):''}<button type="submit">Update password</button></form></section><section class="card" id="security-settings"><h3>Two-factor authentication</h3><p>Loading security settings…</p></section>${owner()?'<section class="card" id="invitation-settings"><h3>Account invitations</h3><p>Loading invitation settings…</p></section><section class="card"><h3>Tax agent access & activity</h3><p class="muted">Invite your tax agent, manage permissions and review account activity.</p><div class="settings-options"><button class="secondary" id="manage-tax-agents">Manage tax agent access →</button><button class="secondary" id="audit">View activity log</button></div></section>':''}`;
 formHandler('#password-form',async d=>{await api('password',d);toast('Password changed. Sign in again.');await boot()});bind('#signout',async()=>{await api('logout',{});await boot()});bind('#audit',async()=>{try{const r=await api('audit');modal('Recent activity',`<div class="table-wrap"><table><thead><tr><th>UTC time</th><th>Person</th><th>Action</th></tr></thead><tbody>${r.map(a=>`<tr><td>${esc(dateAU(a.at))}</td><td>${esc(a.name||'System')}</td><td>${esc(a.action)}</td></tr>`).join('')}</tbody></table></div>`)}catch(e){toast(e.message)}})}
function editTrip(t){modal('Edit overnight trip',`<form id="edit-trip-form"><div class="grid2">${field('Location','location','text',t.location,'required')}${select('Workspace','scope',Features.scopes(t.scope,false),t.scope)}${field('Departure','start','date',t.start,'required')}${field('Return','end','date',t.end,'required')}${allowanceField(t.allowance_cents)}<div class="span2">${field('Purpose','purpose','text',t.purpose,'required')}</div></div><div class="modal-footer"><button type="button" class="danger" id="delete-trip">Delete trip</button><button type="submit">Save changes</button></div></form>`);formHandler('#edit-trip-form',async d=>{await api('trips/'+t.id,{...d,allowance:d.allowance||0},'PUT');$('#modal').close();await refresh();render();toast('Trip updated')});bind('#delete-trip',async()=>{if(!confirm('Delete this trip? Linked expenses must be removed first.'))return;try{await api('trips/'+t.id,{},'DELETE');$('#modal').close();await refresh();render()}catch(e){toast(e.message)}})}


function settingsPage(){
 accountSettingsPage();$('#content').classList.add('settings-page');
 Security.settings().catch(e=>toast(e.message));Tracking.settings();Features.settings();PublicRelease.settings().catch(e=>toast(e.message));
 if(owner()){RefinedSettings.notifications().catch(e=>toast(e.message));bind('#manage-tax-agents',()=>navigate('team'));Billing.settings();BankFeeds.settingsCard();}
}
window.addEventListener('DOMContentLoaded',boot);

function createInlineCategory(target){
 let dialog=$('#category-dialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='category-dialog';document.body.append(dialog);}
 dialog.innerHTML=`<div class="modal-title"><h2>Create expense category</h2><button type="button" class="ghost" id="close-category" aria-label="Close category menu">✕</button></div><form id="inline-category-form">${field('Category name','new_category_name','text','','required maxlength="80"')}<button type="submit">Create category</button></form>`;dialog.showModal();bind('#close-category',()=>dialog.close());formHandler('#inline-category-form',async d=>{S.categories=await api('categories',{name:d.new_category_name});const select=$(target);select.innerHTML=S.categories.filter(c=>c!=='Meals').map(c=>`<option value="${esc(c)}">${esc(categoryLabel(c))}</option>`).join('');select.value=d.new_category_name.trim();dialog.close();toast('Category created.');});
}
