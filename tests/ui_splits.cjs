// Browser checks for split allocations, compact receipt review and feature preferences.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
async function main(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await page.locator('[data-page=dashboard]').waitFor();
  assert.deepEqual(await page.locator('nav > button[data-page]').evaluateAll(elements=>elements.slice(0,3).map(el=>el.dataset.page)),['dashboard','receipts','expenses']);
  assert.equal(await page.locator('.brand small').innerText(),'a clearer view of every dollar');
  assert.equal(await page.getByText('Private workspace · AUD',{exact:true}).count(),0);
  await page.locator('[popovertarget=nav-business]').click();await page.locator('#nav-business:popover-open').waitFor();
  await page.screenshot({path:output+'/navigation-popup.png',fullPage:true});
  await page.keyboard.press('Escape');assert.equal(await page.locator('#nav-business').isVisible(),false);
  await navigate(page,'expenses');await page.getByRole('button',{name:'Add expense',exact:false}).first().click();
  await page.getByLabel('Merchant / payee').fill('Split allocation browser test');await page.getByLabel('Date',{exact:true}).fill('09/10/2026');await page.getByLabel('Amount paid (AUD)').fill('100');
  await page.getByLabel('Employment (%)').fill('30');await page.getByLabel('Business (%)').fill('20');
  assert.equal(await page.locator('#personal_percent').innerText(),'50%');assert.match(await page.locator('#allocation_summary').innerText(),/\$30\.00 employment · \$20\.00 business/);
  await page.getByLabel('Business (%)').fill('80');assert.equal(await page.getByLabel('Business (%)').evaluate(el=>el.checkValidity()),false);await page.getByLabel('Business (%)').fill('20');
  await page.locator('#expense-form').getByLabel('Review status').selectOption('ready');await page.screenshot({path:output+'/expense-split-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/expense-split-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Save expense',exact:true}).click();await page.getByText('Expense saved',{exact:true}).waitFor();
  const records=await (await page.request.get(url+'/api/expenses')).json(),record=records.find(r=>r.merchant==='Split allocation browser test');assert.equal(record.work_percent,30);assert.equal(record.business_percent,20);assert.equal(record.scope,'split');
  await page.setViewportSize({width:1440,height:1050});await page.getByRole('button',{name:'Edit Split allocation browser test',exact:true}).click();
  assert.equal(await page.getByLabel('Employment (%)').inputValue(),'30');assert.equal(await page.getByLabel('Business (%)').inputValue(),'20');await page.locator('#close-modal').click();
  await navigate(page,'reports');await page.getByLabel('Workspace',{exact:true}).selectOption('work');assert.match(await page.locator('#expense-report-body').innerText(),/Split allocation browser test/);await page.getByLabel('Workspace',{exact:true}).selectOption('business');assert.match(await page.locator('#expense-report-body').innerText(),/Split allocation browser test/);
  // Preview one captured draft: default currency stays compact and does not require confirmation.
  await navigate(page,'receipts');const drafts=page.getByRole('button',{name:'Review & categorise',exact:false});
  if(await drafts.count()){
   await drafts.first().click();assert.equal(await page.getByRole('button',{name:'Confirm currency',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'This receipt is AUD',exact:true}).count(),0);
   const box=await page.locator('.currency-compact').boundingBox();assert.ok(box.height<145);await page.screenshot({path:output+'/receipt-currency-compact.png',fullPage:true});await page.locator('#close-modal').click();
  }
  const before=await (await page.request.get(url+'/api/tax/2026')).json();
  await navigate(page,'settings');await page.getByRole('button',{name:'Employment expenses only',exact:true}).click();await page.getByRole('button',{name:'Save features',exact:true}).click();await page.getByText('Feature preferences saved.',{exact:true}).waitFor();
  assert.equal(await page.locator('[popovertarget=nav-business]').count(),0);assert.equal(await page.locator('[data-page=vehicles]').count(),0);assert.equal(await page.locator('[data-page=tax]').count(),0);
  await page.reload();await page.getByRole('heading',{name:'Recent expenses',exact:true}).waitFor();assert.equal(await page.locator('[popovertarget=nav-business]').count(),0);assert.equal(await page.getByRole('heading',{name:'Recent invoices',exact:true}).count(),0);
  const after=await (await page.request.get(url+'/api/tax/2026')).json();assert.deepEqual(after.recorded,before.recorded);
  await page.screenshot({path:output+'/employment-only-dashboard.png',fullPage:true});await navigate(page,'expenses');await page.getByRole('button',{name:'Add expense',exact:false}).first().click();
  assert.equal(await page.getByLabel('Business (%)').count(),0);assert.equal(await page.getByLabel('Employment (%)').inputValue(),'100');await page.locator('#close-modal').click();
  await navigate(page,'settings');await page.screenshot({path:output+'/feature-settings.png',fullPage:true});
  for(const label of ['Employment tracking','Business features','Trips & meals','Vehicle tracking','Bank accounts & imports','Tax forecast'])await page.locator('#feature-form').getByLabel(label,{exact:true}).check();
  await page.getByRole('button',{name:'Save features',exact:true}).click();await page.getByText('Feature preferences saved.',{exact:true}).waitFor();await navigate(page,'invoices');await page.getByRole('heading',{name:'Invoices',exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});await page.locator('[popovertarget=nav-business]').click();await page.locator('#nav-business:popover-open').waitFor();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/navigation-popup-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: split expense creation/editing, validation, reports, compact currency, sidebar popup keyboard/mobile navigation, persisted feature settings and retained tax totals.');
 }catch(e){await page.screenshot({path:output+'/splits-failure.png',fullPage:true});throw e;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
