'use strict';
const BillingMail=(()=>{
  const area=(label,name,value,max=10000)=>`<div class="field"><label for="${name}">${esc(label)}</label><textarea id="${name}" name="${name}" maxlength="${max}" required>${esc(value)}</textarea></div>`;
  const check=(name,label,checked)=>`<label class="check"><input type="checkbox" id="${name}" name="${name}" ${checked?'checked':''}>${esc(label)}</label>`;
  const run=async fn=>{try{await fn();}catch(error){toast(error.message);}};
  const on=(selector,fn)=>document.querySelectorAll(selector).forEach(el=>el.onclick=async()=>{el.disabled=true;try{await fn(el);}catch(error){toast(error.message);}finally{el.disabled=false;}});
  const tabs={invoices:['Invoices',['invoice']],quotes:['Quotes',['quote']],reminders:['Reminders',['reminder_due','reminder_overdue','reminder_manual']],receipts:['Receipts',['receipt_partial','receipt_full']],statements:['Statements',['statement_all','statement_outstanding']],signature:['Signature',[]]};
  const titles={invoice:'Invoice',quote:'Quote',reminder_due:'Auto reminder before the invoice is due',reminder_overdue:'Auto overdue invoice reminder',reminder_manual:'Manually sending a reminder',receipt_partial:'Partial payment receipt',receipt_full:'Paid in full receipt',statement_all:'All invoices and payments statement',statement_outstanding:'Outstanding invoices statement'};
  const examples={client:'Alex Taylor',business:'Example Flight Testing',full_name:'Chris Taylor',number:'INV-0001',kind:'invoice',total:'$1,100.00',balance:'$600.00',latest_payment:'$500.00',due_date:'23/10/2026',date_range:'01/07/2026 to 09/10/2026'};
  function mountSignature(el,html){
    // Only server-sanitised HTML reaches here. Apply permitted formatting through DOM styles under the app CSP.
    el.innerHTML=html;
    el.querySelectorAll('[style]').forEach(node=>{const styles=node.getAttribute('style');node.removeAttribute('style');for(const item of styles.split(';')){const [key,value]=item.split(':');if(key&&value)node.style.setProperty(key,value);}});
  }
  function signaturePreview(draft){
    return draft.signature_html?`${check('include_signature','Include email signature',true)}<div class="email-signature-preview" id="compose-signature"></div>`:'';
  }
  function bindSignaturePreview(draft){
    if(!draft.signature_html)return;
    mountSignature($('#compose-signature'),draft.signature_html);
    $('#include_signature').onchange=e=>$('#compose-signature').hidden=!e.target.checked;
  }
  async function templates(initial='invoices'){
    if(!owner())return;
    const data=await api('billing/email-templates');
    let selected=initial,lastField=null;
    const capture=()=>{
      document.querySelectorAll('[data-template]').forEach(section=>{const key=section.dataset.template;data.templates[key]={subject:section.querySelector('input').value,body:section.querySelector('textarea').value};});
      if($('#signature-editor'))data.signature_html=$('#signature-editor').innerHTML;
    };
    const draw=()=>{
      const keys=tabs[selected][1];
      modal('Email templates',`<p class="muted">Set the default message for each email sent to your clients.</p><div class="email-template-tabs" role="tablist" aria-label="Email template types">${Object.entries(tabs).map(([key,[label]])=>`<button type="button" role="tab" aria-selected="${key===selected}" aria-controls="email-template-panel" data-template-tab="${key}" class="${key===selected?'active':''}">${label}</button>`).join('')}</div><form id="email-template-form"><div id="email-template-panel" role="tabpanel">${selected==='signature'?signatureEditorMarkup():keys.map(key=>`<section data-template="${key}" class="email-template-section"><h3>${titles[key]}</h3>${key==='reminder_due'?'<p class="muted">Used for automatic reminders before and on the due date.</p>':key==='reminder_overdue'?'<p class="muted">Used for automatic reminders after the due date.</p>':''}${field(titles[key]+' subject',key+'_subject','text',data.templates[key].subject,'required maxlength="200"')}${area(titles[key]+' email body',key+'_body',data.templates[key].body)}<div class="template-fields" aria-label="Insert fields into ${titles[key]}"><span>Insert field:</span>${data.template_fields[key].filter(token=>token!=='kind').map(token=>`<button type="button" class="template-token" data-insert-field="${token}" data-for-template="${key}">${esc(token==='number'?(key==='quote'?'Quote number':'Invoice number'):token==='total'?(key==='quote'?'Quote amount':'Invoice amount'):data.fields[token])}</button>`).join('')}</div><details class="template-example"><summary>Preview with sample details</summary><strong id="${key}_preview_subject"></strong><p class="preserve-lines" id="${key}_preview_body"></p></details></section>`).join('')}</div><div class="modal-footer"><button type="submit">Save email templates</button>${selected!=='signature'?'<button type="button" class="secondary" id="reset-email-template">Use default wording</button>':''}</div><p class="footnote">Your full name comes from the owner’s profile. The signature is appended separately. Changes apply to new email previews.</p></form>${selected==='reminders'?'<button class="secondary" id="open-reminder-settings">Automatic reminder schedule →</button>':''}`);
      $('#modal').classList.add('billing-dialog');
      on('[data-template-tab]',b=>{capture();selected=b.dataset.templateTab;draw();});
      document.querySelectorAll('[role=tab]').forEach(button=>button.onkeydown=event=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
        event.preventDefault();const keys=Object.keys(tabs),at=keys.indexOf(selected);capture();selected=keys[event.key==='Home'?0:event.key==='End'?keys.length-1:(at+(event.key==='ArrowRight'?1:keys.length-1))%keys.length];draw();$(`[data-template-tab="${selected}"]`).focus();
      });
      const preview=key=>{
        const value={...examples,number:key==='quote'?'QUO-0001':examples.number,kind:key==='quote'?'quote':'invoice'};
        for(const field of ['subject','body'])$('#'+key+'_preview_'+field).textContent=$('#'+key+'_'+field).value.replace(/\{([a-z_]+)\}/g,(tag,token)=>value[token]??tag);
      };
      document.querySelectorAll('[data-template] input,[data-template] textarea').forEach(el=>{el.onfocus=()=>lastField=el;el.oninput=()=>preview(el.closest('[data-template]').dataset.template);});
      on('[data-insert-field]',b=>{const key=b.dataset.forTemplate,el=lastField?.isConnected&&lastField.closest('[data-template]')?.dataset.template===key?lastField:$('#'+key+'_body');el.setRangeText('{'+b.dataset.insertField+'}',el.selectionStart??el.value.length,el.selectionEnd??el.value.length,'end');el.focus();preview(key);});
      keys.forEach(preview);
      on('#reset-email-template',()=>{for(const key of keys)data.templates[key]={...data.defaults[key]};draw();toast('Default wording restored. Save to apply it.');});
      on('#open-reminder-settings',async()=>{capture();await save();await reminders();});
      if(selected==='signature')bindSignatureEditor(data.signature_html);
      const save=async()=>{capture();const result=await api('billing/email-templates',{templates:data.templates,signature_html:data.signature_html},'PUT');data.signature_html=result.signature_html;data.templates=result.templates;toast('Email templates saved.');};
      formHandler('#email-template-form',async()=>{await save();draw();});
    };
    draw();
  }
  function signatureEditorMarkup(){
    return `<h3>Email signature</h3><div class="signature-toolbar" role="toolbar" aria-label="Signature formatting">${[['bold','Bold'],['italic','Italic'],['underline','Underline']].map(([cmd,label])=>`<button type="button" class="secondary" data-signature-command="${cmd}" aria-label="${label}">${label}</button>`).join('')}<select id="signature-size" aria-label="Signature text size"><option value="2">Small</option><option value="3" selected>Normal</option><option value="4">Large</option><option value="5">Extra large</option></select><label>Text colour <input type="color" id="signature-colour" value="#252b3b"></label><label>Highlight <input type="color" id="signature-highlight" value="#fff2a8"></label><button type="button" class="secondary" id="signature-link">Add link</button><button type="button" class="secondary" id="signature-image">Add image</button><button type="button" class="ghost" data-signature-command="removeFormat">Clear formatting</button></div><div id="signature-editor" class="signature-editor" role="textbox" aria-label="Email signature" aria-multiline="true" contenteditable="true"></div><input type="file" id="signature-image-file" accept="image/png,image/jpeg,image/webp" hidden><p class="footnote">Select text to format it or add a website, email, phone or social link. Images: up to 300 px wide, 600 px tall and 100 KB. Pasted text keeps plain formatting.</p>`;
  }
  function bindSignatureEditor(html){
    const editor=$('#signature-editor');mountSignature(editor,html);let selection=null;
    const remember=()=>{const s=window.getSelection();if(s.rangeCount&&editor.contains(s.anchorNode))selection=s.getRangeAt(0).cloneRange();};
    editor.onkeyup=remember;editor.onmouseup=remember;editor.oninput=remember;
    const restore=()=>{editor.focus();const s=window.getSelection();if(selection){s.removeAllRanges();s.addRange(selection);}else{const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);s.removeAllRanges();s.addRange(range);}};
    const command=(cmd,value=null)=>{restore();document.execCommand('styleWithCSS',false,false);document.execCommand(cmd,false,value);remember();};
    editor.onpaste=event=>{event.preventDefault();command('insertText',event.clipboardData.getData('text/plain'));};
    editor.ondrop=event=>event.preventDefault();
    document.querySelectorAll('[data-signature-command]').forEach(button=>{button.onmousedown=e=>e.preventDefault();button.onclick=()=>command(button.dataset.signatureCommand);});
    $('#signature-size').onchange=e=>command('fontSize',e.target.value);
    $('#signature-colour').onchange=e=>command('foreColor',e.target.value);
    $('#signature-highlight').onchange=e=>command('hiliteColor',e.target.value);
    $('#signature-link').onmousedown=e=>e.preventDefault();
    $('#signature-link').onclick=()=>{const href=prompt('Website, email or phone link (https://, mailto: or tel:):');if(!href)return;if(!/^(https?:\/\/|mailto:|tel:)/i.test(href)||/[\x00-\x1f\x7f]/.test(href))return toast('Use an http, https, mailto or tel link.');restore();if(!window.getSelection().toString()){const label=prompt('Link text:',href);if(!label)return;command('insertHTML',`<a href="${esc(href)}">${esc(label)}</a>`);}else command('createLink',href);};
    $('#signature-image').onmousedown=e=>e.preventDefault();$('#signature-image').onclick=()=>$('#signature-image-file').click();
    $('#signature-image-file').onchange=()=>run(async()=>{const file=$('#signature-image-file').files[0];if(!file)return;const fd=new FormData();fd.append('file',file);const result=await api('billing/signature-image',fd);command('insertHTML',`<img src="${esc(result.src)}" alt="Signature image">`);});
  }
  async function reminders(){
    const d=await api('billing/reminder-settings');
    modal('Automatic invoice reminders',`<form id="reminder-settings-form"><p class="notice">When enabled, Expense Pilot emails clients about issued, unpaid invoices on the dates below. Paid, voided and draft invoices are skipped. You can pause reminders on individual invoices.</p>${check('enabled','Enable automatic reminder emails',d.enabled)}${field('Days before due (0 to skip)','before_days','number',d.before_days,'required min="0" max="30"')}${check('on_due_date','Send on the due date',d.on_due_date)}${field('Days overdue (comma-separated; leave blank to skip)','after_days','text',d.after_days.join(', '),'placeholder="7, 14"')}<p class="footnote">Dates use Brisbane time. The server checks once a minute and sends each scheduled reminder at most once. Missed days are not sent in a batch after downtime. Failed or uncertain deliveries appear in the invoice’s email history and are not automatically retried.</p><button type="submit">Save reminder schedule</button></form>`);
    formHandler('#reminder-settings-form',async(data,form)=>{const values=data.after_days.trim()?data.after_days.split(',').map(s=>{if(!/^\d+$/.test(s.trim()))throw Error('Use whole days separated by commas.');return Number(s.trim());}):[];await api('billing/reminder-settings',{enabled:form.elements.enabled.checked,before_days:Number(data.before_days),on_due_date:form.elements.on_due_date.checked,after_days:values},'PUT');$('#modal').close();toast('Reminder schedule saved.');});
  }
  async function compose(doc,kind='document'){
    const draft=await api(`billing/documents/${doc.id}/email-draft?kind=${kind}`);
    if(!draft.ready){toast('Add your SMTP account in Settings → Email delivery first.');return;}
    modal(kind==='receipt'?`Email payment receipt · ${esc(doc.number)}`:kind==='reminder_manual'?'Payment reminder':`Email ${esc(doc.number)}`,`<form id="client-email-form"><p>From <strong>${esc(draft.from_email)}</strong></p>${field('Recipient','recipient','email',draft.recipient,'required maxlength="254"')}${field('Subject','subject','text',draft.subject,'required maxlength="200"')}${area('Message','body',draft.body,20000)}${signaturePreview(draft)}<div class="notice">Attachment: <strong>${esc(draft.filename)}</strong><br>${doc.state==='draft'?'Sending issues and locks this draft.':'The current document and recorded payments are included.'}</div><a class="button-link secondary" href="${esc(draft.attachment_url)}">Preview PDF</a><div class="modal-footer"><button type="submit">Send email</button><button type="button" class="secondary" id="cancel-client-email">Cancel</button></div></form>`);
    $('#modal').classList.add('billing-dialog');bindSignaturePreview(draft);
    on('#cancel-client-email',()=>Billing.view(doc.id));
    formHandler('#client-email-form',async(data,form)=>{const result=await api(`billing/documents/${doc.id}/send`,{...data,message_kind:kind,include_signature:form.elements.include_signature?.checked??false,version:draft.version,request_key:draft.request_key});await Billing.view(doc.id);if(['invoices','quotes'].includes(page))await Billing.documents(doc.kind);toast(result.state==='sent'?'Email accepted by your mail server.':result.error||'Delivery is still being processed.');});
  }
  async function statement(cid,options={mode:'all'}){
    const query=new URLSearchParams(Object.entries(options).filter(([,value])=>value));
    const [d,history]=await Promise.all([api(`billing/clients/${cid}/statement?${query}`),owner()?api(`billing/clients/${cid}/statement-emails`):Promise.resolve([])]);
    const all=d.mode==='all',pdf=`/api/billing/clients/${cid}/statement/pdf?${query}`;
    modal(`Statement · ${esc(d.client.name)}`,`<form id="statement-filter"><div class="grid2">${select('Statement type','mode',[['all','All invoices and payments'],['outstanding','Outstanding invoices']],d.mode)}${all?field('From date','start','date',d.start,'required')+field('To date','end','date',d.end,`required max="${today()}"`):`<p>As at ${dateAU(d.end)}</p>`}</div><button type="submit" class="secondary">Update statement</button></form><div class="statement-summary">${all?`<span>Opening balance <strong>${money(d.opening_cents)}</strong></span>`:''}<span>${all?'Closing balance':'Total outstanding'} <strong>${money(d.closing_cents)}</strong></span></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Invoice</th><th>${all?'Details':'Due'}</th><th class="right">${all?'Invoiced':'Total'}</th><th class="right">Paid</th><th class="right">${all?'Balance':'Outstanding'}</th></tr></thead><tbody>${d.rows.map(row=>`<tr><td>${dateAU(row.date)}</td><td>${esc(row.number)}</td><td>${esc(all?row.description:dateAU(row.due_date))}</td><td class="right">${money(all?row.debit_cents:row.amount_cents)}</td><td class="right">${money(all?row.credit_cents:row.paid_cents)}</td><td class="right">${money(row.balance_cents)}</td></tr>`).join('')}</tbody></table>${d.rows.length?'':`<p class="empty">${all?'No invoice or payment activity in this period.':'No outstanding invoices.'}</p>`}</div><div class="modal-footer"><a class="button-link secondary" href="${pdf}">Download statement PDF</a>${owner()?'<button id="email-statement">Email statement</button>':''}</div>${owner()?`<h3>Statement email history</h3>${history.length?history.map(row=>`<div class="email-history"><strong>${esc(row.state==='sent'?'Sent / mail server accepted':row.state)}</strong> · ${esc(row.recipient)}<br><small>${dateAU(row.created_at)} · ${esc(row.subject)}</small>${row.error?`<p>${esc(row.error)}</p>`:''}${['sending','unknown'].includes(row.state)?`<button class="secondary resolve-statement-email" data-id="${row.id}">Confirm delivery status</button>`:''}</div>`).join(''):'<p class="muted">No statement emails have been sent.</p>'}`:''}`);
    $('#modal').classList.add('billing-dialog');
    const current={mode:d.mode,start:d.start,end:d.end};
    $('#statement-filter #mode').onchange=e=>run(()=>statement(cid,{...current,mode:e.target.value}));
    formHandler('#statement-filter',data=>statement(cid,data));
    on('#email-statement',()=>composeStatement(cid,current));
    on('.resolve-statement-email',b=>{modal('Confirm statement email delivery',`<p>Check your provider’s sent or delivery logs first. An uncertain message may already have reached the client.</p><form id="resolve-statement-form">${select('What did your provider confirm?','state',[['sent','Message was sent'],['failed','Message was not sent — allow retry']])}<button type="submit">Save confirmed status</button></form>`);formHandler('#resolve-statement-form',async data=>{await api(`billing/statement-emails/${b.dataset.id}/resolve`,data);await statement(cid,current);});});
  }
  async function composeStatement(cid,options){
    const query=new URLSearchParams(Object.entries(options).filter(([,value])=>value)),draft=await api(`billing/clients/${cid}/statement/email-draft?${query}`);
    if(!draft.ready)return toast('Add your SMTP account in Settings → Email delivery first.');
    modal('Email client statement',`<form id="statement-email-form"><p>From <strong>${esc(draft.from_email)}</strong></p>${field('Recipient','recipient','email',draft.recipient,'required maxlength="254"')}${field('Subject','subject','text',draft.subject,'required maxlength="200"')}${area('Message','body',draft.body,20000)}${signaturePreview(draft)}<p>Attachment: ${esc(draft.filename)}</p><a class="button-link secondary" href="/api/billing/clients/${cid}/statement/pdf?${query}">Preview statement PDF</a><div class="modal-footer"><button type="submit">Send statement</button><button type="button" class="secondary" id="cancel-statement-email">Cancel</button></div></form>`);
    bindSignaturePreview(draft);on('#cancel-statement-email',()=>statement(cid,options));
    formHandler('#statement-email-form',async(data,form)=>{const result=await api(`billing/clients/${cid}/statement/send`,{...data,...options,include_signature:form.elements.include_signature?.checked??false,version:draft.version,request_key:draft.request_key});await statement(cid,options);toast(result.state==='sent'?'Statement accepted by your mail server.':result.error||'Delivery is still being processed.');});
  }
  async function invoiceReminders(doc){
    const schedule=await api('billing/reminder-settings');
    modal(`Reminder options · ${esc(doc.number)}`,`<form id="invoice-reminder-form"><p class="notice">Automatic reminders are currently ${schedule.enabled?'enabled':'off'} in Settings. ${schedule.enabled?'This invoice follows the saved reminder schedule.':'Enabling them in Settings is required before any reminders can be sent.'}</p>${check('enabled','Allow automatic reminders for this invoice',doc.reminders_enabled)}<button type="submit">Save invoice reminder preference</button></form>`);
    formHandler('#invoice-reminder-form',async(data,form)=>{await api(`billing/documents/${doc.id}/reminders`,{enabled:form.elements.enabled.checked,version:doc.version},'PUT');await Billing.view(doc.id);toast('Invoice reminder preference saved.');});
  }
  return {templates,reminders,compose,statement,invoiceReminders};
})();
