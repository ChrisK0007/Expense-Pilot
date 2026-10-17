// Final beta regression workflow; browser_server.py uses simulated delivery only.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
async function main(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();await page.locator('[data-page=dashboard]').waitFor();
  await navigate(page,'invoices');
  const nav=page.getByRole('navigation',{name:'Billing pages',exact:true});
  for(const [label,key] of [['Clients','clients'],['Recurring invoices','recurring'],['Services & prices','services'],['Quotes','quotes'],['Invoices','invoices']]){
   await nav.getByRole('button',{name:label,exact:true}).click();await page.locator(`[data-billing-page=${key}][aria-current=page]`).waitFor();
   assert.equal(await nav.getByRole('button',{name:'Invoices',exact:true}).count(),1);
   assert.equal(await nav.getByRole('button',{name:'Quotes',exact:true}).count(),1);
   assert.equal(await nav.getByRole('button',{name:'Clients',exact:true}).count(),1);
  }
  await nav.getByRole('button',{name:'Clients',exact:true}).click();await page.getByRole('heading',{name:'Clients',exact:true}).waitFor();await page.locator('#add-client:not([disabled])').waitFor();
  await page.screenshot({path:output+'/beta-clients-desktop.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/beta-clients-mobile.png',fullPage:true});await nav.getByRole('button',{name:'Invoices',exact:true}).click();await page.locator('[data-billing-page=invoices][aria-current=page]').waitFor();await page.setViewportSize({width:1440,height:1050});
  await nav.getByRole('button',{name:'Quotes',exact:true}).click();await nav.getByRole('button',{name:'Email settings',exact:true}).click();await page.getByRole('heading',{name:'Email settings',exact:true}).waitFor();await page.getByRole('button',{name:'Email templates & signature',exact:false}).click();
  assert.equal(await page.getByRole('tab',{name:'Quotes',exact:true}).getAttribute('aria-selected'),'true');await page.locator('#close-modal').click();
  await nav.getByRole('button',{name:'Recurring invoices',exact:true}).click();await page.screenshot({path:output+'/beta-billing-navigation-desktop.png',fullPage:true});await nav.getByRole('button',{name:'Invoices',exact:true}).click();
  const session=await (await page.request.get(url+'/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const response=await page.request.post(url+'/api/billing/clients',{headers,data:{name:'Reminder browser customer',email:'reminder-browser@example.test',terms:14}});assert.equal(response.status(),200);const cid=(await response.json()).id;
  await page.getByRole('button',{name:'New invoice',exact:false}).click();await page.getByLabel('Client',{exact:true}).selectOption(String(cid));await page.getByLabel('Line description',{exact:true}).fill('Beta reminder preference test');await page.getByLabel('Unit price',{exact:true}).fill('45');await page.getByLabel('Automatic reminders for this invoice',{exact:true}).uncheck();await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.locator('#invoice-reminders-enabled').waitFor();
  assert.equal(await page.locator('#invoice-reminders-enabled').isChecked(),false);assert.equal(await page.getByRole('button',{name:'Reminder options',exact:true}).isVisible(),true);
  const documents=await (await page.request.get(url+'/api/billing/documents')).json(),original=documents.find(d=>d.client_id===cid);assert.equal(original.reminders_enabled,0);
  const changeReminder=async checked=>{const response=page.waitForResponse(r=>r.url().endsWith('/reminders')&&r.request().method()==='PUT');await page.locator('#invoice-reminders-enabled').setChecked(checked);assert.equal((await response).status(),200);await page.locator('#invoice-reminder-status').filter({hasText:checked?'On for this invoice':'Off for this invoice'}).waitFor();};
  await changeReminder(true);page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Issue without email',exact:true}).click();await page.getByRole('button',{name:'Send reminder',exact:true}).waitFor();await changeReminder(false);
  await page.screenshot({path:output+'/beta-invoice-reminders-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Make recurring',exact:true}).click();assert.equal(await page.getByLabel('Allow automatic reminders on generated invoices').isChecked(),false);await page.getByLabel('Allow automatic reminders on generated invoices').check();
  const today=await page.evaluate(()=>today());await page.getByLabel('First draft date',{exact:true}).fill(today);await page.getByRole('button',{name:'Create recurring schedule',exact:true}).click();await page.getByText('Recurring draft schedule created.',{exact:true}).waitFor();await page.locator('[data-billing-page=recurring][aria-current=page]').waitFor();
  await page.getByRole('button',{name:'Generate due drafts now',exact:true}).click();await page.getByText(/draft invoice\(s\) created\./).waitFor();
  const current=await (await page.request.get(url+'/api/billing/documents')).json(),generated=current.find(d=>d.client_id===cid&&d.schedule_id);assert.ok(generated);assert.equal(generated.reminders_enabled,1);
  await nav.getByRole('button',{name:'Invoices',exact:true}).click();await page.locator('#billing-table tbody tr').filter({hasText:generated.number}).getByRole('button',{name:'Open ↗',exact:true}).click();await changeReminder(false);await page.locator('#close-modal').click();
  const generatedSaved=await (await page.request.get(url+'/api/billing/documents/'+generated.id)).json();assert.equal(generatedSaved.reminders_enabled,0);
  await navigate(page,'settings');await page.getByRole('button',{name:'Automatic invoice reminders',exact:false}).click();await page.getByLabel('Before the due date',{exact:true}).uncheck();assert.equal(await page.getByLabel('Days before the due date',{exact:true}).isDisabled(),true);
  await page.getByLabel('On the due date',{exact:true}).check();await page.getByLabel('After the due date',{exact:true}).check();await page.getByRole('button',{name:'Remove overdue reminder',exact:true}).first().click();await page.getByLabel('Days after the due date',{exact:true}).fill('5');await page.getByRole('button',{name:'Add overdue reminder',exact:false}).click();await page.getByLabel('Days after the due date',{exact:true}).nth(1).fill('12');
  assert.match(await page.locator('#reminder-schedule-summary').innerText(),/5 days overdue.*12 days overdue/);
  await page.screenshot({path:output+'/beta-reminder-settings-desktop.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/beta-reminder-settings-mobile.png',fullPage:true});await page.getByRole('button',{name:'Save reminder schedule',exact:true}).click();await page.getByText('Reminder schedule saved.',{exact:true}).waitFor();
  const schedule=await (await page.request.get(url+'/api/billing/reminder-settings')).json();assert.equal(schedule.before_days,0);assert.deepEqual(schedule.after_days,[5,12]);assert.equal(schedule.enabled,false);
  await page.setViewportSize({width:1440,height:1050});
  // Accept a receipt, delete its expense, and prove it cannot return after refresh.
  const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=240;c.height=80;const ctx=c.getContext('2d');ctx.fillStyle='#e8ebff';ctx.fillRect(0,0,240,80);ctx.fillStyle='#182747';ctx.fillText('Permanent expense deletion test',10,30);return c.toDataURL('image/png').split(',')[1];});
  const upload=await page.request.post(url+'/api/receipts',{headers,multipart:{file:{name:'delete-accepted.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')}}});assert.equal(upload.status(),200);const rid=(await upload.json()).id;
  const draft=await page.request.put(url+'/api/receipts/'+rid+'/draft',{headers,data:{date:today,merchant:'Delete accepted expense browser',amount:'31.27',currency:'AUD',category:'Other',scope:'business',percent:100}});assert.equal(draft.status(),200);
  await navigate(page,'receipts');await page.locator('.receipt-card').filter({has:page.getByRole('heading',{name:'Delete accepted expense browser',exact:true})}).getByRole('button',{name:'Review & categorise',exact:false}).click();await page.getByRole('button',{name:'Save expense',exact:true}).click();await page.getByText('Expense saved.',{exact:true}).waitFor();
  await navigate(page,'expenses');await page.getByLabel('Search expenses').fill('Delete accepted expense browser');await page.getByRole('button',{name:'Edit Delete accepted expense browser',exact:true}).click();
  page.once('dialog',d=>{assert.match(d.message(),/attached receipt/);d.accept();});await page.locator('#delete').click();await page.getByText('Expense deleted',{exact:true}).waitFor();
  for(const suffix of ['','/preview','/info'])assert.equal((await page.request.get(url+'/api/receipts/'+rid+suffix)).status(),404);
  await page.reload();await page.locator('[data-page=dashboard]').waitFor();await navigate(page,'receipts');await page.getByRole('heading',{name:'Draft receipts',exact:true}).waitFor();assert.equal(await page.getByRole('heading',{name:'Delete accepted expense browser',exact:true}).count(),0);
  const remaining=await (await page.request.get(url+'/api/receipts?unfiled=1')).json();assert.ok(!remaining.some(r=>r.id===rid));assert.deepEqual(errors,[]);
  console.log('Beta billing cleanup passed: persistent navigation, email settings, per-invoice/recurring reminder choices, reminder schedule controls, permanent expense and receipt removal.');
 }catch(e){await page.screenshot({path:output+'/beta-billing-cleanup-failure.png',fullPage:true});throw e;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
