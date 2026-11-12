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
 const separated=async(selector,label)=>{
  const boxes=await page.locator(selector).evaluateAll(nodes=>nodes.map(node=>{
   const {top,bottom}=node.getBoundingClientRect();
   return {top,bottom};
  }));
  assert.ok(boxes.length>1,label+' has adjacent sections');
  for(let i=1;i<boxes.length;i++){
   assert.ok(boxes[i].top-boxes[i-1].bottom>=10,label+' has space between sections');
  }
 };
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
   const ready={banks:'#feed-filter',equipment:'.equipment-cards',drive_review:'#drive-date',vehicles:'#vehicle-results .cards',home_office:'#home-office-year',trips:'#trip-results .panel',invoices:'#billing-search',quotes:'#billing-search',clients:'#client-search',recurring:'#run-schedules:not([disabled])',services:'#service-search',time:'#time-search',income:'#income-result table',employment:'#employment-year',reports:'#expense-report-body .report-summary',documents:'#document-search',adviser_questions:'.adviser-list',tax:'#tax-year'};
   await page.locator('#content[data-workspace-page="'+route+'"]').waitFor();await page.locator(ready[route]).first().waitFor({state:'visible'});
   if(route==='banks'){
    await page.locator('#feed-filter').waitFor();await page.locator('.page-tabs [href="#/bank_accounts"]').click();await page.locator('#bank-account-overview').waitFor({state:'visible'});assert.equal(await page.locator('#bank-feeds').isVisible(),false);await shot('bank-accounts-tab');await page.locator('.page-tabs [href="#/banks"]').click();await page.locator('#feed-filter').waitFor({state:'visible'});
    const loaded=page.waitForResponse(response=>response.url().includes('/api/bank-transactions?state=all'));await page.locator('#feed-filter').selectOption('all');const feed=await(await loaded).json();
    if(feed.items.length){await page.locator('[data-bank-review]').first().click();await page.locator('#bank-review-detail #modal[open]').waitFor();await fits('bank review desktop');await shot('bank-review-desktop');await page.locator('#close-modal').click();}
   }
   await fits(route+' desktop');await shot(route+'-desktop');
   await page.setViewportSize({width:390,height:844});await fits(route+' mobile');await shot(route+'-mobile');
   if(route==='banks'&&await page.locator('[data-bank-review]').count()){await page.locator('[data-bank-review]').first().click();await page.locator('#bank-review-detail #modal[open]').waitFor();await fits('bank review mobile');await shot('bank-review-mobile');await page.locator('#close-modal').click();}
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
   await page.getByLabel('Answer',{exact:true}).fill('Recorded for review.');await page.getByLabel('Resolved',{exact:true}).check();await fits('adviser response mobile');await shot('adviser-response-mobile');await page.getByRole('button',{name:'Save response',exact:true}).click();await page.getByText('Response saved.',{exact:true}).waitFor();
   const after=await(await context.request.get(url+'/api/expenses')).json();assert.equal(JSON.stringify(after.find(e=>e.id===expenses[0].id)),original);
  }
  // Check panel spacing as well as horizontal overflow at widths where the layout changes.
  await page.setViewportSize({width:1440,height:1050});
  await navigate(page,'dashboard');
  await page.evaluate(()=>Theme.set('dark'));
  const overview=page.locator('.overview-grid > .dash-cell');
  await overview.first().waitFor();
  for(const width of [1440,1024,390]){
   await page.setViewportSize({width,height:1050});
   await fits('Overview '+width);
   const padding=await overview.evaluateAll(cards=>cards.map(card=>{
    const style=getComputedStyle(card);
    return [parseFloat(style.paddingLeft),parseFloat(style.paddingRight)];
   }));
   assert.ok(padding.length>=3);
   for(const [left,right] of padding){
    assert.ok(left>=11&&left===right,'Overview card has even horizontal padding at '+width);
   }
  }
  await page.setViewportSize({width:1440,height:1050});await shot('overview-dark-spacing');
  await navigate(page,'budgets');
  await page.locator('#budget-list > section').first().waitFor();
  for(const width of [1440,1024,390]){
   await page.setViewportSize({width,height:1050});
   await separated('#content > .budget-period-card, #budget-list','Category budgets '+width);
   await fits('Category budgets '+width);
  }
  await page.setViewportSize({width:1440,height:1050});await shot('category-budgets-dark-spacing');
  await page.getByRole('link',{name:'Recurring expenses',exact:true}).click();
  await page.getByRole('heading',{name:'Reviewed payments',exact:true}).waitFor();
  for(const width of [1440,1024,390]){
   await page.setViewportSize({width,height:1050});
   await separated('#recurring-content > .panel','Recurring expenses '+width);
   await fits('Recurring expenses '+width);
  }
  await page.setViewportSize({width:1440,height:1050});await shot('recurring-expenses-dark-spacing');
  await navigate(page,'banks');
  await page.getByRole('link',{name:'Transfers',exact:true}).click();
  await page.getByRole('heading',{name:'Paired transfers',exact:true}).waitFor();
  await separated('#transfer-content > section','Bank transfers');

  const merchant='Example Coastal Supplies',alternate='CARD PAYMENT 842';
  for(const name of [merchant,alternate]){
   await post('expenses',{merchant:name,date:'2026-11-02',amount:10,scope:'work',category:'Other',status:'ready'});
  }
  await navigate(page,'expenses');
  await page.getByRole('button',{name:'Saved merchants',exact:true}).click();
  await page.getByRole('searchbox',{name:'Search merchants and alternate names'}).fill(merchant);
  const savedMerchant=page.locator('.merchant-list li').filter({hasText:merchant});
  await savedMerchant.getByRole('button',{name:'Edit names',exact:true}).click();
  await page.getByLabel('Add an alternate name (optional)',{exact:true}).fill(alternate);
  await page.getByRole('button',{name:'Save merchant',exact:true}).click();
  await savedMerchant.getByRole('button',{name:'Add expense',exact:true}).click();
  assert.equal(await page.locator('#expense-form #merchant').inputValue(),merchant);
  await page.locator('#close-modal').click();
  await navigate(page,'reports');
  await page.locator('#report-year').selectOption('all');
  await page.locator('#report-group').selectOption('merchant');
  const merchantSummary=page.locator('.report-summary .breakdown-list');
  assert.equal(await merchantSummary.getByText(merchant,{exact:true}).count(),1);
  assert.equal(await merchantSummary.getByText(alternate,{exact:true}).count(),0);

  await navigate(page,'quotes');await fits('dark quotes');await shot('quotes-dark');
  assert.deepEqual(errors,[]);console.log('PASS: complete server layouts, quote editor/search, client/service/time search, billing design/email navigation, 18 desktop/mobile destinations, document viewer and adviser response.');
 }catch(error){await shot('failure');throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
