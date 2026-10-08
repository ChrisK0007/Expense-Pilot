'use strict';
const Receipts=(()=>{
let items=[], tab='inbox', busy=false;
const accept='image/jpeg,image/png,image/webp,application/pdf';
const pending=()=>items.filter(r=>!r.expense_id);
async function load(){items=await api('receipts');}
function fileLabel(r){return r.extraction?.merchant||r.filename;}
async function pageView(){
  $('#content').innerHTML=heading('Receipt inbox','Capture now. Organise when you have a moment.')+'<div class="panel empty">Loading receipts…</div>';
  try{await load();draw();}catch(e){toast(e.message);}
}
function draw(){
 if(page!=='receipts')return;
 const shown=items.filter(r=>tab==='all'||!r.expense_id);
 $('#content').innerHTML=heading('Receipt inbox','Capture now. Organise when you have a moment.',editor()?'<button id="capture-receipts">+ Capture receipts</button>':'<span class="pill">Read only</span>')+
 `<section class="capture-banner"><div class="capture-symbol">✧</div><div><h2>Less typing. More getting on with it.</h2><p>Photos, PDFs and multiple receipts. ${S.ai_configured?'Let AI read the details, then review them in your own time.':'Save your receipts now. Enable Ollama in container settings to read them with AI.'}</p></div>${editor()?'<button class="secondary" id="inbox-upload">Upload receipts</button>':''}</section>
 <div class="inbox-tabs"><button data-tab="inbox" class="${tab==='inbox'?'selected':''}">To categorise <span>${pending().length}</span></button><button data-tab="all" class="${tab==='all'?'selected':''}">All receipts <span>${items.length}</span></button></div>
 <div class="panel"><div class="panel-header"><h2>${tab==='inbox'?'Ready when you are':'Your receipt library'}</h2><span class="muted">${shown.length} receipts</span></div><div class="receipt-grid">${shown.map(r=>{
 const d=r.extraction||{}, state=r.expense_id?'Filed':r.scan_status==='scanned'?'Ready to categorise':r.scan_status==='failed'?'Needs manual entry':r.scan_status==='reading'?'Scan started · retry if interrupted':'Saved for later';
 return `<article class="receipt-card"><div class="receipt-paper"><span class="receipt-thumbnail-fallback hidden">${r.mime==='application/pdf'?'PDF':'Image'}</span><img class="receipt-thumbnail" src="/api/receipts/${r.id}${r.mime==='application/pdf'?'/preview?page=1&thumbnail=1':'/preview'}" alt="${r.mime==='application/pdf'?'First PDF page':'Receipt'} from ${esc(fileLabel(r))}" loading="lazy" decoding="async"></div><div class="receipt-card-body"><span class="pill ${r.expense_id?'business':'review'}">${state}</span><h3>${esc(fileLabel(r))}</h3><p>${esc(d.date||'Date to confirm')} · ${d.amount!=null?esc(d.currency||'Currency?')+' '+esc(d.amount.toFixed(2))+(d.currency_status==='confirmed'?' · confirmed':d.currency_status==='inferred'?' · suggested':d.currency?' · check currency':''):'Total to confirm'}</p><small>${esc(r.owner)} · ${esc(r.filename)}</small><button class="secondary wide review-receipt" data-rid="${r.id}">${r.expense_id||!editor()?'View receipt':'Review & categorise'} →</button></div></article>`;
 }).join('')}</div>${!shown.length?'<div class="empty"><div class="empty-receipt">▤</div><h2>'+ (tab==='inbox'?'A clear inbox feels good.':'Your receipts belong here.')+'</h2><p>Capture a receipt now and come back to the details later.</p></div>':''}</div>`;
 document.querySelectorAll('.receipt-thumbnail').forEach(img=>{const fallback=()=>{img.classList.add('hidden');img.previousElementSibling.classList.remove('hidden');};img.onerror=fallback;if(img.complete&&!img.naturalWidth)fallback();});
 ['#capture-receipts','#inbox-upload','#empty-upload'].forEach(id=>bind(id,capture));
 document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;draw();});
 document.querySelectorAll('[data-rid]').forEach(b=>b.onclick=()=>review(items.find(r=>r.id===b.dataset.rid)));
}
function capture(){
 if(!editor())return;
 if(busy)return toast('Your receipt uploads are still running.');
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
      if(scan&&!r.duplicate){row.textContent=f.name+' — saved, AI reading…';try{await api('receipts/'+r.id+'/extract',{});row.textContent=f.name+' — ready to categorise';}catch(e){row.textContent=f.name+' — saved. '+e.message;}}
    }catch(e){row.textContent=f.name+' — '+e.message;row.classList.add('error');}
  }
  busy=false;$('#modal').removeEventListener('cancel',preventClose);$('#close-modal').disabled=false;$('#capture-done').disabled=false;$('#inbox-files').disabled=false;$('#inbox-camera').disabled=false;
  await load();draw();
 };
 $('#inbox-files').onchange=e=>upload([...e.target.files]);$('#inbox-camera').onchange=e=>upload([...e.target.files]);
}
function review(r){
 if(!editor())return preview(r.id);
 const d=r.extraction||{}, foreign=d.amount!=null&&d.currency!=='AUD', suggestion=r.suggestion;
 if(r.expense_id)return preview(r.id);
 modal('Review receipt',`<form id="receipt-review"><div class="receipt-review-layout"><div class="receipt-preview">${r.mime.startsWith('image/')?`<img src="/api/receipts/${r.id}" alt="Original receipt">`:'<img src="/api/receipts/${r.id}/preview?page=1" alt="First page of PDF receipt">'}<button type="button" class="secondary" id="preview-original">View full receipt</button><p class="footnote">${esc(r.filename)} · ${esc(r.owner)}</p><button type="button" id="rescan-receipt" class="secondary wide" ${S.ai_configured?'':'disabled'}>✧ Read with AI</button>${r.scan_error?`<p class="error">${esc(r.scan_error)}</p>`:''}</div><div><section class="currency-review"><p id="currency-status">${esc(d.currency_status==='confirmed'?'Currency confirmed by you.':d.currency_evidence||'Check the currency against the receipt; older AI results may contain a guess.')}</p><div class="currency-controls">${field('Receipt currency','receipt_currency','text',d.currency||'','maxlength="3" pattern="[A-Za-z]{3}" placeholder="AUD"')}<button type="button" class="secondary" id="save-currency">Confirm currency</button><button type="button" class="secondary" id="confirm-aud">This receipt is AUD</button></div><p class="footnote">Correcting the label does not convert money or change a saved expense. For a foreign receipt, enter the actual AUD amount paid below.</p></section>${suggestion?`<div class="notice">Your last reviewed expense from this merchant was <strong>${esc(suggestion.category)}</strong> / ${esc(scopeName(suggestion.scope))}. <button type="button" class="ghost" id="use-suggestion">Use suggestion</button></div>`:''}
 ${r.matches?.length?`<section class="match-box"><h3>Possible existing expense</h3><p>Same date and amount. Check before adding another.</p>${r.matches.map(e=>`<button class="secondary match-expense" type="button" data-eid="${e.id}" ${e.receipt_id?'disabled':''}>${esc(e.merchant)} · ${money(e.amount_cents)}${e.receipt_id?' · receipt attached':' · Attach receipt'}</button>`).join('')}</section>`:''}
 <div class="grid2">${field('Merchant / payee','receipt_merchant','text',d.merchant||'','required maxlength="200"')}${field('Receipt date','receipt_date','date',d.date||'','required')}${field('Amount paid (AUD)','receipt_amount','number',!foreign&&d.amount!=null?d.amount:'','required step="0.01"')}${select('Workspace','receipt_scope',role()==='employee'||r.owner_role==='employee'?[['business','Business']]:[['','Choose later'],['work','Employment'],['business','Business'],['personal','Personal']])}${select('Category','receipt_category',S.categories.filter(v=>v!=='Meals').map(v=>[v,v]),d.category==='Meals'?'Uncategorised':d.category||'Uncategorised')}${field('Work / business use (%)','receipt_percent','number','0','min="0" max="100" required')}</div><div class="field"><label for="receipt_notes">What was it for?</label><textarea id="receipt_notes" name="receipt_notes" placeholder="Add the purpose when you’re ready">${esc(d.notes||'')}</textarea></div><label class="check"><input id="receipt_ready" type="checkbox">I have reviewed the details</label><p class="footnote">AI fields are suggestions. Set the use percentage yourself. Unfiled receipts stay out of expense totals. Your tax agent can view them in the inbox.</p></div></div><div class="modal-footer"><button type="button" class="danger" id="remove-receipt">Delete receipt</button><button type="button" class="secondary" id="receipt-to-trip">Add to trip meal</button><button type="button" class="secondary" id="receipt-later">Decide later</button><button type="submit">Save expense</button></div></form>`);
 const confirmCurrency=async code=>{
  const before=d.currency;const saved=await api('receipts/'+r.id+'/currency',{currency:code},'PUT');
  Object.assign(d,saved.extraction);r.extraction=d;$('#receipt_currency').value=d.currency;
  $('#currency-status').textContent=d.currency_evidence;
  const input=$('#receipt_amount');if(d.currency==='AUD'&&input.value===''&&d.amount!=null)input.value=d.amount;
  else if(before==='AUD'&&d.currency!=='AUD'&&Number(input.value)===d.amount)input.value='';
  draw();toast('Receipt currency confirmed.');
 };
 const saveCurrency=async code=>{const buttons=[$('#save-currency'),$('#confirm-aud')];buttons.forEach(b=>b.disabled=true);try{await confirmCurrency(code);}catch(e){toast(e.message);}finally{buttons.forEach(b=>b.disabled=false);}};
 bind('#save-currency',()=>saveCurrency($('#receipt_currency').value));
 bind('#confirm-aud',()=>saveCurrency('AUD'));
 bind('#preview-original',()=>preview(r.id));
 bind('#receipt-to-trip',()=>mealFromReceipt(r));
 bind('#receipt-later',()=>$('#modal').close());
 bind('#use-suggestion',()=>{$('#receipt_category').value=suggestion.category==='Meals'?'Uncategorised':suggestion.category;$('#receipt_scope').value=suggestion.scope;});
 bind('#rescan-receipt',async()=>{const b=$('#rescan-receipt');b.disabled=true;b.textContent='Reading…';try{await api('receipts/'+r.id+'/extract',{});await load();if($('#receipt-review'))review(items.find(x=>x.id===r.id));}catch(e){toast(e.message);b.disabled=false;b.textContent='✧ Read with AI';}});
 bind('#remove-receipt',async()=>{if(!confirm('Delete this unfiled receipt permanently?'))return;try{await api('receipts/'+r.id,{},'DELETE');$('#modal').close();await load();draw();}catch(e){toast(e.message);}});
 document.querySelectorAll('.match-expense').forEach(b=>b.onclick=async()=>{if(!confirm('Attach this receipt to the selected existing expense?'))return;try{await api('receipts/'+r.id+'/expense',{existing_expense_id:Number(b.dataset.eid)});$('#modal').close();await refresh();await load();draw();toast('Receipt attached. No duplicate expense created.');}catch(e){toast(e.message);}});
 formHandler('#receipt-review',async()=>{
   const value=id=>$('#receipt_'+id).value;
   if(!value('scope'))throw Error('Choose Employment, Business or Personal before saving. Use Decide later to leave it in your inbox.');
   if(value('currency').trim().toUpperCase()!==d.currency&&value('currency').trim())await confirmCurrency(value('currency'));
   if(!value('amount'))throw Error('Enter the actual AUD amount paid before saving.');
   await api('receipts/'+r.id+'/expense',{merchant:value('merchant'),date:value('date'),amount:value('amount'),scope:value('scope'),category:value('category'),percent:value('percent'),trip_id:null,meal:'',notes:value('notes'),status:$('#receipt_ready').checked?'ready':'review',shared:false});
   $('#modal').close();await refresh();await load();draw();toast('Expense saved.');
 });
}
function mealFromReceipt(r){
 const trips=T.filter(t=>t.user_id===r.user_id);
 if(!trips.length)return toast('Create an overnight trip for this person in Trips & meals first.');
 modal('Add receipt to a trip meal',`<form id="receipt-trip-form">${select('Overnight trip','selected_trip',trips.map(t=>[t.id,t.location+' · '+t.start]))}<div class="modal-footer"><button type="submit">Continue to meal details</button></div></form>`);
 formHandler('#receipt-trip-form',async d=>{const trip=trips.find(t=>t.id===Number(d.selected_trip)),v=r.extraction||{};
 expenseModal(null,trip,{receipt_id:r.id,merchant:v.merchant||'',date:v.date||trip.start,amount_cents:v.currency==='AUD'&&v.amount!=null?Math.round(v.amount*100):0,notes:v.notes||''});});
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
