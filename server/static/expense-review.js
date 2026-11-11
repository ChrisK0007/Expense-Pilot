'use strict';
const ExpenseReview=(()=>{
 const year=()=>TaxTreatment.financialYear(today());
 let recurringYear=null;
 const table=(heads,rows)=>rows.length?`<div class="table-wrap"><table><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<p class="empty">No records to show.</p>';
 const action=(label,kind,i)=>`<button type="button" class="secondary" data-review-action="${kind}" data-index="${i}">${label}</button>`;
 function actions(root,handlers){
  root.querySelectorAll('[data-review-action]').forEach(b=>b.onclick=async()=>{
   b.disabled=true;
   try{await handlers[b.dataset.reviewAction](Number(b.dataset.index));}
   catch(error){toast(error.message);}
   finally{if(b.isConnected)b.disabled=false;}
  });
 }
 async function recurring(){
  const y=recurringYear??year();
  $('#content').innerHTML=heading('Recurring expenses','Review expected payments and match them to posted bank charges.',bookkeeper()?'<button id="recurring-add">+ New schedule</button>':'')+
   Workflows.links('expenses')+`<div class="toolbar">${select('Financial year','recurring-year',fyOptions().filter(([v])=>v!=='all'),y)}</div><div id="recurring-content">Loading…</div>`;
  bind('#manage-expense-categories',()=>Tracking.categories());
  const root=$('#recurring-content');
  $('#recurring-year').onchange=e=>{recurringYear=Number(e.target.value);recurring().catch(e=>toast(e.message));};
  bind('#recurring-add',()=>schedule());
  try{
   const data=await api('recurring-expenses?year='+y);
   if(!root.isConnected)return;
   root.innerHTML=`<section class="panel"><div class="panel-header"><h2>Due payments</h2></div>${table(['Expense','Due','Expected','Bank charges',''],data.pending.map((d,i)=>[
     esc(d.merchant),dateAU(d.due_date),money(d.expected_cents),d.matches.length===1?`${money(-d.matches[0].amount_cents)}${-d.matches[0].amount_cents!==d.expected_cents?' · Amount changed':''}`:d.matches.length?`${d.matches.length} possible matches`:'Awaiting charge',
     bookkeeper()?(d.matches.length?action('Review','match',i):'')+action('Skip','skip',i):'',
   ]))}</section>
   <section class="panel"><div class="panel-header"><h2>Schedules</h2></div>${table(['Expense','Repeat','First due','Expected','Status',''],data.rules.map((r,i)=>[
    esc(r.merchant),esc(r.interval),dateAU(r.start),money(r.amount_cents),r.active?'Active':'Paused',bookkeeper()?action('Edit','edit',i):'',
   ]))}</section>
   <section class="panel"><div class="panel-header"><h2>Reviewed payments</h2></div>${table(['Due','Record','Amount'],data.settled.map(r=>[
    dateAU(r.due_date),r.expense_id?esc(r.merchant):r.bank_id?'Expense removed':'Skipped',r.expense_id?money(r.amount_cents):'—',
   ]))}</section>`;
   actions(root,{edit:i=>schedule(data.rules[i]),match:i=>chooseCharge(data.pending[i]),skip:async i=>{
    const d=data.pending[i];if(!confirm('Skip this occurrence? The schedule will continue.'))return;
    await api(recurringPath(d,'skip'),{});await recurring();
   }});
  }catch(error){if(root.isConnected)root.textContent=error.message;}
 }
 function schedule(r={}){
  if(!A.length){toast('Add a bank account label first.');return;}
  const categories=(S.categories||[]).filter(c=>c!=='Meals');
  modal(r.id?'Edit recurring expense':'New recurring expense',`<form id="recurring-form">
   <div class="grid2">${field('Merchant','merchant','text',r.merchant||'','required maxlength="200"')}
   ${field('Expected amount (AUD)','amount','number',r.amount_cents==null?'':(r.amount_cents/100).toFixed(2),'required min="0.01" step="0.01"')}
   ${field('First due date','start','date',r.start||today(),'required')}
   ${select('Repeat','interval',['weekly','fortnightly','monthly','quarterly','yearly'].map(x=>[x,x[0].toUpperCase()+x.slice(1)]),r.interval||'monthly')}
   ${select('Category','category',categories.map(c=>[c,categoryLabel(c)]),r.category||'Other')}
   ${select('Bank account','account_id',A.map(a=>[a.id,a.name]),r.account_id)}
   ${field('Employment (%)','work_percent','number',r.work_percent??0,'required min="0" max="100" step="1"')}
   ${field('Business (%)','business_percent','number',r.business_percent??0,'required min="0" max="100" step="1"')}</div>
   <p class="footnote">The remaining share is personal. A draft stays outside Expenses until you review a posted charge.</p>
   <label class="check"><input type="checkbox" name="active" ${r.active===0?'':'checked'}> Active schedule</label>
   <div class="modal-footer"><button type="submit">Save schedule</button></div></form>`);
  formHandler('#recurring-form',async(d,f)=>{
   await api('recurring-expenses'+(r.id?'/'+r.id:''),{...d,active:f.elements.active.checked,version:r.version},r.id?'PUT':'POST');
   $('#modal').close();await recurring();toast('Schedule saved.');
  });
 }
 const recurringPath=(d,verb)=>`recurring-expenses/${d.rule_id}/${d.due_date}/${verb}`;
 async function chooseCharge(d){
  modal('Review recurring payment',`<form id="recurring-charge">
   ${select('Posted bank charge','bank_id',d.matches.map(b=>[b.id,`${dateAU(b.date)} · ${b.payee} · ${money(-b.amount_cents)} · ${b.account_name}`]))}
   <div class="modal-footer"><button type="submit">Review match</button></div></form>`);
  formHandler('#recurring-charge',async p=>{
   const bank_id=Number(p.bank_id);
   const result=await api(recurringPath(d,'preview'),{bank_id});
   const total=-result.bank.amount_cents;
   modal('Confirm recurring payment',`<form id="recurring-match">
    <p>Expected ${money(d.expected_cents)} · Posted ${money(total)}${total!==d.expected_cents?' · Amount changed':''}</p>
    ${result.expenses.length?select('Existing expense','expense_id',result.expenses.map(e=>[e.id,`${dateAU(e.date)} · ${e.merchant} · ${money(e.amount_cents)}`])):'<p>A new expense will be saved for review.</p>'}
    <div class="modal-footer"><button type="submit">Confirm match</button></div></form>`);
   formHandler('#recurring-match',async x=>{
    await api(recurringPath(d,'apply'),{bank_id,expense_id:x.expense_id?Number(x.expense_id):null,token:result.token});
    $('#modal').close();await refresh();await recurring();toast('Recurring payment matched.');
   });
  });
 }
 async function transfers(){
  $('#content').innerHTML=heading('Transfers','Match money moved between accounts or paid to a credit card.')+Workflows.bankLinks()+'<div id="transfer-content">Loading…</div>';
  const root=$('#transfer-content');
  try{
   const data=await api('bank-transfers');
   if(!root.isConnected)return;
   const debits=data.candidates.filter(d=>d.amount_cents<0);
   const credits=data.candidates.filter(d=>d.amount_cents>0);
   const display=d=>`${dateAU(d.date)} · ${d.account_name} · ${d.payee} · ${money(d.amount_cents)}`;
   const available=bookkeeper()&&debits.length&&credits.length;
   root.innerHTML=`<section class="card"><h2>Pair a transfer</h2>${available?`<form id="transfer-form"><div class="grid2">
    ${select('Money out','transfer_debit',[['','Choose a debit'],...debits.map(d=>[d.id,display(d)])])}
    ${select('Money in','transfer_credit',[['','Choose a debit first']])}</div><p class="footnote">Both sides must be posted for the same AUD amount on different accounts.</p><button type="submit" disabled>Pair transfer</button></form>`:'<p>No unpaired debit and credit records are available to match.</p>'}</section>
    <section class="panel"><div class="panel-header"><h2>Paired transfers</h2></div>${table(['From','To','Amount','Status',''],data.pairs.map((p,i)=>[
    esc(p.debit_account)+' · '+dateAU(p.debit_date),esc(p.credit_account)+' · '+dateAU(p.credit_date),money(p.amount_cents),
    p.needs_review?'Bank record changed':'Paired',bookkeeper()?action('Unpair','undo',i):'',
   ]))}</section>`;
   const form=$('#transfer-form');
   if(form){
    const out=$('#transfer_debit'),incoming=$('#transfer_credit'),submit=form.querySelector('button');
    out.onchange=()=>{
     const debit=debits.find(x=>String(x.id)===out.value);
     const choices=debit?credits.filter(c=>c.amount_cents===-debit.amount_cents&&c.feed_account_id!==debit.feed_account_id):[];
     incoming.innerHTML=`<option value="">${choices.length?'Choose matching credit':'No equal credit available'}</option>`+choices.map(c=>`<option value="${c.id}">${esc(display(c))}</option>`).join('');
     if(choices.length===1)incoming.value=String(choices[0].id);
     submit.disabled=!incoming.value;
    };
    incoming.onchange=()=>{submit.disabled=!incoming.value;};
    formHandler('#transfer-form',async()=>{
     const debit=debits.find(x=>String(x.id)===out.value),credit=credits.find(x=>String(x.id)===incoming.value);
     if(!debit||!credit)throw Error('Choose a debit and its matching credit.');
     await api('bank-transfers',{debit_id:debit.id,credit_id:credit.id,debit_version:debit.version,credit_version:credit.version});
     await transfers();toast('Transfer paired.');
    });
   }
   actions(root,{undo:async i=>{if(!confirm('Unpair these transactions?'))return;await api('bank-transfers/'+data.pairs[i].id,{},'DELETE');await transfers();toast('Transfer unpaired.');}});
  }catch(error){if(root.isConnected)root.textContent=error.message;}
 }
 async function markBillable(e){
  const d=await api(`expenses/${e.id}/billable`);
  if(d.link?.document_id){
   modal('Billable expense',`<p>Linked to invoice ${esc(d.link.number)}.</p><a href="#/invoices">Open invoices</a>`);
   return;
  }
  if(!d.available&&!d.link){toast('Review this expense and save a business allocation before billing it.');return;}
  modal('Billable expense',`<form id="billable-expense-form"><p>${esc(e.merchant)} · ${money(e.amount_cents)}</p>
   ${select('Client','billable_client',[['','Do not bill'],...d.clients.map(c=>[c.id,c.name])],d.link?.client_id||'')}
   <div class="modal-footer"><button type="submit">Save billable expense</button></div></form>`);
  formHandler('#billable-expense-form',async data=>{
   await api(`expenses/${e.id}/billable`,{client_id:data.billable_client?Number(data.billable_client):null},'PUT');
   $('#modal').close();toast('Billable expense updated.');
  });
 }
 async function handover(root,y){
  const path=`workflows/handover/${y}`;
  const d=await api(path+'/review');
  if(!root.isConnected)return;
  const labels={salary_cents:'Recorded employment income',withheld_cents:'Recorded PAYG withheld',
    business_income_cents:'Recorded business income',business_deductions_cents:'Business deductions in forecast',
    work_deductions_cents:'Employment deductions in forecast',overnight_work_cents:'Recorded employment overnights',
    overnight_business_cents:'Recorded business overnights'};
  root.innerHTML=`<h2>Annual handover</h2><p>Download your financial-year registers, outstanding review items and original evidence.</p>
   <div class="actions"><a class="button-link secondary" href="/api/${path}">Download annual handover</a></div>
   <h3>Reviewed figures</h3><p>${d.revision?`Revision ${d.revision} · ${d.changes.length?'Recorded amounts have changed':'Recorded amounts match'}`:'Save the figures reviewed by your tax agent.'}</p>
   ${d.changes.length?table(['Amount','Last reviewed','Current'],d.changes.map(c=>[esc(labels[c.key]||c.key),money(c.before),money(c.after)])):
    table(['Recorded amount','Current'],Object.entries(d.current).map(([key,v])=>[esc(labels[key]||key),money(v)]))}
   ${bookkeeper()&&(!d.revision||d.changes.length)?`<form id="handover-review-form">${field('Reviewed by or reason for revision','note','text','','required maxlength="500"')}<button type="submit">${d.revision?'Save revised figures':'Finalise reviewed figures'}</button></form>`:''}
   ${d.history.length?`<h3>Revision history</h3>${table(['Revision','Saved','Review note'],d.history.map(r=>[r.revision,esc(r.created_at),esc(r.note)]))}`:''}`;
  if($('#handover-review-form'))formHandler('#handover-review-form',async p=>{
   await api(path+'/review',{note:p.note,token:d.token});
   await handover(root,y);toast('Reviewed figures saved.');
  });
 }
 return {recurring,transfers,markBillable,handover};
})();
