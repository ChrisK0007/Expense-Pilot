const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const url=process.env.APP_URL||'http://127.0.0.1:8788';
const output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1050}});
 const page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const post=async(endpoint,data,method='POST')=>{
  const session=await(await context.request.get(url+'/api/session')).json();
  const response=await context.request.fetch(url+'/api/'+endpoint,{method,data,headers:{'X-CSRF-Token':session.csrf}});
  assert.equal(response.status(),200,await response.text());return response.json();
 };
 try{
  for(let attempt=0;attempt<30;attempt++){
   try{if((await context.request.get(url+'/api/server-info')).ok())break;}catch(error){if(attempt===29)throw error;}
   await new Promise(resolve=>setTimeout(resolve,500));
  }
  if((await(await context.request.get(url+'/api/server-info')).json()).setup){
   await post('setup',{token:'browser-test-setup-token-123456789',name:'Test owner',email:'owner@example.test',password:'Browser-test-password-123'});
  }
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  const session=await(await context.request.get(url+'/api/session')).json();
  const receipt=await context.request.post(url+'/api/receipts',{headers:{'X-CSRF-Token':session.csrf},multipart:{file:{name:'test-home-office-bill.png',mimeType:'image/png',buffer:fs.readFileSync(path.resolve(__dirname,'../../server/static/expense-pilot-logo.png'))}}});
  assert.equal(receipt.status(),200,await receipt.text());
  const bill=await post('expenses',{date:'2026-10-01',merchant:'Home-office test internet',amount:'100',scope:'work',work_percent:100,business_percent:0,category:'Phone & internet',status:'ready',receipt_id:(await receipt.json()).id});
  await page.goto(url+'/#/home_office');
  await page.getByRole('heading',{name:'Home office',exact:true}).waitFor();
  await page.locator('#home-office-year').selectOption('2026');
  await page.locator('#home-office-add').click();
  await page.getByLabel('Work date',{exact:true}).fill('08/10/2026');
  await page.getByLabel('Workspace',{exact:true}).selectOption('work');
  await page.getByLabel('Start time',{exact:true}).fill('09:00');
  await page.getByLabel('Finish time',{exact:true}).fill('17:00');
  await page.getByLabel('Breaks (minutes)').fill('60');
  await page.getByLabel('Work performed').fill('Test client preparation');
  await page.getByRole('button',{name:'Save hours',exact:true}).click();
  await page.getByText('Home-office hours saved.',{exact:true}).waitFor();
  await page.locator('#home-office-bill').click();
  await page.getByLabel('Expense',{exact:true}).selectOption(String(bill.id));
  await page.getByLabel('Cost type',{exact:true}).selectOption('internet');
  await page.getByLabel('Calculation / apportionment evidence').fill('Recorded internet use for client preparation.');
  await page.getByRole('button',{name:'Save bill classification',exact:true}).click();
  await page.getByText('Bill linked to home-office records.',{exact:true}).waitFor();
  await page.locator('#home-office-method').click();
  await page.getByLabel('Calculation method').selectOption('fixed');
  for(const name of ['eligible','hours_complete','costs_complete','cost_internet']) await page.locator(`#home-office-method-form [name="${name}"]`).check();
  await page.getByRole('button',{name:'Save annual method',exact:true}).click();
  await page.getByText('Annual method saved.',{exact:true}).waitFor();
  await page.getByText('Included in recorded tax forecast',{exact:true}).waitFor();
  const annual=await(await context.request.get(url+'/api/home-office/2026')).json();
  assert.equal(annual.minutes.work,420);assert.equal(annual.hourly.work,490);assert.equal(annual.active,true);
  await page.reload();await page.getByText('Test client preparation',{exact:true}).waitFor();
  await page.locator('#home-office-allowance').click();
  await page.getByLabel('Payment date').fill('09/10/2026');
  await page.getByLabel('Employer',{exact:true}).fill('Test employer');
  await page.getByLabel('Allowance received (AUD)').fill('50');
  await page.getByRole('button',{name:'Save allowance',exact:true}).click();
  await page.getByText('Allowance saved.',{exact:true}).waitFor();
  assert.equal((await(await context.request.get(url+'/api/home-office/2026')).json()).allowance_income_cents,0);
  await page.screenshot({path:output+'/home-office-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:output+'/home-office-mobile.png',fullPage:true});
  await page.locator('#home-office-history').click();await page.getByRole('heading',{name:'Home-office edit history'}).waitFor();
  await page.locator('#close-modal').click();
  assert.equal((await context.request.get(url+'/api/home-office/2026/export')).status(),200);
  const original=(await(await context.request.get(url+'/api/expenses')).json()).find(e=>e.id===bill.id);
  assert.equal(original.amount_cents,10000);
  assert.deepEqual(errors,[]);
  console.log('PASS: home-office diary, method checks, fixed-rate amount, allowance income, reload, history, CSV and mobile layout');
 }catch(error){console.error('Browser errors:',errors);await page.screenshot({path:output+'/home-office-failure.png',fullPage:true});throw error;}
 finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
