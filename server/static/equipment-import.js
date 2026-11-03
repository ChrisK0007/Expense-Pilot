'use strict';
const EquipmentImport=(()=>{
 const methods=[['diminishing_value','DV — diminishing value'],['prime_cost','PC — prime cost'],['written_off','Fully written off'],['manual','Manual / pool review']];
 async function open(reload){
  const list=await api('workflows/equipment/imports');modal('Import depreciation schedule',`<p>Upload the accountant’s PDF, image or a CSV. Review the assets before importing. Original cost and the opening balance stay separate; earlier years are not reconstructed.</p><form id="schedule-upload"><div class="field"><label for="schedule-file">Schedule file · up to 10 MB</label><input id="schedule-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.csv" required></div><button type="submit">Read schedule</button> <a class="button-link secondary" href="/api/workflows/equipment/import-template">Download CSV template</a></form><p class="footnote">PDF/image reading uses your configured AI provider. Up to 6 pages and 60 assets per import. CSV is read locally. Replace the example row in the template with your own records.</p>${list.imports.length?'<h3>Saved imports</h3>':''}${list.imports.map(i=>`<p><button class="ghost resume-schedule" data-id="${i.id}">${esc(i.filename)} · ${esc(i.status)}</button></p>`).join('')}`);
  document.querySelectorAll('.resume-schedule').forEach(b=>b.onclick=()=>watch(b.dataset.id,reload).catch(e=>toast(e.message)));
  formHandler('#schedule-upload',async()=>{const fd=new FormData();fd.append('file',$('#schedule-file').files[0]);const r=await api('workflows/equipment/imports',fd);await watch(r.id,reload);});
 }
 async function watch(id,reload){
  const r=await api('workflows/equipment/imports/'+id);
  if(r.status==='review')return review(r,reload);
  modal('Depreciation schedule',`<div id="schedule-reading" data-import="${id}"><p>${esc(r.filename)}</p><p class="${r.status==='failed'?'error':'notice'}">${r.status==='reading'?'Reading the saved original. You can close this window and resume from Equipment.':r.status==='imported'?'This schedule has already been imported. To correct a removed asset, read it again and select only assets not already registered.':esc(r.error||'The original is saved.')}</p><a class="button-link secondary" href="/api/documents/${r.document_id}/download" target="_blank" rel="noopener">View original</a>${r.status!=='reading'?'<button id="retry-schedule" class="secondary">Read again</button>':''}<button id="schedule-list" class="ghost">Back to imports</button></div>`);
  bind('#schedule-list',()=>open(reload));bind('#retry-schedule',async()=>{await api('workflows/equipment/imports/'+id,{},'PUT');watch(id,reload);});
  if(r.status==='reading'){const node=$('#schedule-reading');setTimeout(()=>{if(node.isConnected&&$('#modal').open)watch(id,reload).catch(e=>toast(e.message));},2000);}
 }
 function review(source,reload){
  const data=source.data,rawYear=Number(data.year),validYear=Number.isInteger(rawYear)&&rawYear>=1900&&rawYear<=2098,year=validYear?rawYear:TaxTreatment.financialYear(today());
  modal('Review imported assets',`<form id="schedule-review"><p>${esc(source.filename)} · ${data.rows.length} assets · <a href="/api/documents/${source.document_id}/download" target="_blank" rel="noopener">Original schedule</a></p>${select('Schedule financial year','schedule_year',[['','Choose financial year'],...TaxTreatment.yearOptions(year)],validYear?year:'')}<div id="schedule-rows">${data.rows.map((r,i)=>`<fieldset class="import-row" data-index="${i}"><legend><label class="check"><input type="checkbox" class="include-asset" checked>${esc(r.name||'Asset '+(i+1))}</label></legend><p class="import-summary" aria-live="polite"></p>${select('Treatment','import-choice-'+i,[['source','Keep the schedule’s treatment'],['fully_claimed','Fully claimed this year']])}<details class="equipment-advanced"><summary>Advanced details</summary><div class="grid2">${field('Asset name','import-name-'+i,'text',r.name??'','required maxlength="200"')}${field('Acquired','import-acquired-'+i,'date',r.acquired??'','required')}${[['Original tax cost (AUD)','cost'],['Opening value (AUD)','opening'],['Gross decline (AUD)','decline'],['Closing value (AUD)','closing'],['Annual rate % (PC / DV)','rate'],['Employment use %','work_percent'],['Business use %','business_percent']].map(([label,k])=>field(label,'import-'+k+'-'+i,'number',r[k]??'',`min="0" step="${k.endsWith('percent')?'1':'0.01'}" ${['cost','opening','decline','closing','work_percent','business_percent'].includes(k)?'required':''}`)).join('')}${select('Method','import-method-'+i,methods,r.method||'manual')}</div><p class="footnote">Amounts are AUD before the employment/business split. Original cost and earlier history are preserved. D5 work-related expenses belong under Employment.</p></details><div class="import-purchase">${select('Existing purchase','import-expense_id-'+i,[['','No recorded purchase']])}<label class="check separate-purchase"><input type="checkbox" id="import-separate_purchase-${i}">This is a different purchase</label></div></fieldset>`).join('')}</div><details class="equipment-advanced"><summary>Import notes</summary><p>${esc(data.notes||'Figures are retained from the uploaded schedule.')}</p><p>Only the selected year is recorded. Future depreciation starts from the remaining value. Fully claimed items stay at zero. Your accountant can review the source and calculations.</p></details><p class="footnote">Importing saves the selected AUD figures. Leave out any assets already registered.</p><button type="submit">Import selected assets</button></form>`);
  const form=$('#schedule-review');form.elements.schedule_year.required=true;
  const reveal=el=>{for(let p=el.parentElement;p&&p!==form;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;};
  form.addEventListener('invalid',event=>reveal(event.target),true);
  const updates=[];
  document.querySelectorAll('.import-row').forEach(row=>{
   const i=Number(row.dataset.index),original=data.rows[i],get=k=>row.querySelector('#import-'+k+'-'+i),purchase=get('expense_id'),choice=get('choice');let automatic=false,first=true;
   function update(){
    const selectedYear=Number($('#schedule_year').value),full=choice.value==='fully_claimed';let acquired='';try{acquired=dateValue(get('acquired'));}catch{}
    const purchaseYear=acquired?TaxTreatment.financialYear(acquired):null;
    if(full){
     if(automatic&&purchaseYear!==selectedYear){get('opening').value='';automatic=false;}
     if((automatic||get('opening').value==='')&&purchaseYear===selectedYear){get('opening').value=get('cost').value;automatic=true;}
     get('decline').value=get('opening').value;get('closing').value='0';get('method').value='written_off';get('rate').value='';
    }
    get('decline').readOnly=full;get('closing').readOnly=full;
    const numbers=['cost','opening','decline','closing','work_percent','business_percent'].map(k=>get(k).value),valid=numbers.every(v=>v!==''&&Number.isFinite(Number(v)))&&acquired&&get('name').value;
    const [cost,opening,decline,closing,work,business]=numbers.map(Number),balances=valid&&Math.abs(opening-decline-closing)<0.005&&opening<=cost&&closing>=0&&decline>=0&&work+business<=100;
    const shares=valid?Splits.amounts({amount_cents:Math.round(decline*100),work_percent:work,business_percent:business}):null;
    row.querySelector('.import-summary').textContent=balances?`${money(shares.work+shares.business)} deduction · ${money(Math.round(closing*100))} remaining · ${work}% employment / ${business}% business`:'Some figures need checking. Open Advanced details or choose Fully claimed this year.';
    row.querySelector('.import-summary').classList.toggle('muted',!!balances);
    if(first&&!balances)row.querySelector('details').open=true;
    const matches=E.filter(e=>e.date===acquired&&e.amount_cents===Math.round(cost*100)),usable=matches.filter(e=>!e.equipment_id&&!e.reimbursed&&!e.meal&&!e.trip_id&&!e.vehicle_id&&e.category!=='Meals'&&JSON.parse(e.items_json||'[]').length===0&&e.work_percent===work&&e.business_percent===business),previous=purchase.value;
    purchase.innerHTML='<option value="">Choose a purchase / link later</option>'+usable.map(e=>`<option value="${e.id}">${esc(e.merchant+' · '+dateAU(e.date)+' · '+money(e.amount_cents))}</option>`).join('');
    purchase.value=usable.some(e=>String(e.id)===previous)?previous:(first&&usable.length===1?String(usable[0].id):'');
    row.querySelector('.import-purchase').hidden=!matches.length;row.querySelector('.separate-purchase').hidden=!!purchase.value;
    first=false;
   }
   choice.onchange=()=>{if(choice.value==='source'){for(const k of ['opening','decline','closing','method','rate'])get(k).value=original[k]??'';automatic=false;}update();if(choice.value==='fully_claimed'&&get('opening').value!=='')row.querySelector('details').open=false;};
   get('opening').addEventListener('input',()=>automatic=false);
   row.addEventListener('input',event=>{if(!event.target.classList.contains('include-asset'))update();});
   row.addEventListener('change',event=>{if(event.target!==choice&&!event.target.classList.contains('include-asset'))update();});
   row.querySelector('.include-asset').onchange=event=>row.querySelectorAll('.field input,.field select,.separate-purchase input').forEach(input=>input.disabled=!event.target.checked);
   update();updates.push(update);
  });
  $('#schedule_year').onchange=()=>updates.forEach(update=>update());
  formHandler('#schedule-review',async d=>{
   const entries=[...document.querySelectorAll('.import-row')].filter(row=>row.querySelector('.include-asset').checked).map(row=>{const i=row.dataset.index;return {...Object.fromEntries(['name','acquired','cost','opening','decline','closing','rate','work_percent','business_percent','method','expense_id'].map(k=>{const el=row.querySelector('#import-'+k+'-'+i);return [k,k==='acquired'?dateValue(el):el.value];})),fully_claimed:row.querySelector('#import-choice-'+i).value==='fully_claimed',separate_purchase:row.querySelector('#import-separate_purchase-'+i).checked};});
   try{await api('workflows/equipment/imports/'+source.id+'/commit',{version:source.version,year:Number(d.schedule_year),rows:entries,confirmed:true,aud_confirmed:true});}catch(e){form.querySelectorAll('.import-row').forEach(row=>{if(row.querySelector('.include-asset').checked)row.querySelector('details').open=true;});throw e;}
   $('#modal').close();await reload();toast('Depreciation schedule imported.');
  });
 }
 return {open};
})();
