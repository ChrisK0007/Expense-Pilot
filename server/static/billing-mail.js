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
    return `<h3>Email signature</h3><div class="signature-toolbar" role="toolbar" aria-label="Signature formatting">${[['bold','Bold'],['italic','Italic'],['underline','Underline']].map(([cmd,label])=>`<button type="button" class="secondary" data-signature-command="${cmd}" aria-label="${label}">${label}</button>`).join('')}<select id="signature-size" aria-label="Signature text size"><option value="2">Small</option><option value="3" selected>Normal</option><option value="4">Large</option><option value="5">Extra large</option></select><label>Text colour <input type="color" id="signature-colour" value="#252b3b"></label><label>Highlight <input type="color" id="signature-highlight" value="#fff2a8"></label><button type="button" class="secondary" id="signature-link">Add link</button><button type="button" class="secondary" id="signature-image">Add image</button><button type="button" class="ghost" data-signature-command="removeFormat">Clear formatting</button></div><div id="signature-editor" class="signature-editor" role="textbox" aria-label="Email signature" aria-multiline="true" contenteditable="true"></div><input type="file" id="signature-image-file" accept="image/png,image/jpeg,image/webp" hidden><p class="footnote">Select text to format it or add a website, email, phone or social link. Paste a formatted signature to keep its supported styling and layout. Images up to 2 MB are fitted to 300 × 600 px; the embedded result must be under 100 KB. Up to three images. Linked or unavailable clipboard images can be added separately.</p>`;
  }
  function bindSignatureEditor(html){
    const editor=$('#signature-editor');mountSignature(editor,html);let selection=null;
    const remember=()=>{const s=window.getSelection();if(s.rangeCount&&editor.contains(s.anchorNode))selection=s.getRangeAt(0).cloneRange();};
    editor.onkeyup=remember;editor.onmouseup=remember;editor.oninput=remember;
    const restore=()=>{editor.focus();const s=window.getSelection();if(selection){s.removeAllRanges();s.addRange(selection);}else{const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);s.removeAllRanges();s.addRange(range);}};
    const command=(cmd,value=null)=>{restore();document.execCommand('styleWithCSS',false,false);document.execCommand(cmd,false,value);remember();};
    editor.onpaste=event=>{
      event.preventDefault();remember();const html=event.clipboardData.getData('text/html'),plain=event.clipboardData.getData('text/plain'),files=[...event.clipboardData.files].filter(f=>f.type.startsWith('image/'));
      run(async()=>{
        if(html){let payload={html};if(files.length){payload=new FormData();payload.append('html',html);files.slice(0,3).forEach(file=>payload.append('images',file));}const result=await api('billing/signature-paste',payload);if(!editor.isConnected)return;command('insertHTML',result.html);mountSignature(editor,editor.innerHTML);selection=null;if(result.missing_images)toast(`${result.missing_images} image(s) could not transfer. Select each [Add image] label and use Add image to replace it.`);}
        else if(files.length){for(const file of files.slice(0,3)){const fd=new FormData();fd.append('file',file);const result=await api('billing/signature-image',fd);if(editor.isConnected)command('insertHTML',`<img src="${esc(result.src)}" alt="Signature image">`);}}
        else command('insertText',plain);
      });
    };
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
  function reminderScheduleText(d){
    const parts=[];
    if(d.before_days)parts.push(`${d.before_days} day${d.before_days===1?'':'s'} before the due date`);
    if(d.on_due_date)parts.push('on the due date');
    for(const days of d.after_days)parts.push(`${days} day${days===1?'':'s'} overdue`);
    return parts.length?parts.join(' · '):'No reminder dates selected';
  }
  async function reminders(){
    const [d,config]=await Promise.all([api('billing/reminder-settings'),api('billing/settings')]);
    const ready=!!(config.email?.host&&config.email?.from_email);
    modal('Automatic invoice reminders',`<form id="reminder-settings-form"><p class="muted">Choose when to follow up unpaid invoices. These settings are shared by invoices with automatic reminders switched on.</p><section class="reminder-master">${check('enabled','Enable automatic reminder emails',d.enabled)}<p id="reminder-master-status" class="footnote"></p></section><p class="${ready?'footnote':'notice'}">${ready?`Emails are sent from ${esc(config.email.from_email)} to the client’s saved invoice email.`:'Set up Email delivery before enabling automatic reminders.'}</p><h3>When to send</h3><div class="reminder-stages"><section>${check('before_enabled','Before the due date',d.before_days>0)}${field('Days before the due date','before_days','number',d.before_days||3,'required min="1" max="30"')}</section><section>${check('on_due_date','On the due date',d.on_due_date)}<p class="footnote">Send one reminder on the invoice’s payment due date.</p></section><section>${check('after_enabled','After the due date',d.after_days.length>0)}<div id="overdue-reminder-days"></div><button type="button" class="secondary" id="add-overdue-reminder">+ Add overdue reminder</button><p class="footnote">Up to six follow-ups, each 1–365 days after the due date.</p></section></div><section class="reminder-preview" aria-live="polite"><h3>Schedule summary</h3><p id="reminder-schedule-summary"></p></section><p class="footnote">Only issued invoices with money still owing are included. Draft, paid and voided invoices are skipped. Turn reminders off on an individual invoice to exclude it.</p><details class="reminder-delivery-notes"><summary>Timing and delivery</summary><p class="footnote">Dates use Brisbane time. The server checks every minute while running and sends each scheduled reminder once. Missed dates are skipped after downtime. Check the invoice’s email history for failed or uncertain deliveries; these are not automatically retried. Changing this schedule can make an existing unpaid invoice eligible today.</p></details><div class="modal-footer"><button type="submit">Save reminder schedule</button></div></form><div class="actions document-actions"><button class="secondary" id="reminder-email-wording">Edit reminder emails →</button><button class="secondary" id="reminder-email-delivery">Email delivery settings →</button></div>`);
    $('#modal').classList.add('billing-dialog');
    const list=$('#overdue-reminder-days');let nextId=0;
    const addDay=days=>{
      const row=document.createElement('div');row.className='overdue-reminder-row';const id='overdue-days-'+(++nextId);
      row.innerHTML=field('Days after the due date',id,'number',days,'required min="1" max="365"')+'<button type="button" class="ghost" aria-label="Remove overdue reminder">Remove</button>';
      row.querySelector('button').onclick=()=>{row.remove();update();};list.append(row);
    };
    (d.after_days.length?d.after_days:[7,14]).forEach(addDay);
    const values=()=>({enabled:$('#enabled').checked,before_days:$('#before_enabled').checked?Number($('#before_days').value):0,on_due_date:$('#on_due_date').checked,after_days:$('#after_enabled').checked?[...list.querySelectorAll('input')].map(el=>Number(el.value)):[]});
    function update(){
      const before=$('#before_enabled').checked,after=$('#after_enabled').checked;
      $('#before_days').disabled=!before;
      list.querySelectorAll('input,button').forEach(el=>el.disabled=!after);
      $('#add-overdue-reminder').disabled=!after||list.children.length>=6;
      const v=values();$('#reminder-master-status').textContent=v.enabled?'On: eligible unpaid invoices follow this schedule after you save.':'Off: no automatic reminder emails will be sent. Your schedule stays saved for later.';
      $('#reminder-schedule-summary').textContent=reminderScheduleText(v)+(v.enabled?'':'. Automatic sending is off.');
    }
    $('#reminder-settings-form').addEventListener('input',update);$('#reminder-settings-form').addEventListener('change',update);
    $('#add-overdue-reminder').onclick=()=>{if(list.children.length<6){const last=Number(list.lastElementChild?.querySelector('input').value)||0;addDay(Math.min(365,last+7));update();}};
    on('#reminder-email-wording',()=>templates('reminders'));on('#reminder-email-delivery',()=>Billing.emailDelivery());
    update();
    formHandler('#reminder-settings-form',async()=>{const v=values();if(v.after_days.length!==new Set(v.after_days).size)throw Error('Use a different day for each overdue reminder.');if($('#after_enabled').checked&&!v.after_days.length)throw Error('Add an overdue reminder or turn off After the due date.');await api('billing/reminder-settings',v,'PUT');$('#modal').close();toast('Reminder schedule saved.');});
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
  function invoiceReminderStatus(doc,schedule){
    if(!doc.reminders_enabled)return 'Off for this invoice. You can still send a reminder manually.';
    if(!schedule.enabled)return 'On for this invoice, but automatic sending is off in Settings.';
    if(doc.state==='draft')return 'On. Reminders begin after this draft is issued, using its saved reminder schedule.';
    if(doc.state==='void'||doc.balance_cents<=0)return 'On, but no reminders are sent while this invoice is paid or voided.';
    return 'On: '+reminderScheduleText(schedule)+'.';
  }
  function invoiceReminderSummary(doc){
    return `<section class="invoice-reminder-summary">${check('invoice-reminders-enabled','Automatic reminders for this invoice',doc.reminders_enabled)}<p class="footnote" id="invoice-reminder-status">Loading this invoice’s reminder settings…</p></section>`;
  }
  function bindInvoiceReminderSummary(doc){
    const input=$('#invoice-reminders-enabled'),status=$('#invoice-reminder-status');
    run(async()=>{const data=await api(`billing/documents/${doc.id}/reminders`);if(status.isConnected)status.textContent=invoiceReminderStatus(doc,data.effective_schedule);});
    input.onchange=async()=>{input.disabled=true;try{await api(`billing/documents/${doc.id}/reminders`,{enabled:input.checked,version:doc.version},'PUT');await Billing.view(doc.id);toast('Invoice reminder preference saved.');}catch(error){input.checked=!!doc.reminders_enabled;toast(error.message);}finally{input.disabled=false;}};
  }
  async function invoiceReminders(doc){
    const d=await api(`billing/documents/${doc.id}/reminders`),schedule=d.options.schedule||d.shared_schedule;
    const names={reminder_due:'Before / on due date',reminder_overdue:'Overdue',reminder_manual:'Manual reminder'};
    modal(`Reminder options · ${esc(doc.number)}`,`<form id="invoice-reminder-form"><p class="notice">${esc(invoiceReminderStatus({...doc,reminders_enabled:d.enabled},d.effective_schedule))}</p>${check('invoice-reminder-enabled','Allow automatic reminders for this invoice',d.enabled)}<section class="invoice-reminder-section"><h3>Schedule</h3>${check('invoice-custom-schedule','Use a custom schedule for this invoice',!!d.options.schedule)}<p class="footnote">When off, this invoice follows the shared schedule in Settings.</p><fieldset id="invoice-schedule-fields" class="reminder-stages"><section>${check('ir-before-enabled','Before the due date',schedule.before_days>0)}${field('Days before the due date','ir-before-days','number',schedule.before_days||3,'required min="1" max="30"')}</section><section>${check('ir-on-due','On the due date',schedule.on_due_date)}</section><section>${check('ir-after-enabled','After the due date',schedule.after_days.length>0)}<div id="ir-overdue-days"></div><button type="button" class="secondary" id="ir-add-day">+ Add overdue reminder</button><p class="footnote">Up to six follow-ups, each 1–365 days after the due date.</p></section></fieldset><p class="reminder-preview" id="invoice-schedule-preview" aria-live="polite"></p></section><section class="invoice-reminder-section"><h3>Email wording</h3><p class="footnote">Custom wording applies only to this invoice. Unchecked emails use the latest shared template. Your shared email signature is included.</p>${Object.keys(names).map((key,i)=>{const custom=d.options.templates?.[key],t=custom||d.shared_templates[key];return `<details class="invoice-email-options" ${i===0?'open':''}><summary>${names[key]} email</summary>${check('custom-'+key,'Customise '+names[key].toLowerCase()+' email',!!custom)}<fieldset id="fields-${key}">${field('Subject',key+'-subject','text',t.subject,'required maxlength="200"')}${area('Message',key+'-body',t.body)}<div class="template-fields">${select('Insert field',key+'-insert',[['','Choose a field…'],...d.template_fields[key].map(f=>[f,d.fields[f]])])}</div><details class="template-example"><summary>Preview for ${esc(doc.number)}</summary><strong id="preview-${key}-subject"></strong><p class="preserve-lines" id="preview-${key}-body"></p></details></fieldset></details>`;}).join('')}</section><p class="footnote">Automatic sending must also be enabled in Settings. Draft, paid and voided invoices are skipped. Changing dates can make this invoice eligible today; a reminder already attempted today is not sent again.</p><div class="modal-footer"><button type="submit">Save invoice reminders</button><button type="button" class="secondary" id="cancel-invoice-reminders">Cancel</button></div></form>`);
    $('#modal').classList.add('billing-dialog');
    const list=$('#ir-overdue-days');let nextId=0,lastField=null;
    const addDay=days=>{const row=document.createElement('div');row.className='overdue-reminder-row';row.innerHTML=field('Days after the due date','ir-day-'+(++nextId),'number',days,'required min="1" max="365"')+'<button type="button" class="ghost" aria-label="Remove overdue reminder">Remove</button>';row.querySelector('button').onclick=()=>{row.remove();update();};list.append(row);};
    (schedule.after_days.length?schedule.after_days:[7,14]).forEach(addDay);
    const scheduleValues=()=>({before_days:$('#ir-before-enabled').checked?Number($('#ir-before-days').value):0,on_due_date:$('#ir-on-due').checked,after_days:$('#ir-after-enabled').checked?[...list.querySelectorAll('input')].map(el=>Number(el.value)):[]});
    function update(){
      const custom=$('#invoice-custom-schedule').checked,after=$('#ir-after-enabled').checked;
      $('#invoice-schedule-fields').disabled=!custom;$('#ir-before-days').disabled=!$('#ir-before-enabled').checked;
      list.querySelectorAll('input,button').forEach(el=>el.disabled=!after);$('#ir-add-day').disabled=!after||list.children.length>=6;
      $('#invoice-schedule-preview').textContent=(custom?'This invoice: ':'Shared schedule: ')+reminderScheduleText(custom?scheduleValues():d.shared_schedule)+(!d.shared_schedule.enabled?'. Automatic sending is off in Settings.':'');
      for(const key of Object.keys(names)){
        $('#fields-'+key).disabled=!$('#custom-'+key).checked;
        for(const field of ['subject','body'])$('#preview-'+key+'-'+field).textContent=$('#'+key+'-'+field).value.replace(/\{([a-z_]+)\}/g,(tag,token)=>d.preview_values[token]??tag);
      }
    }
    $('#invoice-reminder-form').addEventListener('input',update);$('#invoice-reminder-form').addEventListener('change',update);
    $('#ir-add-day').onclick=()=>{if(list.children.length<6){addDay(Math.min(365,(Number(list.lastElementChild?.querySelector('input').value)||0)+7));update();}};
    for(const key of Object.keys(names)){
      for(const part of ['subject','body'])$('#'+key+'-'+part).onfocus=e=>lastField=e.target;
      $('#'+key+'-insert').onchange=e=>{if(!e.target.value)return;const el=lastField?.id.startsWith(key+'-')?lastField:$('#'+key+'-body');el.setRangeText('{'+e.target.value+'}',el.selectionStart??el.value.length,el.selectionEnd??el.value.length,'end');e.target.value='';el.focus();update();};
    }
    on('#cancel-invoice-reminders',()=>Billing.view(doc.id));update();
    formHandler('#invoice-reminder-form',async()=>{
      const options={templates:{}};
      if($('#invoice-custom-schedule').checked){options.schedule=scheduleValues();if(options.schedule.after_days.length!==new Set(options.schedule.after_days).size)throw Error('Use a different day for each overdue reminder.');if($('#ir-after-enabled').checked&&!options.schedule.after_days.length)throw Error('Add an overdue reminder or turn off After the due date.');}
      for(const key of Object.keys(names))if($('#custom-'+key).checked)options.templates[key]={subject:$('#'+key+'-subject').value,body:$('#'+key+'-body').value};
      await api(`billing/documents/${doc.id}/reminders`,{enabled:$('#invoice-reminder-enabled').checked,options,version:d.version},'PUT');await Billing.view(doc.id);toast('Invoice reminders saved.');
    });
  }
  return {templates,reminders,compose,statement,invoiceReminders,invoiceReminderSummary,bindInvoiceReminderSummary};
})();
