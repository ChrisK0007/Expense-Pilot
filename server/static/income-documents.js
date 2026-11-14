'use strict';
const IncomeDocuments=(()=>{
 const kinds=[['expense','Expense'],['home_office','Home-office bill evidence'],['payslip','Payslip'],['income_statement','Annual income statement']];
 const typeField=kind=>select('File as','document_kind',kinds,kind||'expense');
 const fiscalYear=date=>Number(date.slice(0,4))-(date.slice(5,7)<'07');
 const financialYearHint='<p class="footnote" data-payment-year role="status"></p>';
 function bindPaymentYear(form,annual=()=>false){
  const hint=form.querySelector('[data-payment-year]');
  const field=key=>{try{return dateValue(form.elements[key]);}catch{return '';}};
  const show=()=>{
   const date=field('date'),start=field('period_start'),end=field('period_end');
   if(annual()){hint.textContent='';return;}
   const crossing=start&&end&&start<=end&&fiscalYear(start)!==fiscalYear(end);
   const year=date?fiscalYear(date):null;
   hint.textContent=(year===null?'Enter the payment date to assign the financial year.':`This payment counts toward FY ${year}–${String(year+1).slice(-2)}.`)
    +(crossing?' This pay period crosses 30 June. Check Date paid on the original payslip. Gross pay and PAYG go into the payment year.':'');
  };
  form.addEventListener('input',show);
  form.addEventListener('change',show);
  show();
 }
 async function review(r,options){
  const d={...r.extraction,...r.draft},kind=d.document_kind==='income_statement'?'income_statement':'payslip',annual=kind==='income_statement';
  const records=await api('employment');
  if(!options.isCurrent())return;
  options.mount('Review employment document',`<form id="income-document-form"><div class="receipt-review-layout"><div class="receipt-preview">${Receipts.inlinePreview(r,'Original employment document')}<button type="button" class="secondary" id="income-original">View full document</button><button type="button" class="secondary" data-evidence="${esc(r.id)}">Check extracted evidence</button><p class="footnote">${esc(r.filename)}</p><button type="button" class="secondary" id="income-read" ${S.ai_configured||r.mime==='application/pdf'?'':'disabled'}>Read document again</button><p class="footnote">${S.ai_configured?'Clear text payslips are read locally; other layouts use your configured AI provider.':'Supported text payslips are read locally. Other layouts can be entered manually.'}</p></div><div>${typeField(kind)}${d.extraction_warning?`<p class="notice" role="status">${esc(d.extraction_warning)}</p>`:d.extraction_method==='local labels'?'<p class="footnote">Read directly from document text. Check all figures against the original.</p>':''}${d.extraction_note?`<p class="notice">${esc(d.extraction_note)}</p>`:''}<div class="notice">${annual?'Use the annual taxable gross and PAYG totals for the stated financial year. Existing payslips for the same pay must be reviewed first.':'Use this payment’s gross taxable pay and PAYG withholding. Year-to-date totals are not added as another payment.'} Employer super is excluded from gross pay.</div>${d.ytd_gross!=null||d.ytd_withheld!=null?`<p class="footnote">Year-to-date reference only: gross ${d.ytd_gross!=null?money(Math.round(d.ytd_gross*100)):'not read'} · tax ${d.ytd_withheld!=null?money(Math.round(d.ytd_withheld*100)):'not read'}. These figures are not saved as this payment.</p>`:''}${d.amounts_basis==='unknown'?'<p class="notice">The payment totals could not be distinguished reliably. Enter them from the original.</p>':''}<div class="grid2">${field('Employer','employer','text',d.employer||'','required maxlength="200"')}${field(annual?'Financial year ending (30 June)':'Payment date','date','date',d.date||'','required')}${field('Gross taxable pay (AUD)','gross','number',d.gross??'','required min="0" step="0.01"')}${field('PAYG tax withheld (AUD)','withheld','number',d.withheld??'','required min="0" step="0.01"')}${field('Pay period start (optional)','period_start','date',d.period_start||'')}${field('Pay period end (optional)','period_end','date',d.period_end||'')}</div>${financialYearHint}${d.currency&&d.currency!=='AUD'?`<p class="notice">The original is marked ${esc(d.currency)}. Enter the actual AUD taxable pay and withholding; no currency conversion is performed.</p>`:''}${!annual?field('Printed annual base salary (optional)','annual_base_salary','number',d.annual_base_salary??'','min="0.01" step="0.01"')+'<p class="footnote">Enter this only if your payslip states an annual base salary. It can suggest an overnight salary band.</p>':''}${field('Notes (optional)','notes','text',d.notes||'','maxlength="2000"')}<div id="income-existing"></div><label class="check"><input type="checkbox" id="income-reviewed" required>I checked the original: these AUD figures are ${annual?'the annual totals for this tax year':'for this payment, not year-to-date totals'}.</label><p class="footnote">Nothing affects income or the forecast until you save. The original remains available from Employment income.</p></div></div><div class="modal-footer"><button type="button" class="danger" id="income-delete-draft">Delete document</button><button type="button" class="secondary" id="income-save-draft">Save changes</button><button type="submit">Save employment income</button>${options.showNext?'<button type="submit" id="save-income-next">Save &amp; next</button>':''}</div></form>`);
  const form=$('#income-document-form');
  bindPaymentYear(form,()=>annual);
  const gather=()=>{const x=formData(form);return {document_kind:x.document_kind,employer:x.employer,date:x.date,gross:x.gross,withheld:x.withheld,period_start:x.period_start,period_end:x.period_end,notes:x.notes,...(x.annual_base_salary===undefined?{}:{annual_base_salary:x.annual_base_salary})};};
  const existing=()=>{
   const v=gather(),matching=records.filter(x=>!x.receipt_id&&x.employer===v.employer&&x.date===v.date&&x.gross_cents===Math.round(Number(v.gross)*100)&&x.withheld_cents===Math.round(Number(v.withheld)*100));
   $('#income-existing').innerHTML=matching.length?`<div class="notice">These figures already exist. Attach this original to the existing income record to avoid counting it twice.${select('Existing income record','existing_income_id',[['','Choose the existing record'],...matching.map(x=>[x.id,`${x.employer} · ${dateAU(x.date)} · ${money(x.gross_cents)}`])])}</div>`:'';
  };
  for(const key of ['employer','date','gross','withheld'])form.elements[key].addEventListener('change',existing);
  existing();
  bind('#income-original',()=>Receipts.preview(r.id));
  bind('#income-delete-draft',()=>options.run(async()=>{if(!confirm('Permanently delete this unfiled document?'))return;try{await api('receipts/'+r.id,{},'DELETE');$('#modal').close();await Receipts.reload();}catch(e){toast(e.message);}}));
  $('#document_kind').onchange=()=>options.run(async()=>{try{await api('receipts/'+r.id+'/draft',gather(),'PUT');await Receipts.reopen(r.id);}catch(e){toast(e.message);}});
  bind('#income-save-draft',()=>options.run(async()=>{try{await api('receipts/'+r.id+'/draft',gather(),'PUT');$('#modal').close();await Receipts.reload();toast('Inbox changes saved.');}catch(e){toast(e.message);}}));
  bind('#income-read',async ev=>{const button=ev.currentTarget;button.disabled=true;try{await readDocument(r.id);if(options.isCurrent())await Receipts.reopen(r.id);}catch(e){toast(e.message);if(button.isConnected)button.disabled=false;}});
  formHandler('#income-document-form',async(_values,_form,submitter)=>{
   const v=gather();await api('receipts/'+r.id+'/income',{...v,record_kind:v.document_kind,currency:'AUD',reviewed:$('#income-reviewed').checked,existing_income_id:Number($('#existing_income_id')?.value)||null});
   await options.afterSave(submitter?.id==='save-income-next','Employment income saved. Original available in Employment income.');
  });
 }
 return {review,typeField,financialYearHint,bindPaymentYear};
})();
