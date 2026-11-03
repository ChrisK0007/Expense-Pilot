'use strict';
const BillingWorkspace=(()=>{
 let current=null;
 const units=value=>[...new Set(['Units','Hours','Days','Flight tests','Kilometres','Sessions','Jobs','Items',...(value?[value]:[])])];
 const active=()=>!!current;
 async function recover(doc,type){
  const key=doc?'document-'+doc.id:'new-'+type;
  if(!owner())return {key,version:0,payload:null};
  const r=await api('billing/editor-drafts/'+key);
  return {...r,key,conflict:!!(doc&&r.payload&&r.payload.version!==doc.version)};
 }
 function status(s,message){if(s.form.isConnected)s.status.textContent=message;}
 async function save(s){
  clearTimeout(s.timer);
  if(s.finished||s.conflict)return;
  const payload={...s.gather(true),request_key:s.requestKey},fingerprint=JSON.stringify(payload);
  s.queue=s.queue.catch(()=>{}).then(async()=>{
   if(s.finished||s.conflict||s.last===fingerprint)return;
   status(s,'Saving draft…');
   try{const r=await api('billing/editor-drafts/'+s.key,{version:s.version,payload},'PUT');s.version=r.version;s.last=fingerprint;status(s,'Draft saved');}
   catch(e){status(s,'Draft not saved: '+e.message);if(e.status===409){s.conflict=true;if(!s.form.querySelector('.draft-conflict')){const note=document.createElement('div');note.className='notice draft-conflict';note.innerHTML='<p>Another tab changed this draft. Reload to recover its saved version; the unsaved edits in this tab will be discarded.</p><button type="button" class="secondary">Reload saved draft</button>';note.querySelector('button').onclick=()=>location.reload();s.form.prepend(note);}}throw e;}
  });
  return s.queue;
 }
 async function leave(){
  const s=current;if(!s)return;
  if(s.conflict)throw Error('Resolve the draft conflict before leaving this editor.');
  if(s.submitting)throw Error('Please wait while the invoice is saved.');
  try{await save(s);}catch(e){toast(e.message);throw e;}
  clearTimeout(s.timer);clearTimeout(s.previewTimer);s.finished=true;current=null;
  if(s.previewURL)URL.revokeObjectURL(s.previewURL);
 }
 function complete(){if(!current)return;clearTimeout(current.timer);clearTimeout(current.previewTimer);current.finished=true;if(current.previewURL)URL.revokeObjectURL(current.previewURL);current=null;}
 async function beforeSubmit(){
  const s=current;if(!s)return {};
  if(s.conflict)throw Error('Resolve the saved-draft conflict before saving this invoice.');
  s.submitting=true;s.form.inert=true;clearTimeout(s.timer);
  try{await save(s);}catch(e){s.submitting=false;s.form.inert=false;throw e;}
  return {editor_draft:{key:s.key,version:s.version},...(s.doc?{}:{request_key:s.requestKey})};
 }
 function resume(){if(current){current.submitting=false;current.form.inert=false;}}
 function pdfURL(value){const bytes=Uint8Array.from(atob(value),c=>c.charCodeAt(0));return URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));}
 async function preview(s,data){
  const token=++s.previewRevision;
  try{
   const result=await api('billing/preview?format=image',data);
   if(token!==s.previewRevision||!s.preview.isConnected||s.finished)return;
   if(s.previewURL)URL.revokeObjectURL(s.previewURL);s.previewURL=pdfURL(result.pdf);
   s.preview.innerHTML=`<img class="invoice-paper" alt="Invoice PDF preview, first page" src="data:image/png;base64,${result.image}"><a class="button-link secondary" target="_blank" rel="noopener" href="${s.previewURL}">Open full PDF${result.pages>1?' · '+result.pages+' pages':''}</a>`;
  }catch(e){if(token===s.previewRevision&&s.preview.isConnected&&!s.finished)s.preview.innerHTML=`<div class="preview-placeholder">${esc(e.message)}</div>`;}
 }
 async function mount(options){
  const {doc,type,title,recovery,form,gather}=options;
  await navigate(type==='quote'?'quotes':'invoices');
  const docs=await api('billing/documents');
  const s={...options,key:recovery.key,version:recovery.version,last:JSON.stringify(gather(true)),queue:Promise.resolve(),conflict:recovery.conflict,previewRevision:0,requestKey:recovery.payload?.request_key||('draft-'+crypto.randomUUID())};
  $('#content').innerHTML=`<div class="invoice-workspace-heading"><div><button type="button" class="ghost" id="editor-back">← ${type==='quote'?'Quotes':'Invoices'}</button><h1>${esc(title)}</h1><p id="editor-save-status" role="status">${recovery.payload?'Recovered saved draft':'Changes are saved automatically'}</p></div><div class="actions"><button type="button" class="secondary" id="editor-preview-toggle" aria-expanded="true">Hide preview</button><button type="submit" form="document-form">${doc?.state==='issued'?'Save changes':'Save draft'}</button></div></div><div class="invoice-workspace"><aside class="invoice-switcher"><h2>Recent ${type==='quote'?'quotes':'invoices'}</h2>${docs.filter(d=>d.kind===type).slice(0,12).map(d=>`<button type="button" data-editor-invoice="${d.id}"><span>${esc(d.number)}</span><strong>${esc(d.client.name)}</strong><small>${money(d.total_cents)} · ${esc(Billing.label(d.status))}</small></button>`).join('')||'<p class="muted">Your saved documents will appear here.</p>'}</aside><section class="invoice-edit-sheet" id="editor-sheet"></section><aside class="invoice-live-preview" id="editor-preview"><h2>PDF preview</h2><p class="footnote">Updates as you edit. The preview uses the actual PDF layout.</p><div id="editor-preview-content"></div></aside></div>`;
  form.querySelector('.modal-footer')?.remove();$('#editor-sheet').append(form);$('#modal').close();$('#modal').innerHTML='';
  s.status=$('#editor-save-status');s.preview=$('#editor-preview-content');current=s;
  history.pushState({invoiceEditor:true},'',pageURL(page));
  if(recovery.conflict){const banner=document.createElement('div');banner.className='notice';banner.innerHTML='<p>This invoice changed after your earlier autosave. The current saved invoice is shown.</p><button type="button" class="secondary">Discard outdated autosave</button>';form.prepend(banner);banner.querySelector('button').onclick=async()=>{try{await api('billing/editor-drafts/'+s.key,{version:s.version},'DELETE');s.version=0;s.conflict=false;banner.remove();s.last='';await save(s);}catch(e){toast(e.message);}};}
  const redraw=()=>{clearTimeout(s.previewTimer);s.previewTimer=setTimeout(()=>{if(s.finished||!s.form.isConnected)return;try{preview(s,{...gather(),...(doc?{document_id:doc.id}:{})});}catch(e){s.preview.innerHTML='<p class="preview-placeholder">Complete the dates and line items to see the PDF.</p>';}},650);};
  const changed=()=>{if(s.finished||s.submitting)return;status(s,'Unsaved changes');clearTimeout(s.timer);s.timer=setTimeout(()=>save(s).catch(()=>{}),650);redraw();};
  form.addEventListener('input',changed);form.addEventListener('change',changed);form.addEventListener('click',e=>{if(e.target.closest('#add-line,.remove-line,#due-date-auto'))changed();});
  $('#editor-back').onclick=()=>navigate(type==='quote'?'quotes':'invoices').catch(e=>toast(e.message));
  $('#editor-preview-toggle').onclick=e=>{const box=$('#editor-preview'),hidden=!box.hidden;box.hidden=hidden;$('.invoice-workspace').classList.toggle('preview-hidden',hidden);e.target.textContent=hidden?'Show preview':'Hide preview';e.target.setAttribute('aria-expanded',String(!hidden));};
  document.querySelectorAll('[data-editor-invoice]').forEach(b=>b.onclick=async()=>{try{await leave();const d=await api('billing/documents/'+b.dataset.editorInvoice);if(d.status==='paid'||['void','converted','declined'].includes(d.state)){await navigate(type==='quote'?'quotes':'invoices');await Billing.view(d.id);}else await Billing.edit(d,d.kind);}catch(e){toast(e.message);}});
  redraw();
 }
 async function design(){
  await leave();await navigate('invoices');
  const [settings,choices,saved]=await Promise.all([api('billing/settings'),api('billing/clients'),api('billing/design')]);
  const client=choices.find(c=>!c.archived);
  $('#content').innerHTML=heading('Invoice design','Choose a layout and preview the PDF as you adjust it.','<button id="design-back" class="secondary">Back to invoices</button>')+`<div class="design-workspace"><section id="design-preview" class="invoice-live-preview"><div id="design-preview-content"></div></section><form id="invoice-design-form" class="design-controls"><h2>Layout</h2><div class="design-presets">${[['classic','Classic'],['modern','Modern'],['compact','Compact']].map(([value,label])=>`<label><input type="radio" name="layout" value="${value}" ${saved.layout===value?'checked':''}><span class="design-swatch ${value}"></span>${label}</label>`).join('')}</div>${select('Font','font',[['sans','Clean sans serif'],['serif','Traditional serif']],saved.font)}${field('Brand colour','accent','color',saved.accent||settings.business.accent)}<div class="field"><label for="design-logo">Business logo</label><input id="design-logo" type="file" accept="image/png,image/jpeg,image/webp"></div><p class="footnote">Logo uploads apply to new documents and documents you edit and save.</p><h2>Show on the PDF</h2>${[['show_quantity','Quantity column'],['show_unit','Quantity type'],['show_rate','Rate column'],['show_client_address','Client address'],['show_reference','Reference / purchase order']].map(([key,label])=>`<label class="check"><input type="checkbox" name="${key}" ${saved[key]?'checked':''}>${label}</label>`).join('')}<button type="submit">Save invoice design</button><p class="footnote">Saved invoices keep their existing layout until edited and saved again.</p></form></div>`;
  const form=$('#invoice-design-form'),state={preview:$('#design-preview-content'),previewRevision:0};let timer;
  const values=()=>({...Object.fromEntries(new FormData(form)),...Object.fromEntries(['show_quantity','show_unit','show_rate','show_client_address','show_reference'].map(k=>[k,form.elements[k].checked]))});
  const draw=()=>{if(!client){state.preview.innerHTML='<p class="empty">Add a client to preview your invoice design.</p>';return;}preview(state,{kind:'invoice',client_id:client.id,issue_date:today(),due_date:today(),tax_mode:'none',number:'PREVIEW',notes:settings.defaults.invoice_notes,payment_details:settings.defaults.invoice_payment_details,design:values(),lines:[{description:'Professional services',quantity:2,quantity_type:'Hours',unit_price:150,tax:'none'}]});};
  form.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(draw,450);});form.addEventListener('change',()=>{clearTimeout(timer);timer=setTimeout(draw,450);});
  formHandler('#invoice-design-form',async()=>{await api('billing/design',values(),'PUT');toast('Invoice design saved.');});
  $('#design-logo').onchange=async e=>{if(!e.target.files[0])return;try{const data=new FormData();data.append('file',e.target.files[0]);await api('billing/logo',data);draw();toast('Logo saved.');}catch(error){toast(error.message);}};
  $('#design-back').onclick=()=>{if(state.previewURL)URL.revokeObjectURL(state.previewURL);navigate('invoices');};draw();
 }
 function attachmentHTML(files){return `<section class="email-supporting-files"><h3>Supporting files <span class="muted">optional</span></h3><div id="supporting-file-list">${fileRows(files)}</div><div class="actions"><label class="button-link secondary" for="supporting-upload">Attach files</label><input class="visually-hidden" id="supporting-upload" type="file" multiple accept=".pdf,.jpg,.jpeg,.png"><button type="button" class="ghost" id="attach-saved-receipt">Choose saved receipt</button></div><div id="supporting-receipts"></div><p class="footnote">Only ticked files are included with this email. Up to five files, 20 MB total.</p><p id="supporting-status" role="status"></p></section>`;}
 function fileRows(files,selected=new Set()){return files.map(f=>`<div class="supporting-file"><label class="check"><input type="checkbox" name="supporting_file" value="${f.id}" ${selected.has(f.id)?'checked':''}>${esc(f.filename)} <small>${Math.ceil(f.size/1024)} KB</small></label><button class="ghost" type="button" data-remove-file="${f.id}" aria-label="Remove ${esc(f.filename)}">✕</button></div>`).join('')||'<p class="muted">The invoice PDF is included automatically.</p>';}
 function mountAttachments(doc,initial){
  let files=initial||[];const root=$('.email-supporting-files'),selected=()=>new Set([...root.querySelectorAll('[name=supporting_file]:checked')].map(e=>Number(e.value)));
  function draw(set){root.querySelector('#supporting-file-list').innerHTML=fileRows(files,set);root.querySelectorAll('[data-remove-file]').forEach(b=>b.onclick=async()=>{try{await api(`billing/documents/${doc.id}/attachments/${b.dataset.removeFile}`,{},'DELETE');files=files.filter(f=>f.id!==Number(b.dataset.removeFile));draw(selected());}catch(e){toast(e.message);}});}
  async function upload(data){const form=root.closest('form');form.dataset.attachmentsBusy='true';try{const set=selected(),old=new Set(files.map(f=>f.id));root.querySelector('#supporting-status').textContent='Attaching…';files=await api(`billing/documents/${doc.id}/attachments`,data);files.filter(f=>!old.has(f.id)).forEach(f=>set.add(f.id));draw(set);root.querySelector('#supporting-status').textContent='Attached. Selected files will be sent to the recipient.';}finally{delete form.dataset.attachmentsBusy;}}
  root.querySelector('#supporting-upload').onchange=async e=>{try{for(const file of e.target.files){const data=new FormData();data.append('file',file);await upload(data);}}catch(error){root.querySelector('#supporting-status').textContent=error.message;}finally{e.target.value='';}};
  root.querySelector('#attach-saved-receipt').onclick=async()=>{try{const choices=await api('billing/attachment-receipts');root.querySelector('#supporting-receipts').innerHTML=select('Saved receipt','supporting-receipt',[['','Choose a receipt'],...choices.map(r=>[r.id,r.filename])])+'<button type="button" class="secondary" id="confirm-supporting-receipt">Attach receipt</button>';root.querySelector('#confirm-supporting-receipt').onclick=async()=>{try{const data=new FormData();data.append('receipt_id',root.querySelector('#supporting-receipt').value);await upload(data);root.querySelector('#supporting-receipts').replaceChildren();}catch(e){toast(e.message);}};}catch(e){toast(e.message);}};draw(new Set());
 }
 return {units,active,recover,mount,leave,complete,beforeSubmit,resume,design,attachmentHTML,mountAttachments};
})();
