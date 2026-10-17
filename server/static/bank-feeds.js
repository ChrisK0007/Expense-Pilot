'use strict';
const BankFeeds=(()=>{
 let filter='review',offset=0;
 const stamp=v=>v?WorkspaceTime.stamp(v):'Not synced yet';
 const amount=t=>new Intl.NumberFormat('en-AU',{style:'currency',currency:t.currency}).format(t.amount_cents/100);
 const busy=async(button,fn)=>{button.disabled=true;try{await fn();}catch(e){toast(e.message);}finally{button.disabled=false;}};
 function settingsCard(){
  $('#settings-connections-cards').insertAdjacentHTML('beforeend','<section class="card"><h3>PocketSmith</h3><p class="muted">Connect your PocketSmith accounts and review bank transactions before adding them to expenses.</p><button class="secondary" id="settings-bank-feeds">Configure PocketSmith →</button></section>');
  bind('#settings-bank-feeds',()=>settings().catch(e=>toast(e.message)));
 }
 async function settings(){
  const c=await api('pocketsmith');
  modal('PocketSmith bank feeds',`<p>Manage your bank connections in PocketSmith. Expense Pilot reads the transactions already available there.</p><p><a href="https://my.pocketsmith.com/" target="_blank" rel="noopener noreferrer">Open PocketSmith</a> → Settings → Security → create a developer key.</p>
   <form id="feed-key-form">${field(c.connected?'Replace developer key (optional)':'Developer key','feed-key','password','','autocomplete="off" spellcheck="false" maxlength="512" '+(c.connected?'':'required'))}<p class="footnote">The key is encrypted on this server and is never shown again. This connection only reads PocketSmith.</p><button type="submit">${c.connected?'Refresh accounts / update key':'Connect PocketSmith'}</button></form>
   ${c.connected?`<hr class="subtle-line"><p><strong>Connected to ${esc(c.display_name)}</strong></p><form id="feed-config-form">${field('Sync transactions from','feed-start','date',c.start_date,'required')}<p>Select accounts and choose their Expense Pilot account labels. Use the same label as previous CSV imports to find matching expenses.</p><div class="feed-account-list">${c.accounts.map(a=>`<section class="feed-account"><label class="check"><input type="checkbox" data-feed-account="${a.id}" ${a.enabled&&a.available?'checked':''} ${a.available?'':'disabled'}>${esc(a.name)} · ${esc(a.currency)}</label><p class="footnote">${esc(a.institution)}${a.available?'':' · Unavailable in PocketSmith'}</p>${a.local_account_id?`<p class="footnote">Expense Pilot: ${esc(A.find(x=>x.id===a.local_account_id)?.name||a.name)}</p>`:select('Expense Pilot label for '+esc(a.name),'feed-map-'+a.id,[['','Create a new account label'],...A.map(x=>[x.id,x.name])])}</section>`).join('')||'<p>No transaction accounts are available in PocketSmith yet.</p>'}</div><label class="check"><input type="checkbox" id="feed-auto" ${c.auto_sync?'checked':''}>Sync automatically every hour while the container is running</label><p class="footnote">Automatic sync fills the bank review queue. You choose which transactions become expenses.</p><div class="modal-footer"><button type="button" class="danger" id="feed-disconnect">Disconnect</button><button type="submit">Save bank feed settings</button></div></form>`:''}
   <p class="footnote">Last successful sync: ${esc(stamp(c.last_sync))}</p>${c.last_error?`<p class="error">${esc(c.last_error)}</p>`:''}`);
  formHandler('#feed-key-form',async()=>{const key=$('#feed-key').value.trim();try{await api('pocketsmith',{key});}finally{$('#feed-key').value='';}await settings();toast('PocketSmith connected. Select accounts and save settings.');});
  if(!c.connected)return;
  formHandler('#feed-config-form',async()=>{
   const accounts=[...document.querySelectorAll('[data-feed-account]:checked')].map(el=>{const id=Number(el.dataset.feedAccount),a=c.accounts.find(x=>x.id===id);return {id,local_account_id:a.local_account_id||Number($('#feed-map-'+id)?.value)||null};});
   await api('pocketsmith',{version:c.version,start_date:dateValue($('#feed-start')),auto_sync:$('#feed-auto').checked,accounts},'PUT');
   $('#modal').close();await refresh();render();toast('Bank feed settings saved. Use Sync now on Bank accounts.');
  });
  bind('#feed-disconnect',ev=>busy(ev.currentTarget,async()=>{if(!confirm('Disconnect PocketSmith and remove the saved key? Imported transactions and expenses will be kept.'))return;await api('pocketsmith',{version:c.version},'DELETE');$('#modal').close();await refresh();render();toast('PocketSmith disconnected.');}));
 }
 async function mount(){
  const host=$('#bank-feeds');if(!host)return;
  const [c,result]=await Promise.all([owner()?api('pocketsmith'):Promise.resolve(null),api(`bank-transactions?state=${filter}&offset=${offset}`)]);
  if(!host.isConnected)return;
  host.innerHTML=`<section class="panel feed-panel"><div class="feed-heading"><div><h2>PocketSmith bank feed</h2><p class="muted">${c?c.connected?`Connected to ${esc(c.display_name)} · ${c.auto_sync?'Hourly sync on':'Manual sync'}`:'Connect PocketSmith to bring bank transactions into your review queue.':'Review synced bank transactions and match them to expenses.'}</p></div>${owner()?`<div class="feed-actions"><button class="secondary" id="feed-settings">${c.connected?'Connection settings':'Connect PocketSmith'}</button>${c.connected?`<button id="feed-sync" ${c.syncing||c.retry_after>Date.now()/1000?'disabled':''}>${c.syncing?'Syncing…':'Sync now'}</button>`:''}</div>`:''}</div>
   ${c?.connected?`<p class="footnote">Last successful sync: ${esc(stamp(c.last_sync))}${c.auto_sync&&c.next_sync?` · Next check: ${esc(stamp(c.next_sync*1000))}`:''}</p>`:''}${c?.last_error?`<p class="error">${esc(c.last_error)}${c.retry_after>Date.now()/1000?` Retry after ${esc(stamp(c.retry_after*1000))}.`:''}</p>`:''}
   <div class="feed-actions">${select('Bank transaction filter','feed-filter',[['review','To review'],['linked','Linked expenses'],['ignored','Ignored'],['pending','Pending'],['other','Transfers / not returned'],['all','All bank transactions']],filter)}<button class="secondary" id="feed-refresh">Refresh view</button><p class="footnote">${result.total} transaction${result.total===1?'':'s'}</p></div>
   <p class="footnote">Purchases and refunds need your review. Pending transactions cannot be added. Transfers and other credits can be ignored. PocketSmith categories do not set your expense allocation.</p>
   ${result.items.length?`<div class="table-wrap"><table class="feed-table"><thead><tr><th>Date</th><th>Transaction</th><th>Account</th><th>Bank amount</th><th>Status</th><th></th></tr></thead><tbody>${result.items.map(t=>`<tr><td>${esc(dateAU(t.date))}</td><td><strong>${esc(t.payee)}</strong>${t.source_category?`<br><small>${esc(t.source_category)}</small>`:''}</td><td>${esc(t.account_name)}</td><td>${esc(amount(t))}</td><td>${esc(t.missing?'Not returned':t.source_status==='pending'?'Pending':t.is_transfer?'Transfer':t.state==='linked'?'Linked expense':t.state==='ignored'?'Ignored':t.amount_cents>0?'Credit':'To review')}${t.changed?'<br><strong class="error">Source changed</strong>':''}</td><td><button class="secondary" data-bank-review="${t.id}">Review</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty"><p>No transactions in this view.</p></div>'}
   <div class="feed-actions"><button class="secondary" id="feed-prev" ${offset?'':'disabled'}>Previous</button><span>${result.total?`${offset+1}–${Math.min(offset+100,result.total)} of ${result.total}`:'0 transactions'}</span><button class="secondary" id="feed-next" ${offset+100<result.total?'':'disabled'}>Next</button></div></section>`;
  bind('#feed-settings',()=>settings().catch(e=>toast(e.message)));
  bind('#feed-sync',ev=>busy(ev.currentTarget,async()=>{ev.currentTarget.textContent='Syncing…';try{const r=await api('pocketsmith/sync',{});toast(`${r.added} new transactions · ${r.received} checked`);}finally{await mount();}}));
  bind('#feed-refresh',()=>mount().catch(e=>toast(e.message)));
  $('#feed-filter').onchange=()=>{filter=$('#feed-filter').value;offset=0;mount().catch(e=>toast(e.message));};
  bind('#feed-prev',()=>{offset=Math.max(0,offset-100);mount().catch(e=>toast(e.message));});
  bind('#feed-next',()=>{offset+=100;mount().catch(e=>toast(e.message));});
  host.querySelectorAll('[data-bank-review]').forEach(b=>b.onclick=()=>review(Number(b.dataset.bankReview)).catch(e=>toast(e.message)));
 }
 async function review(id){
  const result=await api('bank-transactions/'+id),t=result.transaction,candidates=result.matches;
  const eligible=!t.expense_id&&!t.missing&&t.source_status==='posted'&&!t.is_transfer&&t.amount_cents!==0;
  modal('Review bank transaction',`<h3>${esc(t.payee)}</h3><p>${esc(dateAU(t.date))} · ${esc(t.account_name)} · <strong>${esc(amount(t))}</strong></p><p class="muted">${esc(t.memo)}</p>
   ${t.changed?'<div class="notice">PocketSmith has changed this transaction. Your linked expense has been kept as it was; compare its amount and date before acknowledging the change.</div>':''}
   ${t.missing?'<div class="notice">This transaction was not returned by PocketSmith on the last complete sync. It may have been removed or replaced. Any linked expense is kept.</div>':''}
   ${t.source_status==='pending'?'<div class="notice">Pending transactions may be replaced when posted. Wait for a posted transaction before adding an expense.</div>':''}
   ${t.is_transfer?'<div class="notice">PocketSmith marks this as a transfer. It cannot be added as an expense here.</div>':''}
   ${t.expense_id?`<button class="secondary" id="feed-open-linked">Open linked expense →</button>${bookkeeper()?'<button class="ghost" id="feed-unlink">Unlink expense</button>':''}`:''}
   ${eligible&&!t.local_account_id?'<p class="error">Map this account in connection settings before continuing.</p>':''}
   ${eligible?`<h3>Possible existing expenses</h3>${candidates.length?candidates.map(e=>`<section class="receipt-match"><p>${esc(e.merchant)} · ${esc(dateAU(e.date))} · ${money(e.amount_cents)}</p><button class="secondary" data-feed-view="${e.id}">View expense →</button>${bookkeeper()?`<button data-feed-link="${e.id}">Match this expense</button>`:''}</section>`).join(''):`<p class="muted">${t.currency==='AUD'?'No unlinked expenses with the same amount and account within three days.':'Automatic matching is available for AUD accounts. Enter the converted AUD amount when adding an expense.'}</p>`}`:''}
   ${eligible&&t.amount_cents>0?'<p class="notice">This is money coming in. Only add it if it refunds an expense. Salary, invoice payments and transfers should not become negative expenses.</p>':''}
   <div class="modal-footer">${bookkeeper()?`${t.changed?'<button class="secondary" id="feed-ack">Acknowledge change</button>':''}${!t.expense_id?`<button class="secondary" id="feed-ignore">${t.state==='ignored'?'Restore to review':'Ignore transaction'}</button>`:''}${eligible&&t.local_account_id?`<button id="feed-create">${t.amount_cents>0?'Record expense refund':'Create expense'}</button>`:''}`:''}</div>`);
  const act=async(action,extra={})=>{await api('bank-transactions/'+id,{version:t.version,action,...extra});$('#modal').close();await refresh();await mount();toast('Bank transaction updated.');};
  const open=eid=>{const e=E.find(x=>x.id===eid)||candidates.find(x=>x.id===eid);if(e)expenseModal(e);else toast('Expense not found. Refresh the page.');};
  bind('#feed-open-linked',()=>open(t.expense_id));
  bind('#feed-unlink',ev=>busy(ev.currentTarget,()=>act('unlink')));
  bind('#feed-ack',ev=>busy(ev.currentTarget,()=>act('acknowledge')));
  bind('#feed-ignore',ev=>busy(ev.currentTarget,()=>act(t.state==='ignored'?'restore':'ignore')));
  document.querySelectorAll('[data-feed-view]').forEach(b=>b.onclick=()=>open(Number(b.dataset.feedView)));
  document.querySelectorAll('[data-feed-link]').forEach(b=>b.onclick=()=>busy(b,()=>act('link',{expense_id:Number(b.dataset.feedLink)})));
  bind('#feed-create',()=>{
   if(candidates.length&&!confirm('Possible existing expenses are listed above. Create a separate new expense anyway?'))return;
   if(t.amount_cents>0&&!confirm('Confirm this credit is a refund of an expense, rather than income or a transfer.'))return;
   expenseModal(null,null,{merchant:t.payee,date:t.date,amount_cents:t.currency==='AUD'?-t.amount_cents:null,scope:'personal',percent:0,work_percent:0,business_percent:0,category:'Uncategorised',status:'review',account_id:t.local_account_id,
    notes:`PocketSmith: ${t.payee} · ${amount(t)}\n${t.memo}`.trim(),bank_transaction_id:t.id,bank_transaction_version:t.version,bank_confirm_new:!!candidates.length,bank_confirm_refund:t.amount_cents>0});
   $('#expense-form').insertAdjacentHTML('afterbegin',`<div class="notice">${t.currency==='AUD'?'This expense will be linked to the bank transaction when saved. Keep its bank amount and account.':'Enter the converted AUD amount. The original bank amount is recorded in Notes.'}</div>`);
  });
 }
 return {mount,settings,settingsCard};
})();
