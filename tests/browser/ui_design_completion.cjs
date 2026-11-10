// Exercise the shared page layouts with real server data. Mail is simulated by the test server.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const post=async(path,data,method='POST')=>{const session=await(await context.request.get(url+'/api/session')).json();const response=await context.request.fetch(url+'/api/'+path,{method,headers:{'X-CSRF-Token':session.csrf},data});assert.equal(response.status(),200,await response.text());return response.json();};
 const shot=async(name)=>page.screenshot({path:output+'/design-completion-'+name+'.png',fullPage:true});
 const fits=async(label)=>assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,label);
 try{
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  await post('features',{employment:true,business:true,home_office:true,trips:true,vehicles:true,banks:true,tax:true},'PUT');
  const clients=await(await context.request.get(url+'/api/billing/clients')).json(),client=clients.find(c=>!c.archived);assert.ok(client,'An active client is available from the preceding billing workflows');
  await post('billing/time',{client_id:client.id,date:new Date().toISOString().slice(0,10),description:'Design completion billable time',hours:'1',rate:'125',billable:true});
  await page.goto(url);await page.locator('[data-page=dashboard]').waitFor();
  // A quote goes through the same live PDF editor and saved-document actions as an invoice.
  await navigate(page,'quotes');await page.getByRole('button',{name:'New quote',exact:false}).click();
  await page.getByLabel('Line description',{exact:true}).fill('Design completion quote');await page.getByLabel('Unit price',{exact:true}).fill('275');
  await page.locator('#editor-preview .invoice-paper').waitFor();await shot('quote-editor');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByRole('button',{name:'Issue without email',exact:true}).waitFor();await page.locator('#close-modal').click();
  await page.locator('#billing-search').fill('Design completion quote');assert.equal(await page.locator('#billing-table tbody tr').count(),1);
  await shot('quotes');
  await page.locator('#billing-search').fill('');await page.setViewportSize({width:390,height:844});
  const sortNumber=page.locator('#billing-table [data-sort=number]');await sortNumber.waitFor({state:'visible'});await sortNumber.click();assert.equal(await sortNumber.getAttribute('aria-pressed'),'true');
  const numbers=await page.locator('#billing-table .billing-number').allTextContents();assert.deepEqual(numbers,[...numbers].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})));
  await fits('quote sorting on mobile');await shot('quote-sort-mobile');await page.setViewportSize({width:1440,height:1050});
  // Search is applied to the saved register without dropping any record actions.
  for(const [route,id] of [['clients','client-search'],['services','service-search'],['time','time-search']]){
   await navigate(page,route);await page.locator('#'+id).waitFor();
   if(route==='time'&&await page.locator('.time-select').count())await page.locator('.time-select').first().check();
   await page.locator('#'+id).fill('No matching design record 938472');
   if(route==='time')assert.equal(await page.locator('.time-select:checked').count(),0,'Hidden time entries are not retained for invoicing');
   assert.equal(await page.locator('#content tbody tr:visible').count(),0,route);await page.locator('#'+id).fill('');await shot(route);
  }
  await navigate(page,'invoices');await page.getByRole('button',{name:'Branding',exact:true}).click();
  await page.getByRole('heading',{name:'Invoice design',exact:true}).waitFor();await page.locator('#branding-tab[aria-current=page]').waitFor();await shot('branding');
  await page.getByRole('navigation',{name:'Billing pages',exact:true}).getByRole('button',{name:'Email settings',exact:true}).click();await page.getByRole('button',{name:'Email templates & signature',exact:false}).waitFor();await shot('email-settings');await page.locator('#close-modal').click();
  // All remaining destinations keep the shared shell and remain within a phone viewport.
  for(const route of ['banks','equipment','drive_review','vehicles','home_office','trips','invoices','quotes','clients','recurring','services','time','income','employment','reports','documents','adviser_questions','tax']){
   await page.setViewportSize({width:1440,height:1050});await navigate(page,route);
   await page.waitForFunction(()=>{const t=document.querySelector('#content')?.textContent||'';return t&&!/Loading[.\u2026]/.test(t);});
   await fits(route+' desktop');await shot(route+'-desktop');
   await page.setViewportSize({width:390,height:844});await fits(route+' mobile');await shot(route+'-mobile');
  }
  // Inline document viewing retains paging/zoom/download and returns to the list on close.
  await navigate(page,'documents');const view=page.getByRole('button',{name:'View',exact:true}).first();
  if(await view.count()){
   await view.click();await page.locator('#document-viewer').waitFor();await fits('inline document mobile');await shot('document-review-mobile');
   await page.getByRole('button',{name:'Close document preview',exact:true}).click();await page.locator('.document-register').waitFor({state:'visible'});
  }
  // A saved answer stays with its question and does not modify the financial record.
  const expenses=await(await context.request.get(url+'/api/expenses')).json();
  if(expenses.length){
   const original=JSON.stringify(expenses.find(e=>e.id===expenses[0].id));
   const question=await post('workflows/questions',{record_type:'expense',record_id:expenses[0].id,question:'Design completion discussion'});
   await navigate(page,'adviser_questions');await page.locator('[data-question="'+question.id+'"]').getByRole('button',{name:'Respond',exact:true}).click();
   await page.getByLabel('Answer',{exact:true}).fill('Recorded for review.');await page.getByLabel('Resolved',{exact:true}).check();await page.getByRole('button',{name:'Save response',exact:true}).click();await page.getByText('Response saved.',{exact:true}).waitFor();
   const after=await(await context.request.get(url+'/api/expenses')).json();assert.equal(JSON.stringify(after.find(e=>e.id===expenses[0].id)),original);
  }
  await page.setViewportSize({width:1440,height:1050});await navigate(page,'quotes');await page.evaluate(()=>Theme.set('dark'));await fits('dark quotes');await shot('quotes-dark');
  assert.deepEqual(errors,[]);console.log('PASS: complete server layouts, quote editor/search, client/service/time search, billing design/email navigation, 18 desktop/mobile destinations, document viewer and adviser response.');
 }catch(error){await shot('failure');throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
