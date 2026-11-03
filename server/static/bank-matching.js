'use strict';
const BankMatching=(()=>{
 function bindReceipt(rid,gather,initial={}){
  const host=$('#receipt-bank-match');let timer,serial=0,selection=String(initial.bank_choice||'auto'),version=initial.bank_version;
  host.innerHTML='<div class="field"><label for="receipt-bank-choice">Bank account / transaction</label><select id="receipt-bank-choice"><option value="auto">Find a bank match automatically</option><option value="cash">Cash / other — do not match</option></select></div><p class="footnote" id="receipt-bank-status" role="status"></p><button type="button" class="ghost" id="receipt-bank-refresh">Refresh bank matches</button>';
  async function update(){
   const count=++serial;
   try{
    const v=gather();$('#receipt-bank-status').textContent='Checking synced bank transactions…';
    const result=await api('receipts/'+rid+'/bank-matches',v);if(count!==serial||!host.isConnected)return;
    const options=result.candidates.filter(t=>!t.expense_receipt_id&&!t.existing_conflict);
    $('#receipt-bank-choice').innerHTML=`<option value="auto">${result.status==='matched'?'Use suggested bank match':result.status==='none'?'Automatic · no match, use Cash / other':'Find a bank match automatically'}</option><option value="cash">Cash / other — do not match</option>`+options.map(t=>`<option value="${t.id}">${esc(t.account_name+' · '+dateAU(t.date)+' · '+t.payee+(t.expense_id?' · attach to existing expense':''))}</option>`).join('');
    if(selection!=='cash'&&selection!=='auto'&&!options.some(t=>String(t.id)===selection)){selection='auto';version=null;}
    $('#receipt-bank-choice').value=selection;
    const match=options.find(t=>String(t.id)===selection);version=match?.version;
    const clear=result.candidates[0];
    $('#receipt-bank-status').textContent=result.status==='matched'?`${clear.account_name} · ${dateAU(clear.date)} · ${clear.payee}. ${clear.expense_id?'This document will attach to the existing expense; its financial details are retained.':'This transaction will be linked when saved.'}`:result.status==='review'?'Several matches or an already-filed transaction need review. Choose a transaction or Cash / other before saving.':result.status==='incomplete'?'Enter merchant, date and AUD amount to find a match.':'No clear match in the synced bank feed. The expense will use Cash / other. Sync your bank feed first if transactions are missing.';
    $('#receipt-bank-choice').onchange=()=>{selection=$('#receipt-bank-choice').value;version=options.find(t=>String(t.id)===selection)?.version;};
   }catch(e){if(host.isConnected)$('#receipt-bank-status').textContent=e.message;}
  }
  bind('#receipt-bank-refresh',update);
  for(const id of ['merchant','date','amount'])$('#receipt_'+id).addEventListener('change',()=>{clearTimeout(timer);timer=setTimeout(update,250);});
  update();
  return ()=>({bank_choice:selection,...(version!=null?{bank_version:version}:{})});
 }
 async function previous(account=''){
  const result=await api('bank-matches/previous'+(account?'?account_id='+encodeURIComponent(account):''));
  modal('Match previous expenses',`<form id="bank-match-previous"><p>Review clear matches between existing expenses and posted AUD purchases already synced from PocketSmith. Expense amounts and allocations are retained.</p>${select('Bank account','previous-bank-account',[['','All mapped bank accounts'],...A.map(a=>[a.id,a.name])],account)}<p>${result.checked} unmatched expenses checked · ${result.matches.length} clear matches · ${result.ambiguous} need manual review · ${result.unmatched} without a clear match.</p>${result.matches.length?`<div class="table-wrap"><table><thead><tr><th>Match</th><th>Expense</th><th>Bank transaction</th><th>Amount</th></tr></thead><tbody>${result.matches.map((m,i)=>`<tr><td><input type="checkbox" data-match="${i}" checked aria-label="Match ${esc(m.merchant)} on ${esc(dateAU(m.date))}"></td><td>${esc(m.merchant)}<br>${esc(dateAU(m.date))}</td><td>${esc(m.account_name)} · ${esc(m.payee)}<br>${esc(dateAU(m.bank_date))}</td><td>${money(m.amount_cents)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="notice">No clear matches to apply. Sync your feed and check account mappings. Ambiguous matches can be reviewed individually in the bank feed.</p>'}<p class="footnote">Matching requires the same amount, a recognisable merchant and dates within three days. Explicit Cash / other choices, ignored transactions, transfers, credits and pending transactions are excluded.</p><div class="modal-footer"><button type="submit" ${result.matches.length?'':'disabled'}>Apply selected matches</button></div></form>`);
  $('#previous-bank-account').onchange=e=>previous(e.target.value).catch(err=>toast(err.message));
  formHandler('#bank-match-previous',async()=>{const matches=[...document.querySelectorAll('[data-match]:checked')].map(x=>result.matches[Number(x.dataset.match)]);if(!matches.length)throw Error('Select at least one match.');const r=await api('bank-matches/previous',{account_id:account||null,matches});$('#modal').close();await refresh();await BankFeeds.mount();toast(`${r.matched} previous expenses matched.`);});
 }
 return {bindReceipt,previous};
})();
