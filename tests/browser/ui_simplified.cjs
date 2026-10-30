// Date pickers, invoice revisions and chart labels; the server uses disposable fixtures.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 context.setDefaultTimeout(30000);page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());fs.mkdirSync(output,{recursive:true});
 const post=async(path,data,method='POST')=>{const s=await(await context.request.get(url+'/api/session')).json();const r=await context.request.fetch(url+'/api/'+path,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();};
 try{
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  const c=await post('billing/clients',{name:'Calendar test client',email:'calendar@example.test',terms:14});
  await page.goto(url+'/#/invoices');await page.getByRole('button',{name:'New invoice',exact:false}).click();await page.getByLabel('Client',{exact:true}).selectOption(String(c.id));
  const issue=page.getByLabel('Issue date',{exact:true}),due=page.getByLabel('Due date',{exact:true});
  await issue.fill('20/02/2024');await issue.press('Tab');assert.equal(await due.inputValue(),'05/03/2024');
  await issue.click();await page.locator('.date-calendar').waitFor();await page.getByRole('button',{name:'Choose 29/02/2024',exact:true}).click();assert.equal(await issue.inputValue(),'29/02/2024');assert.equal(await due.inputValue(),'14/03/2024');
  await due.fill('01/04/2024');await issue.fill('01/03/2024');await issue.press('Tab');assert.equal(await due.inputValue(),'01/04/2024');
  await page.getByLabel('Line description',{exact:true}).fill('Calendar test');await page.getByLabel('Unit price',{exact:true}).fill('100');await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByRole('button',{name:'Edit',exact:true}).click();
  await issue.fill('02/03/2024');await issue.press('Tab');assert.equal(await due.inputValue(),'01/04/2024');await page.getByRole('button',{name:'Use payment terms',exact:true}).click();assert.equal(await due.inputValue(),'16/03/2024');
  await page.setViewportSize({width:390,height:844});await issue.click();await page.locator('.date-calendar').waitFor();const box=await page.locator('.date-calendar').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=390);await page.screenshot({path:output+'/calendar-mobile.png',fullPage:true});await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.getByRole('button',{name:'Issue without email',exact:true}).click();await page.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByLabel('Invoice number',{exact:true}).fill('CALENDAR-CORRECTED');await page.getByLabel('Line description',{exact:true}).fill('Corrected calendar service');await page.getByLabel('Unit price',{exact:true}).fill('120');await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.getByRole('button',{name:'Reissue invoice',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Edit wording',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Edit invoice number',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Record payment',exact:true}).count(),0);
  await page.setViewportSize({width:1440,height:1050});await page.screenshot({path:output+'/invoice-correction-desktop.png',fullPage:true});await page.getByRole('button',{name:'Reissue invoice',exact:true}).click();await page.getByRole('button',{name:'Record payment',exact:true}).click();await page.getByRole('button',{name:'Record payment',exact:true}).click();await page.locator('#modal .billing-paid').waitFor();assert.equal(await page.locator('#modal').getByRole('button',{name:'Edit',exact:true}).count(),0);await page.locator('#close-modal').click();
  await page.goto(url+'/#/dashboard');await page.locator('.chart-point').first().waitFor();assert.deepEqual(await page.locator('nav > button[data-page]').evaluateAll(x=>x.slice(0,4).map(e=>e.dataset.page)),['dashboard','attention','receipts','expenses']);
  const point=page.locator('.point-0.chart-point').last(),expected=await point.getAttribute('data-chart-label');await point.hover();await page.locator('.chart-tooltip:visible').waitFor();assert.equal(await page.locator('.chart-tooltip').innerText(),expected);await page.screenshot({path:output+'/monthly-tooltip-desktop.png',fullPage:true});
  await point.focus();assert.equal(await page.locator('.chart-tooltip').innerText(),expected);await page.keyboard.press('Escape');assert.equal(await page.locator('.chart-tooltip').isVisible(),false);
  await page.setViewportSize({width:390,height:844});await point.click();await page.locator('.chart-tooltip:visible').waitFor();assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/monthly-tooltip-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: calendar and manual dates, automatic/manual due dates persisted, issued invoice correction/reissue, paid invoice lock, chart hover/focus/touch.');
 }catch(e){await page.screenshot({path:output+'/simplified-failure.png',fullPage:true});console.error(errors);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
