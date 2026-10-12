const {navigate}=require('./ui_navigation.cjs');
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const check=async(key,title)=>{
  await page.waitForURL('**/#/'+key);
  await page.locator('.topline > span:first-child').filter({hasText:title}).waitFor();
  await page.locator('#content h1').waitFor();
  assert.equal(await page.title(),title+' · Expense Pilot');
 };
 try{
  // A bookmarked page is retained through sign-in and a full document reload.
  await page.goto(url+'/#/expenses');
  await page.getByLabel('Email address').fill('owner@example.test');
  await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');
  await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await check('expenses','Expenses');await page.reload();await check('expenses','Expenses');
  await navigate(page,'invoices');await check('invoices','Invoices');
  await page.locator('[data-billing-page="recurring"]').click();await check('recurring','Recurring invoices');
  await page.reload();await check('recurring','Recurring invoices');
  await page.locator('[data-billing-page="quotes"]').click();await check('quotes','Quotes');
  await page.goBack();await check('recurring','Recurring invoices');
  await page.goForward();await check('quotes','Quotes');
  // In-place rendering after saves must not create phantom Back entries.
  await page.evaluate(()=>render());await page.goBack();await check('recurring','Recurring invoices');
  await page.goForward();await check('quotes','Quotes');
  await navigate(page,'settings');await page.locator('#manage-tax-agents').click();
  await check('settings/tax-agent-access','Settings / Tax agent access');
  await page.reload();await check('settings/tax-agent-access','Settings / Tax agent access');
  await page.locator('#back-to-settings').click();await check('settings','Settings');
  await navigate(page,'budgets');await page.locator('#add-budget').click();
  assert.equal(await page.locator('#modal').evaluate(d=>d.open),true);
  await page.goBack();await check('settings','Settings');
  assert.equal(await page.locator('#modal').evaluate(d=>d.open),false);
  await page.goForward();await check('budgets','Category budgets');
  await page.reload();await check('budgets','Category budgets');
  for(const [key,title] of [['receipts','Receipt inbox'],['trips','Trips & meals'],['vehicles','Vehicles'],['banks','Bank accounts'],['employment','Employment income'],['tax','Tax forecast'],['reports','Expense reports'],['clients','Clients'],['services','Services & prices'],['time','Billable time'],['income','Income report']]){
   await navigate(page,key);await check(key,title);await page.reload();await check(key,title);
  }
  await page.goto(url+'/#/missing-page');await check('dashboard','Dashboard');
  // Feature restrictions apply to direct links too, without deleting any records.
  await navigate(page,'settings');await page.locator('#feature-form [name="business"]').uncheck();
  await page.locator('#feature-form [type="submit"]').click();await page.getByText('Feature preferences saved.',{exact:true}).waitFor();
  await page.goto(url+'/#/invoices');await check('dashboard','Dashboard');
  await navigate(page,'settings');await page.locator('#feature-form [name="business"]').check();
  await page.locator('#feature-form [type="submit"]').click();await page.getByText('Feature preferences saved.',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await navigate(page,'invoices');await page.locator('[data-billing-page="recurring"]').click();await check('recurring','Recurring invoices');
  await page.goBack();await check('invoices','Invoices');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:output+'/page-routing-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1050});
  await page.locator('#logout').click();await page.locator('#login-form').waitFor();
  await page.goBack();await page.locator('#login-form').waitFor();assert.equal(await page.locator('.shell').count(),0);
  assert.deepEqual(errors,[]);console.log('PASS: page URLs, sign-in deep links, refresh, Back/Forward, nested settings, feature guards and mobile navigation');
 }catch(e){console.error('Browser errors:',errors);await page.screenshot({path:output+'/routing-failure.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
