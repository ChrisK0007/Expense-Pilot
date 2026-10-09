const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
async function main(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();await page.locator('[data-page=dashboard]').waitFor();
  await navigate(page,'settings');await page.getByRole('button',{name:'Configure PocketSmith',exact:false}).click();
  await page.getByLabel('Developer key',{exact:true}).fill('browser-pocketsmith-test-key');await page.locator('#feed-key-form button[type=submit]').click();await page.locator('#feed-config-form').waitFor();
  assert.equal(await page.locator('#feed-key').inputValue(),'');
  await page.locator('[data-feed-account]').check();await page.getByRole('button',{name:'Save bank feed settings',exact:true}).click();await page.getByText('Bank feed settings saved. Use Sync now on Bank accounts.',{exact:true}).waitFor();
  await navigate(page,'banks');await page.getByRole('button',{name:'Sync now',exact:true}).click();await page.getByText('4 new transactions · 4 checked',{exact:true}).waitFor();
  const purchase=page.locator('.feed-table tr').filter({hasText:'PocketSmith browser purchase'});await purchase.getByRole('button',{name:'Review',exact:true}).click();await page.getByRole('button',{name:'Create expense',exact:true}).click();
  assert.equal(await page.getByLabel('Amount paid (AUD)').inputValue(),'36.75');assert.equal(await page.getByLabel('Employment (%)').inputValue(),'0');assert.equal(await page.getByLabel('Business (%)').inputValue(),'0');await page.getByLabel('Business (%)').fill('60');await page.getByRole('button',{name:'Save expense',exact:true}).click();await page.getByText('Expense saved',{exact:true}).waitFor();
  await page.getByLabel('Bank transaction filter').selectOption('linked');await page.locator('.feed-table tr').filter({hasText:'PocketSmith browser purchase'}).waitFor();
  await page.screenshot({path:output+'/pocketsmith-linked-desktop.png',fullPage:true});
  // A receipt/manual expense can be matched instead of creating a duplicate.
  const session=await (await page.request.get(url+'/api/session')).json();
  const accounts=await (await page.request.get(url+'/api/accounts')).json(),account=accounts.find(a=>a.name==='PocketSmith browser account');
  const transactions=await (await page.request.get(url+'/api/bank-transactions?state=all')).json();
  const match=transactions.items.find(t=>t.payee==='PocketSmith browser matching receipt');
  const response=await page.request.post(url+'/api/expenses',{headers:{'X-CSRF-Token':session.csrf},data:{date:match.date,merchant:'Existing receipt match',amount:'82.19',scope:'business',percent:100,category:'Other',status:'review',account_id:account.id}});assert.equal(response.status(),200);const eid=(await response.json()).id;
  await page.getByLabel('Bank transaction filter').selectOption('review');await page.locator('.feed-table tr').filter({hasText:match.payee}).getByRole('button',{name:'Review',exact:true}).click();await page.getByText('Existing receipt match',{exact:false}).waitFor();
  await page.getByRole('button',{name:'View expense',exact:false}).click();assert.equal(await page.getByLabel('Merchant / payee').inputValue(),'Existing receipt match');await page.locator('#close-modal').click();
  await page.locator('.feed-table tr').filter({hasText:match.payee}).getByRole('button',{name:'Review',exact:true}).click();await page.getByRole('button',{name:'Match this expense',exact:true}).click();await page.getByText('Bank transaction updated.',{exact:true}).waitFor();
  const linked=await (await page.request.get(url+'/api/bank-transactions/'+match.id)).json();assert.equal(linked.transaction.expense_id,eid);
  await page.getByLabel('Bank transaction filter').selectOption('pending');await page.locator('.feed-table tr').filter({hasText:'PocketSmith browser pending'}).getByRole('button',{name:'Review',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Create expense',exact:true}).count(),0);await page.locator('#close-modal').click();
  await page.getByLabel('Bank transaction filter').selectOption('other');await page.locator('.feed-table tr').filter({hasText:'PocketSmith browser transfer'}).getByRole('button',{name:'Review',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Create expense',exact:true}).count(),0);await page.getByRole('button',{name:'Ignore transaction',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
  await page.getByLabel('Bank transaction filter').selectOption('all');await page.locator('.feed-table tr').filter({hasText:'PocketSmith browser purchase'}).waitFor();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/pocketsmith-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Connection settings',exact:true}).click();await page.locator('#feed-config-form').waitFor();await page.screenshot({path:output+'/pocketsmith-settings-mobile.png',fullPage:true});
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Disconnect',exact:true}).click();await page.getByText('PocketSmith disconnected.',{exact:true}).waitFor();
  const c=await (await page.request.get(url+'/api/pocketsmith')).json();assert.equal(c.connected,false);assert.equal(c.auto_sync,false);assert.equal(JSON.stringify(c).includes('browser-pocketsmith-test-key'),false);
  const records=await (await page.request.get(url+'/api/expenses')).json();assert.equal(records.filter(e=>e.merchant==='PocketSmith browser purchase').length,1);assert.ok(records.some(e=>e.id===eid));assert.deepEqual(errors,[]);
  console.log('PocketSmith browser checks passed: connection, selection, sync, create, receipt matching, pending/transfer guards, mobile, disconnect.');
 }catch(e){await page.screenshot({path:output+'/pocketsmith-failure.png',fullPage:true});throw e;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
