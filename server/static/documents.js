'use strict';
const Documents=(()=>{
 let records=[],categories={},revision=0,search='',category='all',year='all';
 const fy=y=>y==null?'Unassigned':`FY ${y}–${String(Number(y)+1).slice(-2)}`;
 const size=n=>n<1024*1024?`${Math.ceil(n/1024)} KB`:`${(n/1024/1024).toFixed(1)} MB`;
 async function show(){
  const token=++revision;
  $('#content').innerHTML=heading('Documents','Tax-time records that are separate from expenses and deductions.')+'<p>Loading documents…</p>';
  try{const d=await api('documents');if(page!=='documents'||revision!==token)return;records=d.documents;categories=d.categories;render();}
  catch(e){if(page==='documents'&&revision===token)$('#content').innerHTML=heading('Documents','')+`<p class="error">${esc(e.message)}</p><button id="documents-retry">Retry</button>`;bind('#documents-retry',show);}
 }
 function render(){
  const years=[...new Set(records.filter(d=>d.year!=null).map(d=>d.year))].sort((a,b)=>b-a);
  $('#content').innerHTML=heading('Documents','Tax returns, health statements and other records for tax time.',editor()?'<button id="document-add">+ Upload document</button>':'<span class="pill">Read only</span>')+`<p class="home-office-note">Stored separately from receipts and expenses. These documents do not add income or deductions.</p><div class="toolbar trip-filters"><div class="field"><label for="document-search">Search documents</label><input id="document-search" value="${esc(search)}" placeholder="Title, filename or notes…"></div>${select('Category','document-category',[['all','All categories'],...Object.entries(categories)],category)}${select('Financial year','document-year',[['all','All financial years'],['unassigned','Unassigned'],...years.map(y=>[y,fy(y)])],year)}</div><p id="document-count" class="muted" aria-live="polite"></p><div id="document-results"></div>`;
  bind('#document-add',()=>edit());$('#document-search').oninput=e=>{search=e.target.value;draw();};$('#document-category').onchange=e=>{category=e.target.value;draw();};$('#document-year').onchange=e=>{year=e.target.value;draw();};draw();
 }
 function draw(){
  const q=search.trim().toLowerCase(),items=records.filter(d=>(category==='all'||d.category===category)&&(year==='all'||(year==='unassigned'?d.year==null:String(d.year)===year))&&[d.title,d.filename,d.notes].join(' ').toLowerCase().includes(q));
  $('#document-count').textContent=`${items.length} ${items.length===1?'document':'documents'}${items.length!==records.length?` of ${records.length}`:''}`;
  $('#document-results').innerHTML=items.length?`<div class="grid3">${items.map(d=>`<section class="card document-card"><span class="pill">${esc(categories[d.category])}</span><h2>${esc(d.title)}</h2><p class="muted">${fy(d.year)} · ${size(d.size_bytes)}</p><p class="document-filename">${esc(d.filename)}</p>${d.notes?`<details><summary>Notes</summary><p class="document-notes">${esc(d.notes)}</p></details>`:''}<p class="footnote">Uploaded ${esc(WorkspaceTime.stamp(d.created_at+'Z'))}${d.uploaded_by_name?' by '+esc(d.uploaded_by_name):''}</p><div class="settings-options"><a class="button-link secondary" href="/api/documents/${d.id}/download">Download</a>${editor()?`<button class="ghost document-edit" data-id="${d.id}">Edit details</button>`:''}</div></section>`).join('')}</div>`:'<section class="panel empty"><h2>No documents found</h2><p>Upload a tax return, private health statement or other supporting document, or adjust the filters.</p></section>';
  document.querySelectorAll('.document-edit').forEach(b=>b.onclick=()=>edit(records.find(d=>d.id===b.dataset.id)));
 }
 function edit(d){
  const current=Number(today().slice(0,4))-(Number(today().slice(5,7))<7?1:0);
  const years=Array.from({length:current-1899},(_,i)=>current-i);
  if(d?.year!=null&&!years.includes(d.year))years.unshift(d.year);
  modal(d?'Edit document details':'Upload a document',`<form id="document-form">${!d?'<div class="field"><label for="document-file">Document file</label><input id="document-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,.xlsx,.csv,.txt" required><small>PDF, images, Word, Excel, CSV or text · up to 10 MB. Original files are stored without AI processing. Password-protected PDFs can be stored and downloaded.</small></div>':`<p class="muted">Original file: ${esc(d.filename)}</p>`}${field('Title','title','text',d?.title||'','required maxlength="200"')}<div class="grid2">${select('Document category','category',Object.entries(categories),d?.category||'other')}${select('Document financial year','year',[['','Unassigned'],...years.map(y=>[y,fy(y)])],d?.year??'')}</div><div class="field"><label for="document-notes">Notes (optional)</label><textarea id="document-notes" name="notes" maxlength="3000" placeholder="For example, the insurer, tax year or reason to keep this document">${esc(d?.notes||'')}</textarea></div><div class="modal-footer">${d?'<button type="button" class="danger" id="document-delete">Delete document</button>':''}<button type="submit">${d?'Save details':'Upload document'}</button></div></form>`);
  if(!d)$('#document-file').onchange=()=>{const file=$('#document-file').files[0];if(file&&!$('#document-form [name=title]').value)$('#document-form [name=title]').value=file.name.replace(/\.[^.]+$/,'');};
  formHandler('#document-form',async p=>{
   let result;
   if(d)result=await api('documents/'+d.id,{...p,version:d.version},'PUT');
   else{const file=$('#document-file').files[0];if(!file||file.size>10*1024*1024)throw Error('Choose a document no larger than 10 MB.');const fd=new FormData();for(const [key,value] of Object.entries(p))fd.append(key,value);fd.append('file',file);result=await api('documents',fd);}
   $('#modal').close();search='';category='all';year='all';await show();toast(result.duplicate?'This file is already saved. Its existing details were kept.':d?'Document details saved.':'Document uploaded.');
  });
  bind('#document-delete',async()=>{if(!confirm('Permanently delete this document and its original file? Existing backups are not changed.'))return;try{await api('documents/'+d.id,{version:d.version},'DELETE');$('#modal').close();await show();toast('Document deleted.');}catch(e){toast(e.message);}});
 }
 return {page:show};
})();
