'use strict';
const Receipts=(()=>{
let items=[],groups=[], tab='inbox', busy=false,batch={running:false,done:0,total:0,failed:[],cancel:false};const scanning=new Set();
const accept='image/jpeg,image/png,image/webp,application/pdf';
const pending=()=>items.filter(r=>!r.expense_id);
async function load(){[items,groups]=await Promise.all([api('receipts'),api('receipt-trip-proposals')]);}
function values(r){const d={currency:'AUD',percent:100,...r.extraction,...r.draft};if(r.saved_expense)return {...d,...r.saved_expense,amount:r.saved_expense.amount_cents/100,currency:'AUD',currency_status:'saved'};return d;}
function fileLabel(r){return values(r).merchant||r.filename;}
async function pageView(){
  $('#content').innerHTML=heading('Receipt inbox','Capture now. Organise when you have a moment.')+'<div class="panel empty">Loading receipts…</div>';
  try{await load();draw();}catch(e){toast(e.message);}
}
function draw(){
 if(page!=='receipts')return;
 const shown=items.filter(r=>tab==='all'||!r.expense_id);
 $('#content').innerHTML=heading('Receipt inbox','Capture now. Organise when you have a moment.',editor()?`<button class="secondary" id="reprocess-all" ${!S.ai_configured||batch.running||busy||scanning.size||!pending().length?'disabled':''}>✧ Reprocess all with AI</button><button id="capture-receipts" ${batch.running?'disabled':''}>+ Capture receipts</button>`:'<span class="pill">Read only</span>')+
 `<section class="capture-banner"><div class="capture-symbol">✧</div><div><h2>Less typing. More getting on with it.</h2><p>Photos, PDFs and multiple receipts. ${S.ai_configured?'Let AI read the details, then review them in your own time.':'Save your receipts now. Enable Ollama in container settings to read them with AI.'}</p></div>${editor()?'<button class="secondary" id="inbox-upload">Upload receipts</button>':''}</section>
 <div class="inbox-tabs"><button data-tab="inbox" class="${tab==='inbox'?'selected':''}">Draft receipts <span>${pending().length}</span></button><button data-tab="all" class="${tab==='all'?'selected':''}">All receipts <span>${items.length}</span></button></div>
 ${batch.total?`<section class="notice batch-progress" role="status" aria-live="polite">${batch.running?'AI processing · keep this tab open':batch.cancel?'Processing stopped':'AI processing complete'}: ${batch.done} of ${batch.total} · ${batch.failed.length} failed.${batch.running?'<button class="ghost" id="stop-batch">Stop after current receipt</button>':''}${batch.failed.length?`<details><summary>Receipts to retry</summary>${batch.failed.map(x=>`<p>${esc(x)}</p>`).join('')}</details>`:''}</section>`:''}
 ${role()!=='tax_agent'?'<button class="ghost" id="receipt-preferences-button">⚙ Home base & receipt sorting</button>':''}
 ${tab==='inbox'&&groups.length?`<section class="panel"><div class="panel-header"><h2>Possible overnight trips</h2><span>${groups.length} drafts</span></div><div class="receipt-trip-groups">${groups.map((g,i)=>`<section class="card trip-proposal-card"><h3>${esc(g.location)} · ${g.receipts.length} meal receipt(s)</h3><p>${esc(g.owner)} · ${esc(dateAU(g.start))} → ${esc(dateAU(g.end))}</p><p class="footnote">${g.existing_trip_id?'Suggested match to an existing trip.':'Suggested overnight away from '+esc(g.home_base)+'.'} ${esc(g.location_reason||'')} Confirm dates, purpose and meal amounts before accepting.</p>${editor()?`<button class="secondary review-trip-proposal" data-group="${i}" ${batch.running?'disabled':''}>Review ${g.existing_trip_id?'trip meals':'draft trip'}</button><button class="ghost dismiss-trip-proposal" data-group="${i}">Not an overnight</button>`:'<span class="pill">Awaiting review</span>'}</section>`).join('')}</div></section>`:''}
 <div class="panel"><div class="panel-header"><h2>${tab==='inbox'?'Ready when you are':'Your receipt library'}</h2><span class="muted">${shown.length} receipts</span></div><div class="receipt-grid">${shown.map(r=>{
 const d=values(r), state=r.expense_id?'Filed':r.scan_status==='scanned'?'Draft · AI suggestions':r.scan_status==='failed'?'Needs manual entry':r.scan_status==='reading'?'Scan started · retry if interrupted':'Saved for later';
 return `<article class="receipt-card"><div class="receipt-paper"><span class="receipt-thumbnail-fallback hidden">${r.mime==='application/pdf'?'PDF':'Image'}</span><img class="receipt-thumbnail" src="/api/receipts/${r.id}${r.mime==='application/pdf'?'/preview?page=1&thumbnail=1':'/preview'}" alt="${r.mime==='application/pdf'?'First PDF page':'Receipt'} from ${esc(fileLabel(r))}" loading="lazy" decoding="async"></div><div class="receipt-card-body"><span class="pill ${r.expense_id?'business':'review'}">${state}</span><h3>${esc(fileLabel(r))}</h3><p>${esc(dateAU(d.date||'Date to confirm'))} · ${d.amount!=null?esc(d.currency||'Currency?')+' '+esc(Number(d.amount).toFixed(2))+(d.currency_status==='saved'?' · saved expense':d.currency_status==='confirmed'?' · confirmed':d.currency_status==='inferred'?' · suggested':d.currency?' · check currency':''):'Total to confirm'}</p><small>${esc(r.owner)} · ${esc(r.filename)}</small>${actionMenu('Receipt actions for '+fileLabel(r),`<button class="receipt-menu-preview" data-rid="${r.id}">View original receipt</button>${r.expense_id&&editor()?`<button class="receipt-menu-expense" data-eid="${r.expense_id}">Edit saved expense</button>`:''}${!r.expense_id&&editor()?`<button class="review-receipt" data-rid="${r.id}" ${batch.running?'disabled':''}>Edit draft</button>`:''}`)}<button class="secondary wide review-receipt" data-rid="${r.id}" ${scanning.has(r.id)||batch.running?'disabled':''}>${r.expense_id||!editor()?'View receipt':'Review & categorise'} →</button>${editor()&&!r.expense_id?`<button class="ghost wide reprocess-receipt" data-rid="${r.id}" ${!S.ai_configured||scanning.has(r.id)||batch.running?'disabled':''}>${scanning.has(r.id)?'Reading receipt…':r.scan_status==='captured'?'✧ Read with AI':'✧ Reprocess with AI'}</button>${r.scan_error?`<p class="error">${esc(r.scan_error)}</p>`:''}`:''}</div></article>`;
 }).join('')}</div>${!shown.length?'<div class="empty"><div class="empty-receipt">▤</div><h2>'+ (tab==='inbox'?'A clear inbox feels good.':'Your receipts belong here.')+'</h2><p>Capture a receipt now and come back to the details later.</p></div>':''}</div>`;
 document.querySelectorAll('.receipt-thumbnail').forEach(img=>{const fallback=()=>{img.classList.add('hidden');img.previousElementSibling.classList.remove('hidden');};img.onerror=fallback;if(img.complete&&!img.naturalWidth)fallback();});
 bind('#reprocess-all',reprocessAll);bind('#stop-batch',()=>{batch.cancel=true;$('#stop-batch').disabled=true;$('#stop-batch').textContent='Stopping after current receipt…';});bind('#receipt-preferences-button',()=>Tracking.preferences().catch(e=>toast(e.message)));
 document.querySelectorAll('.review-trip-proposal').forEach(b=>b.onclick=()=>reviewTrip(groups[Number(b.dataset.group)]));
 document.querySelectorAll('.dismiss-trip-proposal').forEach(b=>b.onclick=async()=>{b.disabled=true;try{for(const r of groups[Number(b.dataset.group)].receipts)await api('receipts/'+r.id+'/draft',{exclude_trip:true},'PUT');await load();draw();toast('Suggestion dismissed. Receipts remain as drafts.');}catch(e){toast(e.message);b.disabled=false;}});
 document.querySelectorAll('.receipt-menu-preview').forEach(b=>b.onclick=()=>preview(b.dataset.rid));document.querySelectorAll('.receipt-menu-expense').forEach(b=>b.onclick=()=>expenseModal(E.find(e=>e.id===Number(b.dataset.eid))));
 ['#capture-receipts','#inbox-upload','#empty-upload'].forEach(id=>bind(id,capture));
 document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;draw();});
 document.querySelectorAll('.review-receipt').forEach(b=>b.onclick=()=>review(items.find(r=>r.id===b.dataset.rid)));
 document.querySelectorAll('.reprocess-receipt').forEach(b=>b.onclick=()=>reprocess(items.find(r=>r.id===b.dataset.rid)));
}
async function reprocess(r,fromReview=false){
 if(!editor()||!S.ai_configured||scanning.has(r.id)||batch.running)return;
 const form=fromReview?$('#receipt-review'):null;
 const controls=form?[...form.querySelectorAll('input,select,textarea,button')].map(el=>[el,el.disabled]):[];
 controls.forEach(([el])=>el.disabled=true);scanning.add(r.id);draw();
 if(form)$('#rescan-receipt').textContent='Reading receipt…';
 let success=false;
 try{await api('receipts/'+r.id+'/extract',{unfiled_only:true});success=true;toast('Receipt reprocessed. Check the new suggestions before saving.');}
 catch(e){toast('Reprocessing failed. '+e.message);}
 finally{scanning.delete(r.id);controls.forEach(([el,disabled])=>el.disabled=disabled);if(form?.isConnected)$('#rescan-receipt').textContent='✧ Reprocess with AI';}
 try{await load();draw();if(success&&page==='receipts'&&(fromReview?form?.isConnected&&$('#modal').open:!$('#modal').open))review(items.find(x=>x.id===r.id));}catch(e){toast(e.message);}
}
function capture(){
 if(!editor())return;
 if(busy||batch.running)return toast('Receipt processing is still running.');
 modal('Capture receipts',`<div class="capture-drop"><span class="capture-symbol">▤</span><h2>Snap it. Save it. Sort it later.</h2><p>JPEG, PNG, WebP or PDF · up to 12 MB per file</p><label class="upload-label" for="inbox-files">Choose files</label><input class="hidden" id="inbox-files" type="file" multiple accept="${accept}"><label class="upload-label secondary" for="inbox-camera">Take a photo</label><input class="hidden" id="inbox-camera" type="file" accept="image/*" capture="environment"></div><label class="check"><input id="auto-scan" type="checkbox" ${S.ai_configured?'checked':'disabled'}>Read with AI after upload</label><p class="footnote">${S.ai_configured?'Sends these receipts to your configured Ollama server.':'AI is not configured. Receipts are still saved and can be categorised manually.'} No category, workspace or tax allocation is required now.</p><div id="capture-progress" role="status" aria-live="polite"></div><div class="modal-footer"><button class="secondary" id="capture-done">Done</button></div>`);
 bind('#capture-done',()=>{$('#modal').close();page='receipts';render();});
 const upload=async files=>{
  if(!files.length||busy)return;
  busy=true;const scan=$('#auto-scan').checked;const progress=$('#capture-progress');
  $('#close-modal').disabled=true;$('#capture-done').disabled=true;$('#inbox-files').disabled=true;$('#inbox-camera').disabled=true;
  const preventClose=e=>e.preventDefault();$('#modal').addEventListener('cancel',preventClose);
  for(const f of files){
    const row=document.createElement('div');row.className='upload-progress';row.textContent=f.name+' — uploading…';progress.append(row);
    try{
      if(f.size>12*1024*1024)throw Error('File exceeds 12 MB.');
      const fd=new FormData();fd.append('file',f);const r=await api('receipts',fd);
      row.textContent=f.name+(r.duplicate?' — already saved':' — saved');
      if(scan&&!r.duplicate){row.textContent=f.name+' — saved, AI reading…';try{await api('receipts/'+r.id+'/extract',{unfiled_only:true});row.textContent=f.name+' — ready to categorise';}catch(e){row.textContent=f.name+' — saved. '+e.message;}}
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
  try{await api('receipts/'+r.id+'/extract',{unfiled_only:true});}catch(e){batch.failed.push(r.name+' — '+e.message);}
  batch.done++;try{await load();}catch(e){batch.failed.push('Refresh failed: '+e.message);}draw();
 }
 batch.running=false;try{await load();}catch(e){toast(e.message);}draw();toast(`Processed ${batch.done} draft receipt(s). ${batch.failed.length} failed. Manual draft edits were kept.`);
}
function review(r){
 if(!editor()||r.expense_id)return preview(r.id);
 const d=values(r),foreign=d.amount!=null&&d.currency!=='AUD',suggestion=r.suggestion;
 const tripOptions=T.filter(t=>t.user_id===r.user_id),amount=r.draft?.amount!=null?r.draft.amount:!foreign&&d.amount!=null?d.amount:'';
 modal('Review receipt',`<form id="receipt-review"><div class="receipt-review-layout"><div class="receipt-preview"><img src="/api/receipts/${r.id}/preview${r.mime==='application/pdf'?'?page=1':''}" alt="Original receipt"><button type="button" class="secondary" id="preview-original">View full receipt</button><p class="footnote">${esc(r.filename)} · ${esc(r.owner)}</p><button type="button" id="rescan-receipt" class="secondary wide" ${S.ai_configured?'':'disabled'}>✧ Reprocess with AI</button><p class="footnote">A fresh AI reading updates suggestions. Saved draft edits and confirmed currency are kept.</p>${r.scan_error?`<p class="error">${esc(r.scan_error)}</p>`:''}</div><div><section class="currency-review"><p id="currency-status">${esc(d.currency_status==='confirmed'?'Currency confirmed by you.':d.currency_evidence||'AUD is the default unless the receipt specifies another currency.')}</p><div class="currency-controls">${field('Receipt currency','receipt_currency','text',d.currency??'AUD','maxlength="3" pattern="[A-Za-z]{3}" placeholder="AUD"')}<button type="button" class="secondary" id="save-currency">Confirm currency</button><button type="button" class="secondary" id="confirm-aud">This receipt is AUD</button></div><p class="footnote">For a foreign receipt, enter the actual AUD amount paid. Changing the currency label does not convert money.</p></section>${suggestion?`<div class="notice">Previous reviewed category: ${esc(suggestion.category)} / ${esc(scopeName(suggestion.scope))}. <button type="button" class="ghost" id="use-suggestion">Use suggestion</button></div>`:''}
 ${r.matches?.length?`<section class="match-box"><h3>Possible existing expense</h3>${r.matches.map(e=>`<button class="secondary match-expense" type="button" data-eid="${e.id}" ${e.receipt_id?'disabled':''}>${esc(e.merchant)} · ${money(e.amount_cents)}${e.receipt_id?' · receipt attached':' · Attach receipt'}</button>`).join('')}</section>`:''}
 <div class="grid2">${field('Merchant / payee','receipt_merchant','text',d.merchant||'','required maxlength="200"')}${field('Receipt date','receipt_date','date',d.date||'','required')}${field('Amount paid (AUD)','receipt_amount','number',amount,'required step="0.01"')}${select('Workspace','receipt_scope',role()==='employee'||r.owner_role==='employee'?[['business','Business']]:[['work','Employment'],['business','Business'],['personal','Personal']],d.scope||r.preferences?.scope||'work')}${select('Category','receipt_category',S.categories.map(v=>[v,v==='Meals'?'Meals · overnight trip':v]),d.category||'Uncategorised')}${field('Work / business use (%)','receipt_percent','number',d.percent??100,'min="0" max="100" required')}${field('Receipt city / suburb','receipt_merchant_city','text',d.merchant_city||'','maxlength="200"')}${select('Vehicle (optional)','receipt_vehicle_id',[['','Not a vehicle expense'],...V.filter(v=>v.user_id===r.user_id).map(v=>[v.id,v.name])],d.vehicle_id)}</div>${bookkeeper()?'<button type="button" class="ghost" id="receipt-new-category">+ Create expense category</button>':''}<div id="receipt-meal-fields" ${d.category==='Meals'?'':'hidden'}><p class="notice">Use the suggested draft trip in the inbox, or choose an existing overnight trip below. Saving a draft keeps the food receipt available for grouping.</p><div class="grid2">${select('Existing overnight trip','receipt_trip_id',[['','Review a draft trip first'],...tripOptions.map(t=>[t.id,t.location+' · '+dateAU(t.start)])],d.trip_id)}${select('Receipt meal type','receipt_meal',[['','Choose a meal type'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],d.meal)}</div></div><div class="field"><label for="receipt_notes">What was it for?</label><textarea id="receipt_notes" name="receipt_notes">${esc(d.notes||'')}</textarea></div><p class="footnote">Save draft keeps this out of expense totals. Save expense files the details shown here. Use defaults to 100%; change it where needed.</p></div></div><div class="modal-footer"><button type="button" class="danger" id="remove-receipt">Delete receipt</button><button type="button" class="secondary" id="receipt-to-trip">Add to trip meal</button><button type="button" class="secondary" id="save-receipt-draft">Save draft</button><button type="submit">Save expense</button></div></form>`);
 const value=id=>$('#receipt_'+id).value;
 const gather=()=>({merchant:value('merchant'),date:dateValue($('#receipt_date')),amount:value('amount')===''?null:value('amount'),currency:value('currency'),scope:value('scope'),category:value('category'),percent:value('percent')===''?100:value('percent'),merchant_city:value('merchant_city'),notes:value('notes'),trip_id:value('trip_id')||null,vehicle_id:value('vehicle_id')||null,meal:value('category')==='Meals'?value('meal'):''});
 const confirmCurrency=async code=>{
  const before=d.currency,saved=await api('receipts/'+r.id+'/currency',{currency:code},'PUT');
  for(const k of ['currency','currency_status','currency_evidence'])d[k]=saved.extraction[k];
  r.extraction={...r.extraction,...saved.extraction};if(r.draft)r.draft.currency=d.currency;
  $('#receipt_currency').value=d.currency;$('#currency-status').textContent=d.currency_evidence;
  const input=$('#receipt_amount');if(d.currency==='AUD'&&input.value===''&&d.amount!=null)input.value=d.amount;else if(before==='AUD'&&d.currency!=='AUD'&&Number(input.value)===d.amount)input.value='';draw();toast('Receipt currency confirmed.');
 };
 const saveCurrency=async code=>{const buttons=[$('#save-currency'),$('#confirm-aud')];buttons.forEach(b=>b.disabled=true);try{await confirmCurrency(code);}catch(e){toast(e.message);}finally{buttons.forEach(b=>b.disabled=false);}};
 bind('#save-currency',()=>saveCurrency(value('currency')));bind('#confirm-aud',()=>saveCurrency('AUD'));bind('#preview-original',()=>preview(r.id));bind('#receipt-new-category',()=>createInlineCategory('#receipt_category'));
 $('#receipt_category').onchange=()=>$('#receipt-meal-fields').hidden=value('category')!=='Meals';
 bind('#receipt-to-trip',()=>mealFromReceipt({...r,extraction:{...d,...gather()}}));
 bind('#use-suggestion',()=>{$('#receipt_category').value=suggestion.category;$('#receipt_scope').value=suggestion.scope;$('#receipt-meal-fields').hidden=suggestion.category!=='Meals';});
 bind('#rescan-receipt',()=>reprocess(r,true));
 bind('#save-receipt-draft',async()=>{const b=$('#save-receipt-draft');b.disabled=true;try{const data=gather();if(data.currency&&data.currency!==d.currency)await confirmCurrency(data.currency);await api('receipts/'+r.id+'/draft',data,'PUT');$('#modal').close();await load();draw();toast('Receipt draft saved.');}catch(e){toast(e.message);}finally{b.disabled=false;}});
 bind('#remove-receipt',async()=>{if(!confirm('Delete this unfiled receipt permanently?'))return;try{await api('receipts/'+r.id,{},'DELETE');$('#modal').close();await load();draw();}catch(e){toast(e.message);}});
 document.querySelectorAll('.match-expense').forEach(b=>b.onclick=async()=>{if(!confirm('Attach this receipt to the selected existing expense?'))return;try{await api('receipts/'+r.id+'/expense',{existing_expense_id:Number(b.dataset.eid)});$('#modal').close();await refresh();await load();draw();toast('Receipt attached. No duplicate expense created.');}catch(e){toast(e.message);}});
 formHandler('#receipt-review',async()=>{
  const data=gather();if(data.category==='Meals'&&(!data.trip_id||!data.meal))throw Error('Choose an existing trip and meal type, or Save draft and review the suggested trip in the inbox.');
  if(data.currency&&data.currency!==d.currency)await confirmCurrency(data.currency);
  await api('receipts/'+r.id+'/expense',{...data,status:'ready'});$('#modal').close();await refresh();await load();draw();toast('Expense saved.');
 });
}
function reviewTrip(group){
 modal(group.existing_trip_id?'Review meals for existing trip':'Review draft overnight trip',`<form id="receipt-trip-review"><p class="notice">These receipts appear to be away from ${esc(group.home_base)}. Confirm that this was an overnight trip. Nothing is added to expenses until you accept.</p><p>${esc(group.owner)}</p><div class="grid2">${field('Trip location','location','text',group.location,'required')}${select('Trip workspace','scope',group.scope==='business'&&role()==='employee'?[['business','Business']]:[['work','Employment'],['business','Business']],group.scope)}${field('Departure date','start','date',group.start,'required')}${field('Return date','end','date',group.end,'required')}</div>${field('Trip purpose','purpose','text',group.purpose,'required maxlength="500"')}${group.existing_trip_id?'<p class="footnote">Meals will join the existing trip; its dates and purpose are kept. Each meal must be within its date range.</p>':''}${group.receipts.map((r,i)=>`<section class="proposal-receipt" data-rid="${r.id}"><h3>${esc(r.filename)}</h3><button type="button" class="ghost proposal-preview" data-rid="${r.id}">View receipt</button><div class="grid2">${field('Merchant / payee','proposal_merchant_'+i,'text',r.values.merchant||'','required')}${field('Meal date','proposal_date_'+i,'date',r.values.date,'required')}${field('Amount paid (AUD)','proposal_amount_'+i,'number',r.aud_amount??'','required step="0.01"')}${select('Meal type','proposal_meal_'+i,[['','Confirm meal type'],...['Breakfast','Lunch','Dinner','Incidentals'].map(v=>[v,v])],r.values.meal)}${field('Work / business use (%)','proposal_percent_'+i,'number',r.values.percent??100,'required min="0" max="100"')}</div>${r.values.currency!=='AUD'?`<p class="footnote">Receipt currency ${esc(r.values.currency||'unknown')}: enter the actual AUD amount paid.</p>`:''}${field('Meal notes','proposal_notes_'+i,'text',r.values.notes||'','maxlength="3000"')}</section>`).join('')}<div class="modal-footer"><button type="button" class="secondary" id="save-trip-drafts">Save meal drafts</button><button type="submit">${group.existing_trip_id?'Accept meals':'Accept trip & meals'}</button></div></form>`);
 if(group.existing_trip_id)['location','scope','start','end','purpose'].forEach(id=>$('#'+id).disabled=true);
 document.querySelectorAll('.proposal-preview').forEach(b=>b.onclick=()=>preview(b.dataset.rid));
 const entryData=()=>group.receipts.map((r,i)=>({id:r.id,merchant:$('#proposal_merchant_'+i).value,date:dateValue($('#proposal_date_'+i)),amount:$('#proposal_amount_'+i).value,meal:$('#proposal_meal_'+i).value,percent:$('#proposal_percent_'+i).value||100,notes:$('#proposal_notes_'+i).value}));
 bind('#save-trip-drafts',async()=>{const b=$('#save-trip-drafts');b.disabled=true;try{for(const entry of entryData()){const {id,...data}=entry;await api('receipts/'+id+'/draft',{...data,category:'Meals'},'PUT');}$('#modal').close();await load();draw();toast('Meal drafts saved. Trip not yet accepted.');}catch(e){toast(e.message);}finally{b.disabled=false;}});
 formHandler('#receipt-trip-review',async data=>{const entries=entryData();if(entries.some(e=>!e.meal))throw Error('Confirm a meal type for each receipt.');await api('receipt-trip-proposals/accept',{location:group.location,scope:group.scope,start:group.start,end:group.end,purpose:group.purpose,...data,existing_trip_id:group.existing_trip_id,receipts:entries});$('#modal').close();await refresh();await load();draw();toast('Trip and meals saved.');});
}
function mealFromReceipt(r){
 const trips=T.filter(t=>t.user_id===r.user_id);
 if(!trips.length)return toast('Create an overnight trip for this person in Trips & meals first.');
 modal('Add receipt to a trip meal',`<form id="receipt-trip-form">${select('Overnight trip','selected_trip',trips.map(t=>[t.id,t.location+' · '+dateAU(t.start)]))}<div class="modal-footer"><button type="submit">Continue to meal details</button></div></form>`);
 formHandler('#receipt-trip-form',async d=>{const trip=trips.find(t=>t.id===Number(d.selected_trip)),v=r.extraction||{};
 expenseModal(null,trip,{receipt_id:r.id,merchant:v.merchant||'',date:v.date||trip.start,amount_cents:v.currency==='AUD'&&v.amount!=null?Math.round(v.amount*100):0,notes:v.notes||'',percent:v.percent??100,meal:v.meal||'Dinner'});});
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
return {page:pageView,capture,preview};
})();
