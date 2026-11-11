'use strict';
const Receipts=(()=>{
let items=[],groups=[],busy=false,batch={running:false,done:0,total:0,failed:[],cancel:false};
let queue='ready',query='',reviewRevision=0;
const scanning=new Set(),accept='image/jpeg,image/png,image/webp,application/pdf';
const pending=()=>items.filter(r=>!r.expense_id&&!r.income_id);
const isIncome=kind=>['payslip','income_statement'].includes(kind);
const presentNumber=value=>value!=null&&String(value).trim()!==''&&Number.isFinite(Number(value));

async function load(){
 const user=S.user?.id;
 const [documents,proposals]=await Promise.all([api('receipts?unfiled=1'),api('receipt-trip-proposals')]);
 if(S.user?.id!==user)throw Error('Your session changed. Reopen Inbox.');
 items=documents;
 groups=proposals;
}
function values(r){const d={currency:'AUD',percent:100,...r.extraction,...r.draft};if(r.saved_expense)return {...d,...r.saved_expense,amount:r.saved_expense.amount_cents/100,currency:'AUD',currency_status:'saved'};return d;}
function fileLabel(r){return values(r).employer||values(r).merchant||r.filename;}
function ready(r){
 if(scanning.has(r.id)||r.scan_status==='reading')return false;
 const d=values(r),date=/^\d{4}-\d{2}-\d{2}$/.test(d.date||'');
 if(isIncome(d.document_kind)){
  return Boolean(String(d.employer||'').trim()&&date&&Number(d.gross)>0&&presentNumber(d.withheld)&&Number(d.withheld)>=0&&Number(d.withheld)<=Number(d.gross)&&d.amounts_basis!=='unknown');
 }
 return Boolean(String(d.merchant||'').trim()&&date&&presentNumber(d.amount)&&(d.currency==='AUD'||presentNumber(r.draft?.amount)));
}
function readyQueue(){
 return pending().filter(ready);
}
function matchesSearch(r){
 const term=query.trim().toLowerCase();
 return !term||`${fileLabel(r)} ${r.filename}`.toLowerCase().includes(term);
}
function canLeaveReview(){
 const dialog=$('#modal');
 const form=dialog?.matches('.receipt-docked[open]')?dialog.querySelector('form'):null;
 if(form?.dataset.submitting)return false;
 if(form?.dataset.dirty==='true'&&!confirm('Close this review without saving your changes?'))return false;
 reviewRevision++;
 return true;
}
function closeReview(){
 if(!canLeaveReview())return false;
 if($('#modal').matches('.receipt-docked[open]'))$('#modal').close();
 return true;
}
function inboxActions(){
 return editor()?`<button class="secondary" id="reprocess-all">${WorkspaceUI.icon('sparkle')} Reprocess all with AI</button>
  <button id="capture-receipts">${WorkspaceUI.icon('upload')} Capture documents</button>`:'<span class="pill">Read only</span>';
}
async function pageView(){
 reviewRevision++;
 const root=$('#content');
 root.innerHTML=heading('Inbox','Review receipts, bills and payslips before saving them.',inboxActions())+
  `<div id="inbox-batch"></div><div id="inbox-proposals"></div>
   <div class="inbox-workspace">
    <section class="panel inbox-queue" aria-label="Inbox queue">
     <div class="inbox-segments" role="group" aria-label="Inbox status"></div>
     <label class="inbox-search">${WorkspaceUI.icon('search')}<input id="inbox-search" type="search" aria-label="Search Inbox" placeholder="Search Inbox" value="${esc(query)}"></label>
     <div id="inbox-list" class="inbox-list"><p class="muted">Loading documents…</p></div>
     <p class="footnote inbox-note">Saved documents appear with their linked records.</p>
    </section>
    <section class="inbox-detail" id="inbox-review" aria-label="Document review"><div class="panel inbox-placeholder">
     ${WorkspaceUI.icon('inbox')}<h2>Choose a document to review</h2><p class="muted">The original and its details will appear here.</p></div></section>
   </div>
   <button class="ghost inbox-preferences" id="receipt-preferences-button">${WorkspaceUI.icon('settings')} Home base & receipt sorting</button>`;
 const search=$('#inbox-search');
 let loaded=false;
 search.oninput=event=>{query=event.target.value;if(loaded)drawQueue();};
 bind('#reprocess-all',()=>{if(closeReview())reprocessAll();});
 bind('#capture-receipts',()=>{if(closeReview())capture();});
 bind('#receipt-preferences-button',()=>{if(closeReview())Tracking.preferences().catch(e=>toast(e.message));});
 try{
  await load();
  if(!search.isConnected||page!=='receipts')return;
  loaded=true;
  if(!query)queue=readyQueue().length?'ready':'draft';
  draw();
 }catch(e){if(page==='receipts')toast(e.message);}
}
function drawQueue(){
 const list=$('#inbox-list');
 if(!list||page!=='receipts')return;
 const readyRows=readyQueue(),draftRows=pending().filter(r=>!ready(r));
 const tabs=$('.inbox-segments');
 tabs.innerHTML=[['ready','Ready for review',readyRows.length],['draft','Draft',draftRows.length]].map(([key,label,count])=>
  `<button type="button" class="secondary" data-inbox-status="${key}" aria-pressed="${queue===key}">${label} <span>${count}</span></button>`).join('');
 tabs.querySelectorAll('button').forEach(button=>button.onclick=()=>{
  queue=button.dataset.inboxStatus;
  drawQueue();
  tabs.querySelector(`[data-inbox-status="${queue}"]`).focus();
 });
 const shown=(queue==='ready'?readyRows:draftRows).filter(matchesSearch);
 const selected=$('#modal').matches('.receipt-docked[open]')?$('#modal').dataset.receiptId:'';
 list.innerHTML=shown.length?shown.map(r=>{
  const d=values(r),label=fileLabel(r),amount=isIncome(d.document_kind)?d.gross:d.amount;
  const kind={payslip:'Payslip',income_statement:'Income statement',home_office:'Home-office bill'}[d.document_kind]||'Receipt';
  const detail=[kind,d.date?dateAU(d.date):'',presentNumber(amount)?d.currency==='AUD'?money(Math.round(Number(amount)*100)):`${Number(amount).toFixed(2)} ${d.currency}`:''].filter(Boolean).join(' · ');
  return `<article class="receipt-card inbox-row ${selected===r.id?'selected':''}">
   <button type="button" class="ghost review-receipt" data-rid="${esc(r.id)}" aria-label="${editor()?'Review & categorise':'View original'} ${esc(label)}">
    <span class="inbox-doc-icon">${WorkspaceUI.icon(isIncome(d.document_kind)?'money':'file')}</span>
    <span class="inbox-doc-label"><span role="heading" aria-level="3">${esc(label)}</span><small>${esc(detail)}</small>
    ${label!==r.filename?`<small class="inbox-filename">${esc(r.filename)}</small>`:''}
    ${r.scan_error?`<small class="error">${esc(r.scan_error)}</small>`:''}</span>${WorkspaceUI.icon('chev')}
   </button>
   ${actionMenu('Document actions for '+label,`<button class="receipt-menu-preview" data-rid="${esc(r.id)}">View original</button>
   ${editor()&&S.ai_configured?`<button class="reprocess-receipt" data-rid="${esc(r.id)}" ${scanning.has(r.id)||batch.running?'disabled':''}>Reprocess with AI</button>`:''}`)}
  </article>`;
 }).join(''):`<p class="inbox-empty muted">${query.trim()?'No matching documents.':queue==='ready'?'No documents ready for review.':'No drafts.'}</p>`;
 list.querySelectorAll('.review-receipt').forEach(button=>button.onclick=()=>{
  const document=items.find(r=>r.id===button.dataset.rid);
  if(document&&closeReview())review(document);
 });
 list.querySelectorAll('.receipt-menu-preview').forEach(button=>button.onclick=()=>preview(button.dataset.rid));
 list.querySelectorAll('.reprocess-receipt').forEach(button=>button.onclick=()=>{
  const document=items.find(r=>r.id===button.dataset.rid);
  if(document&&closeReview())reprocess(document);
 });
}
function draw(){
 if(page!=='receipts'||!$('#inbox-review'))return;
 const batchArea=$('#inbox-batch');
 batchArea.innerHTML=batch.total?`<section class="notice batch-progress" role="status" aria-live="polite">${batch.running?'AI processing · keep this tab open':batch.cancel?'Processing stopped':'AI processing complete'}: ${batch.done} of ${batch.total} · ${batch.failed.length} failed.${batch.running?'<button class="ghost" id="stop-batch">Stop after current receipt</button>':''}${batch.failed.length?`<details><summary>Receipts to retry</summary>${batch.failed.map(x=>`<p>${esc(x)}</p>`).join('')}</details>`:''}</section>`:'';
 const proposals=$('#inbox-proposals');
 proposals.innerHTML=`${Features.enabled('trips')&&groups.length?`<section class="panel"><div class="panel-header"><h2>Possible overnight trips</h2><span>${groups.length} drafts</span></div><div class="receipt-trip-groups">${groups.map((g,i)=>`<section class="card trip-proposal-card"><h3>${esc(g.location)} · ${g.receipts.length} meal receipt(s)</h3><p>${esc(g.owner)} · ${esc(dateAU(g.start))} → ${esc(dateAU(g.end))}</p><p class="footnote">${g.existing_trip_id?'Suggested match to an existing trip.':'Suggested overnight away from '+esc(g.home_base)+'.'} ${esc(g.location_reason||'')} Confirm dates, purpose and meal amounts before accepting.</p>${editor()?`<button class="secondary review-trip-proposal" data-group="${i}" ${batch.running?'disabled':''}>Review ${g.existing_trip_id?'trip meals':'draft trip'}</button><button class="ghost dismiss-trip-proposal" data-group="${i}">Not an overnight</button>`:'<span class="pill">Awaiting review</span>'}</section>`).join('')}</div></section>`:''}`;
 const reprocessButton=$('#reprocess-all'),captureButton=$('#capture-receipts');
 if(reprocessButton)reprocessButton.disabled=!S.ai_configured||batch.running||busy||scanning.size>0||!pending().length;
 if(captureButton)captureButton.disabled=batch.running;
 bind('#stop-batch',()=>{batch.cancel=true;$('#stop-batch').disabled=true;$('#stop-batch').textContent='Stopping after current receipt…';});
 proposals.querySelectorAll('.review-trip-proposal').forEach(button=>button.onclick=()=>{if(closeReview())reviewTrip(groups[Number(button.dataset.group)]);});
 proposals.querySelectorAll('.dismiss-trip-proposal').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
   for(const r of groups[Number(button.dataset.group)].receipts)await api('receipts/'+r.id+'/draft',{exclude_trip:true},'PUT');
   await load();draw();toast('Suggestion dismissed. Receipts remain as drafts.');
  }catch(e){toast(e.message);button.disabled=false;}
 });
 drawQueue();
}
async function reprocess(r,fromReview=false){
 if(!editor()||!S.ai_configured||scanning.has(r.id)||batch.running)return;
 const form=fromReview?$('#receipt-review'):null;
 if(form?.dataset.dirty==='true'&&!confirm('Reprocess without saving your changes?'))return;
 const controls=form?[...form.querySelectorAll('input,select,textarea,button')].map(el=>[el,el.disabled]):[];
 controls.forEach(([el])=>el.disabled=true);scanning.add(r.id);draw();
 if(form)$('#rescan-receipt').textContent='Reading receipt…';
 const revision=reviewRevision;
 let success=false,failure=null;
 try{await readDocument(r.id);success=true;}
 catch(e){failure=e;}
 finally{scanning.delete(r.id);controls.forEach(([el,disabled])=>el.disabled=disabled);if(form?.isConnected)$('#rescan-receipt').textContent='✧ Reprocess with AI';}
 try{await load();draw();toast(failure?'Reprocessing failed. '+failure.message:'Receipt reprocessed. Check the new suggestions before saving.');if(success&&page==='receipts'&&revision===reviewRevision&&(fromReview?form?.isConnected&&$('#modal').open:!$('#modal').open)){
  const document=items.find(x=>x.id===r.id);
  if(document){queue=ready(document)?'ready':'draft';review(document);}
 }}catch(e){draw();toast(failure?'Reprocessing failed. '+failure.message+' The queue could not refresh: '+e.message:e.message);}
}
function capture(kind='expense'){
 if(typeof kind!=='string')kind='expense';
 if(!editor())return;
 if(busy||batch.running)return toast('Receipt processing is still running.');
 modal('Capture documents',`<div class="capture-drop"><span class="capture-symbol">▤</span><h2>Snap it. Save it. Sort it later.</h2><p>JPEG, PNG, WebP or PDF · up to 12 MB per file</p><label class="upload-label" for="inbox-files">Choose files</label><input class="hidden" id="inbox-files" type="file" multiple accept="${accept}"><label class="upload-label secondary" for="inbox-camera">Take a photo</label><input class="hidden" id="inbox-camera" type="file" accept="image/*" capture="environment"></div>${IncomeDocuments.typeField(kind)}<label class="check"><input id="auto-scan" type="checkbox" ${S.ai_configured||kind==='payslip'?'checked':''}>${S.ai_configured?'Read with AI after upload':'Read supported text payslips after upload'}</label><p class="footnote">${S.ai_configured?'Sends documents to your configured AI provider. Check the figures before saving.':'Supported text payslips are read locally. Other files remain saved for manual entry; configure AI to read photos and other layouts.'} No category, workspace or tax allocation is required now.</p><div id="capture-progress" role="status" aria-live="polite"></div><div class="modal-footer"><button class="secondary" id="capture-done">Done</button></div>`);
 bind('#capture-done',()=>{$('#modal').close();navigate('receipts');});
 $('#document_kind').onchange=()=>{if(!S.ai_configured)$('#auto-scan').checked=$('#document_kind').value==='payslip';};
 const upload=async files=>{
  if(!files.length||busy)return;
  busy=true;const scan=$('#auto-scan').checked,documentKind=$('#document_kind').value;const progress=$('#capture-progress');
  $('#close-modal').disabled=true;$('#capture-done').disabled=true;$('#inbox-files').disabled=true;$('#inbox-camera').disabled=true;
  const preventClose=e=>e.preventDefault();$('#modal').addEventListener('cancel',preventClose);
  for(const f of files){
    const row=document.createElement('div');row.className='upload-progress';row.textContent=f.name+' — uploading…';progress.append(row);
    try{
      if(f.size>12*1024*1024)throw Error('File exceeds 12 MB.');
      const fd=new FormData();fd.append('file',f);fd.append('document_kind',documentKind);const r=await api('receipts',fd);
      row.textContent=f.name+(r.duplicate?' — already saved':' — saved');
      if(scan&&!r.duplicate){row.textContent=f.name+(S.ai_configured?' — saved, AI reading…':' — saved, reading text…');try{await readDocument(r.id);row.textContent=f.name+' — ready to categorise';}catch(e){row.textContent=f.name+' — saved. '+e.message;}}
    }catch(e){row.textContent=f.name+' — '+e.message;row.classList.add('error');}
  }
  busy=false;$('#modal').removeEventListener('cancel',preventClose);$('#close-modal').disabled=false;$('#capture-done').disabled=false;$('#inbox-files').disabled=false;$('#inbox-camera').disabled=false;
  await load();draw();
 };
 $('#inbox-files').onchange=e=>upload([...e.target.files]);$('#inbox-camera').onchange=e=>upload([...e.target.files]);
}
async function reprocessAll(){
 if(batch.running||busy||scanning.size||!editor()||!S.ai_configured)return;
 batch={running:true,done:0,total:pending().length,failed:[],cancel:false};draw();
 try{await load();}catch(e){batch.running=false;draw();return toast(e.message);}
 const queue=pending().map(r=>({id:r.id,name:r.filename}));batch.total=queue.length;if(!queue.length){batch.running=false;draw();return;}draw();
 for(const r of queue){
  if(batch.cancel||!S.user)break;
  try{await readDocument(r.id);}catch(e){batch.failed.push(r.name+' — '+e.message);}
  batch.done++;try{await load();}catch(e){batch.failed.push('Refresh failed: '+e.message);}draw();
 }
 batch.running=false;try{await load();}catch(e){toast(e.message);}draw();toast(`Processed ${batch.done} draft receipt(s). ${batch.failed.length} failed. Manual draft edits were kept.`);
}
function reviewOptions(r){
 const host=$('#inbox-review'),revision=++reviewRevision;
 const ready=readyQueue().filter(matchesSearch);
 const position=ready.findIndex(item=>item.id===r.id);
 const nextId=(ready[position+1]||ready[0])?.id;
 const isCurrent=()=>!host||host.isConnected&&revision===reviewRevision;
 const mount=(title,html)=>{
  const dialog=$('#modal');
  modal(title,html,{host,beforeClose:host?canLeaveReview:null});
  dialog.dataset.receiptId=r.id;
  if(host){
   const form=dialog.querySelector('form');
   const dirty=()=>{form.dataset.dirty='true';};
   form.addEventListener('input',dirty);
   form.addEventListener('change',dirty);
   dialog.onclose=drawQueue;
   drawQueue();
  }
 };
 const run=async action=>{
  const form=$('#modal').querySelector('form');
  if(!isCurrent()||!form||form.dataset.submitting)return;
  form.dataset.submitting='true';
  try{await action();}finally{delete form.dataset.submitting;}
 };
 const afterSave=async(next=false,message='')=>{
  $('#modal').close();
  try{
   await refresh();await load();
   if(!isCurrent()){if(message)toast(message);return;}
   if(next)queue='ready';
   else if(!readyQueue().length)queue='draft';
   draw();
   const candidates=next?readyQueue().filter(item=>item.id!==r.id&&matchesSearch(item)):[];
   const following=candidates.find(item=>item.id===nextId)||candidates[0];
   if(following)review(following);
   if(message)toast(message);
  }catch(e){toast('Saved. Could not refresh Inbox. '+e.message);}
 };
 return {mount,run,afterSave,isCurrent,showNext:!!host&&Boolean(nextId)&&nextId!==r.id};
}
function review(r){
 if(!editor()||r.expense_id||r.income_id)return preview(r.id);
 const options=reviewOptions(r);
 if(isIncome(values(r).document_kind))return IncomeDocuments.review(r,options).catch(e=>toast(e.message));
 const d=values(r),foreign=!!d.currency&&d.currency!=='AUD',suggestion=r.suggestion;d.currency=d.currency||'AUD';d.scope=d.scope||(Features.enabled(r.preferences?.scope==='business'?'business':'employment')?r.preferences?.scope:Features.defaultScope())||Features.defaultScope();
 const home=d.document_kind==='home_office';if(home)Object.assign(d,{work_percent:0,business_percent:0,scope:'personal',category:'Other',vehicle_id:null,trip_id:null,meal:''});
 const tripOptions=T.filter(t=>t.user_id===r.user_id),amount=r.draft?.amount!=null?r.draft.amount:!foreign&&d.amount!=null?d.amount:'';
 options.mount('Review receipt',`<form id="receipt-review"><div class="receipt-review-layout"><div class="receipt-preview"><img src="/api/receipts/${r.id}/preview${r.mime==='application/pdf'?'?page=1':''}" alt="Original receipt"><button type="button" class="secondary" id="preview-original">View full receipt</button><button type="button" class="secondary" data-evidence="${esc(r.id)}">Check extracted evidence</button><p class="footnote">${esc(r.filename)} · ${esc(r.owner)}</p><button type="button" id="rescan-receipt" class="secondary wide" ${S.ai_configured?'':'disabled'}>✧ Reprocess with AI</button><p class="footnote">A fresh AI reading updates suggestions. Saved draft edits and confirmed currency are kept.</p>${r.scan_error?`<p class="error">${esc(r.scan_error)}</p>`:''}</div><div>${IncomeDocuments.typeField(d.document_kind)}${home?`<section class="notice"><strong>Home-office bill evidence</strong><p>This bill supports the fixed-rate claim. No separate bill deduction or percentages are applied.</p>${select('Home-office cost type','home_office_kind',[['electricity','Electricity'],['gas','Gas'],['phone','Phone usage'],['internet','Internet'],['phone_internet','Combined phone / internet'],['stationery','Stationery'],['consumables','Computer consumables']],d.home_office_kind||'electricity')}<label class="check"><input type="checkbox" id="receipt-personally-paid" ${d.personally_paid?'checked':''} required>I personally incurred this cost and it was not reimbursed.</label></section>`:''}<section class="currency-review currency-compact"><div class="currency-controls">${field('Receipt currency','receipt_currency','text',d.currency,'maxlength="3" pattern="[A-Za-z]{3}" required')}<span id="currency-status" class="muted">${foreign?'Foreign receipt':'AUD default'} · <span>edit if needed</span></span></div><p id="foreign-currency-note" class="footnote" ${foreign?'':'hidden'}>Enter the actual AUD amount paid below. Changing this code does not convert money.</p></section>${suggestion?`<div class="notice">Previous reviewed category: ${esc(categoryLabel(suggestion.category))}. <button type="button" class="ghost" id="use-suggestion">Use suggestion</button></div>`:''}
 ${r.matches?.length?`<section class="match-box"><h3>Possible existing expense</h3>${r.matches.map(e=>`<div class="receipt-match"><p><strong>${esc(e.merchant)}</strong> · ${esc(dateAU(e.date))} · ${money(e.amount_cents)}</p><a href="#expense-${e.id}" class="match-view-expense" data-eid="${e.id}">View expense</a> ${e.receipt_id?'<span class="muted">Receipt already attached</span>':`<button class="secondary match-expense" type="button" data-eid="${e.id}">Attach receipt</button>`}</div>`).join('')}</section>`:''}
 <div class="grid2">${field('Merchant / payee','receipt_merchant','text',d.merchant||'','required maxlength="200"')}${field('Receipt date','receipt_date','date',d.date||'','required')}${field('Amount paid (AUD)','receipt_amount','number',amount,'required step="0.01"')}${select('Category','receipt_category',S.categories.map(v=>[v,v==='Meals'?categoryLabel(v)+' · overnight trip':categoryLabel(v)]),d.category||'Uncategorised')}${Splits.fields(d,'receipt_',role()==='employee'||r.owner_role==='employee')}${field('Location','receipt_merchant_location','text',r.location??d.merchant_location??d.merchant_city??'','maxlength="200" placeholder="Suburb or city, state / region"')}${select('Vehicle (optional)','receipt_vehicle_id',[['','Not a vehicle expense'],...V.filter(v=>v.user_id===r.user_id).map(v=>[v.id,v.name])],d.vehicle_id)}</div>${bookkeeper()?'<button type="button" class="ghost" id="receipt-new-category">+ Create expense category</button>':''}<div id="receipt-meal-fields" ${d.category==='Meals'?'':'hidden'}><div class="notice"><p id="receipt-trip-status"></p><button type="button" class="secondary" id="review-receipt-trip">Review trip & meals</button></div><div class="grid2">${select('Existing overnight trip','receipt_trip_id',[['','Review or create a trip'],...tripOptions.map(t=>[t.id,t.location+' · '+dateAU(t.start)])],d.trip_id)}${select('Receipt meal type','receipt_meal',[['','Choose a meal type'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],d.meal)}</div></div><section class="notice" id="receipt-bank-match"></section><div class="field"><label for="receipt_notes">What was it for?</label><textarea id="receipt_notes" name="receipt_notes">${esc(d.notes||'')}</textarea></div><p class="footnote">${home?'Save draft keeps this out of your records. Save home-office bill files the original and its cost type as fixed-rate evidence.':'Save draft keeps this out of expense totals. Save expense files the details shown here. Employment and business allocations total up to 100%; the remainder is personal.'}</p></div></div><div class="modal-footer"><button type="button" class="danger" id="remove-receipt">Delete receipt</button><button type="button" class="secondary" id="receipt-to-trip">Add to trip meal</button><button type="button" class="secondary" id="save-receipt-draft">Save draft</button><button type="submit">${home?'Save home-office bill':'Save expense'}</button>${options.showNext?'<button type="submit" id="save-receipt-next">Save &amp; next</button>':''}</div></form>`);
 const value=id=>$('#receipt_'+id).value;
 const allocationScope=()=>Splits.scope({work_percent:value('work_percent'),business_percent:value('business_percent')},role()==='employee'||r.owner_role==='employee');
 let bankValues=()=>({bank_choice:d.bank_choice||'auto'});
 const gather=()=>({document_kind:$('#document_kind').value,...(home?{home_office_kind:$('#home_office_kind').value,personally_paid:$('#receipt-personally-paid').checked}:{}),...bankValues(),merchant:value('merchant'),date:dateValue($('#receipt_date')),amount:value('amount')===''?null:value('amount'),currency:value('currency'),scope:allocationScope(),category:value('category'),work_percent:value('work_percent'),business_percent:value('business_percent'),merchant_location:value('merchant_location'),notes:value('notes'),trip_id:value('trip_id')||null,vehicle_id:value('vehicle_id')||null,meal:value('category')==='Meals'?value('meal'):''});
 const confirmCurrency=async code=>{
  const before=d.currency,saved=await api('receipts/'+r.id+'/currency',{currency:code},'PUT');
  for(const k of ['currency','currency_status','currency_evidence'])d[k]=saved.extraction[k];
  r.extraction={...r.extraction,...saved.extraction};if(r.draft)r.draft.currency=d.currency;
  $('#receipt_currency').value=d.currency;$('#currency-status').textContent=d.currency==='AUD'?'AUD · saved':'Foreign currency · saved';$('#foreign-currency-note').hidden=d.currency==='AUD';
  draw();
 };
 bankValues=BankMatching.bindReceipt(r.id,gather,d);
 $('#document_kind').onchange=()=>options.run(async()=>{try{await api('receipts/'+r.id+'/draft',gather(),'PUT');await reopen(r.id);}catch(e){toast(e.message);}});
 Splits.bindFields('receipt_','receipt_amount');
 if(home){$('#receipt-new-category').hidden=true;for(const id of ['category','vehicle_id','merchant_location'])$('#receipt_'+id).closest('.field').hidden=true;$('#receipt-review [data-split-prefix=receipt_]').hidden=true;$('#receipt-to-trip').hidden=true;$('#receipt-meal-fields').hidden=true;}
 if(!Features.enabled('vehicles')&&!d.vehicle_id)$('#receipt_vehicle_id').closest('.field').hidden=true;
 if(!Features.enabled('trips')){$('#receipt-to-trip').hidden=true;$('#review-receipt-trip').hidden=true;}
 $('#receipt_currency').addEventListener('input',()=>{const code=value('currency').toUpperCase();$('#receipt_currency').value=code;if(!/^[A-Z]{3}$/.test(code))return;$('#foreign-currency-note').hidden=code==='AUD';$('#currency-status').textContent=code==='AUD'?'AUD · saves with receipt':'Foreign currency · saves with receipt';if(code==='AUD'&&value('amount')===''&&d.amount!=null)$('#receipt_amount').value=d.amount;if(code!=='AUD'&&d.currency==='AUD'&&Number(value('amount'))===Number(d.amount))$('#receipt_amount').value='';$('#receipt_amount').dispatchEvent(new Event('input'));});
 bind('#preview-original',()=>preview(r.id));bind('#receipt-new-category',()=>createInlineCategory('#receipt_category'));
 let receiptGroup=groups.find(group=>group.receipts.some(entry=>entry.id===r.id));
 const tripStatus=()=>{
  const matched=receiptGroup;
  const selected=value('trip_id');
  $('#receipt-trip-status').textContent=selected?'This meal will join the selected trip.':matched?.existing_trip_id?'A matching trip was found. Review this receipt and any matching meal drafts.':matched?'No matching trip exists. Review the proposed new trip and matching meal receipts.':'Review a new trip or find an existing match. Confirm the location and overnight dates before accepting.';
  $('#receipt-to-trip').textContent=selected?'Add to trip meal':'Review trip & meals';
 };
 const openTrip=async()=>{
  const data=gather();
  if(!data.date)throw Error('Enter the receipt date before reviewing a trip.');
  if(!Features.enabled('trips'))throw Error('Enable Trips & meals in Settings first.');
  if(!['work','business'].includes(data.scope))throw Error('Use an employment or business allocation for this trip, or select an existing trip for a split allocation.');
  if(data.currency&&data.currency!==d.currency)await confirmCurrency(data.currency);
  await api('receipts/'+r.id+'/draft',{...data,category:'Meals',exclude_trip:false},'PUT');
  const group=await api('receipts/'+r.id+'/trip-proposal');
  if(data.trip_id){
   const chosen=tripOptions.find(t=>String(t.id)===String(data.trip_id));
   if(!chosen||chosen.scope!==data.scope||data.date<chosen.start||data.date>chosen.end)throw Error('Choose a trip in the same workspace that covers the receipt date.');
   group.existing_trip_id=chosen.id;group.location=chosen.location;group.scope=chosen.scope;group.start=chosen.start;group.end=chosen.end;group.purpose=chosen.purpose;
   // A manually chosen trip may differ from the geographic suggestion.
   group.receipts=group.receipts.filter(entry=>entry.id===r.id);
  }
  reviewTrip(group);
 };
 const openTripClick=event=>options.run(async()=>{
  const button=event.currentTarget;button.disabled=true;
  try{await openTrip();}catch(error){toast(error.message);}finally{button.disabled=false;}
 });
 $('#receipt_category').onchange=()=>{$('#receipt-meal-fields').hidden=value('category')!=='Meals';tripStatus();};
 $('#receipt_trip_id').onchange=tripStatus;
 tripStatus();
 const reviewForm=$('#receipt-review'),snapshot=()=>['date','work_percent','business_percent','merchant_location','category'].map(id=>value(id)).join('|'),openedSnapshot=snapshot();
 if(d.category==='Meals'&&d.date&&!receiptGroup)api('receipts/'+r.id+'/trip-proposal').then(group=>{
  if(reviewForm.isConnected&&snapshot()===openedSnapshot){receiptGroup=group;tripStatus();}
 }).catch(()=>{});
 for(const id of ['date','work_percent','business_percent','merchant_location'])$('#receipt_'+id).addEventListener('change',()=>{receiptGroup=null;tripStatus();});
 bind('#receipt-to-trip',openTripClick);bind('#review-receipt-trip',openTripClick);
 bind('#use-suggestion',()=>{reviewForm.dataset.dirty='true';$('#receipt_category').value=suggestion.category;$('#receipt-meal-fields').hidden=suggestion.category!=='Meals';tripStatus();});
 bind('#rescan-receipt',()=>reprocess(r,true));
 bind('#save-receipt-draft',()=>options.run(async()=>{const b=$('#save-receipt-draft');b.disabled=true;try{const data=gather();if(data.currency&&data.currency!==d.currency)await confirmCurrency(data.currency);await api('receipts/'+r.id+'/draft',data,'PUT');$('#modal').close();await load();draw();toast('Receipt draft saved.');}catch(e){toast(e.message);}finally{b.disabled=false;}}));
 bind('#remove-receipt',()=>options.run(async()=>{if(!confirm('Delete this unfiled receipt permanently?'))return;try{await api('receipts/'+r.id,{},'DELETE');$('#modal').close();await load();draw();}catch(e){toast(e.message);}}));
 const attachMatch=eid=>options.run(async()=>{
  if(!confirm('Attach this receipt to the selected existing expense?'))return;
  await api('receipts/'+r.id+'/expense',{existing_expense_id:eid});
  $('#expense-match-viewer')?.close();$('#modal').close();await refresh();await load();draw();toast('Receipt attached. No duplicate expense created.');
 });
 document.querySelectorAll('.match-expense').forEach(b=>b.onclick=()=>attachMatch(Number(b.dataset.eid)).catch(error=>toast(error.message)));
 document.querySelectorAll('.match-view-expense').forEach(link=>link.onclick=event=>{event.preventDefault();viewMatch(Number(link.dataset.eid),attachMatch).catch(error=>toast(error.message));});
 const treatment=!home?TaxTreatment.mount($('#receipt-review'),gather):null;
 formHandler('#receipt-review',async(_values,_form,submitter)=>{
  const data=gather();if(data.category==='Meals'&&!data.trip_id){await openTrip();return;}
  if(data.category==='Meals'&&!data.meal)throw Error('Choose a meal type.');
  if(data.currency&&data.currency!==d.currency)await confirmCurrency(data.currency);
  const tax=await treatment?.payload();await api('receipts/'+r.id+'/expense',{...data,status:'ready',...(tax?{tax_treatment:tax}:{})});await options.afterSave(submitter?.id==='save-receipt-next',home?'Home-office bill evidence saved.':'Expense saved.');
 });
}
async function viewMatch(eid,attach){
 const expense=(await api('expenses')).find(item=>item.id===eid);
 if(!expense)throw Error('That expense is no longer available. Refresh the document inbox.');
 let dialog=$('#expense-match-viewer');
 if(!dialog){dialog=document.createElement('dialog');dialog.id='expense-match-viewer';document.body.append(dialog);}
 const allocation=Splits.percentages(expense);
 dialog.setAttribute('aria-labelledby','match-expense-title');
 dialog.innerHTML=`<div class="modal-title"><h2 id="match-expense-title">Existing expense</h2><button type="button" class="ghost" id="close-expense-match" aria-label="Close existing expense">✕</button></div><h3>${esc(expense.merchant)}</h3><div class="grid2">${[['Date',dateAU(expense.date)],['Amount paid',money(expense.amount_cents)],['Category',expense.category],['Owner',expense.owner],['Allocation',`${allocation.work}% employment · ${allocation.business}% business · ${100-allocation.work-allocation.business}% personal`],['Trip / meal',[expense.location,expense.meal].filter(Boolean).join(' · ')||'—'],['Status',expense.status==='ready'?'Reviewed':'To review'],['Reimbursement',expense.reimbursed?'Reimbursed':'Not reimbursed']].map(([label,value])=>`<div class="field"><label>${esc(label)}</label><p>${esc(value)}</p></div>`).join('')}</div><p class="preserve-lines">${esc(expense.notes||'No notes recorded.')}</p><div class="modal-footer">${expense.receipt_id?'<span class="muted">Receipt already attached</span><button type="button" class="secondary" id="match-original-receipt">View attached receipt</button>':'<button type="button" id="attach-viewed-expense">Attach receipt to this expense</button>'}<button type="button" class="secondary" id="return-to-receipt">Back to receipt</button></div>`;
 dialog.showModal();
 bind('#close-expense-match',()=>dialog.close());bind('#return-to-receipt',()=>dialog.close());
 bind('#match-original-receipt',()=>preview(expense.receipt_id));
 bind('#attach-viewed-expense',async event=>{event.currentTarget.disabled=true;try{await attach(eid);}catch(error){toast(error.message);}finally{const button=$('#attach-viewed-expense');if(button)button.disabled=false;}});
}
function reviewTrip(group){
 modal(group.existing_trip_id?'Review meals for existing trip':'Review draft overnight trip',`<form id="receipt-trip-review"><p class="notice">${group.existing_trip_id?'A matching overnight trip was found.':'No matching overnight trip exists. Review the new trip below.'} ${esc(group.location_reason||'')} Confirm the location, overnight dates and purpose. Nothing is added to expenses until you accept.</p><p>${esc(group.owner)} · ${esc(scopeName(group.scope))} trip</p><div class="grid2">${field('Trip location','location','text',group.location,'required')}${field('Departure date','start','date',group.start,'required')}${field('Return date','end','date',group.end,'required')}</div>${field('Trip purpose','purpose','text',group.purpose,'required maxlength="500"')}${group.existing_trip_id?'<p class="footnote">Meals will join the existing trip; its dates and purpose are kept. Each meal must be within its date range.</p>':''}${group.receipts.map((r,i)=>`<section class="proposal-receipt" data-rid="${r.id}"><h3>${esc(r.filename)}</h3><button type="button" class="ghost proposal-preview" data-rid="${r.id}">View receipt</button><div class="grid2">${field('Merchant / payee','proposal_merchant_'+i,'text',r.values.merchant||'','required')}${field('Meal date','proposal_date_'+i,'date',r.values.date,'required')}${field('Amount paid (AUD)','proposal_amount_'+i,'number',r.aud_amount??'','required step="0.01"')}${select('Meal type','proposal_meal_'+i,[['','Confirm meal type'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],r.values.meal)}${field(group.scope==='business'?'Business use (%)':'Employment use (%)','proposal_percent_'+i,'number',r.values.percent??100,'required min="0" max="100"')}</div>${r.values.currency!=='AUD'?`<p class="footnote">Receipt currency ${esc(r.values.currency||'unknown')}: enter the actual AUD amount paid.</p>`:''}${field('Meal notes','proposal_notes_'+i,'text',r.values.notes||'','maxlength="3000"')}</section>`).join('')}<div class="modal-footer"><button type="button" class="secondary" id="save-trip-drafts">Save meal drafts</button><button type="submit">${group.existing_trip_id?'Accept meals':'Accept trip & meals'}</button></div></form>`);
 if(group.existing_trip_id)['location','start','end','purpose'].forEach(id=>$('#'+id).disabled=true);
 document.querySelectorAll('.proposal-preview').forEach(b=>b.onclick=()=>preview(b.dataset.rid));
 const entryData=()=>group.receipts.map((r,i)=>({id:r.id,merchant:$('#proposal_merchant_'+i).value,date:dateValue($('#proposal_date_'+i)),amount:$('#proposal_amount_'+i).value,meal:$('#proposal_meal_'+i).value,percent:$('#proposal_percent_'+i).value||100,notes:$('#proposal_notes_'+i).value}));
 bind('#save-trip-drafts',async()=>{const b=$('#save-trip-drafts');b.disabled=true;try{for(const entry of entryData()){const {id,...data}=entry;await api('receipts/'+id+'/draft',{...data,category:'Meals'},'PUT');}$('#modal').close();await load();draw();toast('Meal drafts saved. Trip not yet accepted.');}catch(e){toast(e.message);}finally{b.disabled=false;}});
 formHandler('#receipt-trip-review',async data=>{const entries=entryData();if(entries.some(e=>!e.meal))throw Error('Confirm a meal type for each receipt.');await api('receipt-trip-proposals/accept',{location:group.location,scope:group.scope,start:group.start,end:group.end,purpose:group.purpose,...data,existing_trip_id:group.existing_trip_id,receipts:entries});$('#modal').close();await refresh();await load();draw();toast('Trip and meals saved.');});
}
async function preview(rid){
 let dialog=$('#receipt-viewer');if(!dialog){dialog=document.createElement('dialog');dialog.id='receipt-viewer';document.body.append(dialog);}
 dialog.innerHTML='<div class="modal-title"><h2>Receipt preview</h2><button id="close-preview" class="ghost" aria-label="Close receipt preview">✕</button></div><p>Loading receipt…</p>';dialog.showModal();$('#close-preview').onclick=()=>dialog.close();
 try{const info=await api('receipts/'+rid+'/info');if(!dialog.open)return;
 dialog.innerHTML=`<div class="modal-title"><h2>${esc(info.filename)}</h2><button id="close-preview" class="ghost" aria-label="Close receipt preview">✕</button></div><div class="preview-toolbar"><button class="secondary" id="preview-prev" aria-label="Previous receipt page">←</button><span id="preview-page"></span><button class="secondary" id="preview-next" aria-label="Next receipt page">→</button><button class="secondary" id="preview-zoom">Zoom in</button><a class="button-link" href="/api/receipts/${rid}">Download original</a></div><div id="preview-stage"><img id="receipt-full-image" alt="Receipt page"><p id="preview-error" class="error hidden">Preview failed. Try another page or download the original.</p></div>`;
 let n=1;const img=$('#receipt-full-image');const show=()=>{img.src='/api/receipts/'+rid+'/preview?page='+n;$('#preview-page').textContent='Page '+n+' of '+info.pages;$('#preview-prev').disabled=n===1;$('#preview-next').disabled=n===info.pages;$('#preview-error').classList.add('hidden');};
 img.onerror=()=>$('#preview-error')?.classList.remove('hidden');$('#preview-prev').onclick=()=>{n--;show();};$('#preview-next').onclick=()=>{n++;show();};$('#close-preview').onclick=()=>dialog.close();$('#preview-zoom').onclick=()=>{const zoomed=$('#preview-stage').classList.toggle('zoomed');$('#preview-zoom').textContent=zoomed?'Fit width':'Zoom in';};show();
 }catch(e){toast(e.message);dialog.close();}
}
async function reopen(rid){await load();draw();const r=items.find(x=>x.id===rid);if(r)review(r);else{$('#modal').close();toast('Document already filed or removed.');}}
async function reload(){await load();draw();}
return {page:pageView,capture,preview,reopen,reload,canLeaveReview};
})();
