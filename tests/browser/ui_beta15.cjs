const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 for(const [engine,type] of [['chromium',chromium],['webkit',webkit]]){
  const browser=await type.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  context.setDefaultTimeout(25000);page.on('pageerror',e=>errors.push(e.message));fs.mkdirSync(output,{recursive:true});
  async function post(path,data,method='POST'){const s=await(await context.request.get(url+'/api/session')).json(),r=await context.request.fetch(url+'/api/'+path,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();}
  const assets=async year=>(await(await context.request.get(url+'/api/workflows/equipment?year='+year)).json()).assets;
  try{
   await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
   const prefix='Beta15 '+engine,p=await(await context.request.get(url+'/api/workflows/equipment/tax-profile/2026')).json();await post('workflows/equipment/tax-profile/2026',{version:p.version,mode:'general',confirmed:true},'PUT');
   const purchase=await post('expenses',{date:'2026-07-01',merchant:prefix+' laptop store',amount:1200,scope:'split',work_percent:50,business_percent:25,category:'Equipment',status:'ready'});
   await page.goto(url+'/#/equipment');await page.getByRole('button',{name:'Add equipment',exact:true}).click();await page.getByLabel('Linked expense (optional)',{exact:true}).selectOption(String(purchase.id));await page.getByLabel('Equipment name',{exact:true}).fill(prefix+' Laptop');
   await page.getByText('Depreciation estimate available',{exact:true}).waitFor();assert.equal(await page.getByLabel('Useful life (years)',{exact:true}).inputValue(),'2');
   assert.equal(await page.locator('#equipment-form input[type=checkbox]:visible').count(),1);
   assert.equal(await page.getByLabel('GST credit entitlement (AUD)',{exact:true}).isVisible(),false);
   await page.screenshot({path:output+'/beta15-simple-setup-'+engine+'.png'});
   await page.getByRole('button',{name:'Save equipment',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   const laptop=(await assets(2026)).find(a=>a.name===prefix+' Laptop');assert.equal(laptop.expense_id,purchase.id);assert.equal(laptop.calculation.first_use,'2026-07-01');assert.equal(laptop.calculation.life,'2');
   const laptopCard=page.locator(`[data-equipment-id="${laptop.id}"]`);assert.equal(await laptopCard.getByRole('button',{name:'Calculation settings',exact:true}).isVisible(),false);await laptopCard.getByRole('button',{name:'Edit deduction',exact:true}).click();await page.getByLabel('Amount to depreciate this year (AUD)',{exact:true}).fill('400');await page.getByRole('button',{name:'Save deduction',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});assert.equal((await assets(2026)).find(a=>a.id===laptop.id).current.amount_cents,40000);
   await page.getByRole('button',{name:'Import schedule',exact:true}).click();
   const csv='year,name,acquired,cost,opening,decline,closing,method,rate,work_percent,business_percent\n2025,'+prefix+' iPad,2025-10-22,1799,,,,manual,,0,100\n';
   await page.locator('#schedule-file').setInputFiles({name:'simple-'+engine+'.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});await page.getByRole('button',{name:'Read schedule',exact:true}).click();await page.getByRole('heading',{name:'Review imported assets',exact:true}).waitFor();
   await page.getByLabel('Treatment',{exact:true}).selectOption('fully_claimed');assert.equal(await page.locator('#import-opening-0').inputValue(),'1799');assert.equal(await page.locator('#import-decline-0').inputValue(),'1799');assert.equal(await page.locator('#import-closing-0').inputValue(),'0');assert.equal(await page.locator('.import-row details').evaluate(e=>e.open),false);assert.match(await page.locator('.import-summary').innerText(),/\$1,799.00 deduction · \$0.00 remaining/);assert.equal(await page.getByLabel('Schedule financial year',{exact:true}).locator('option:checked').innerText(),'2025–2026');
   await page.screenshot({path:output+'/beta15-simple-import-'+engine+'.png'});await page.getByRole('button',{name:'Import selected assets',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   const ipad=(await assets(2025)).find(a=>a.name===prefix+' iPad');assert.equal(ipad.current.amount_cents,179900);assert.equal(ipad.closing_cents,0);
   let card=page.locator(`[data-equipment-id="${ipad.id}"]`);await card.getByRole('button',{name:'Link receipt',exact:true}).click();
   const image=await page.evaluate(colour=>{const c=document.createElement('canvas');c.width=c.height=10;const ctx=c.getContext('2d');ctx.fillStyle=colour;ctx.fillRect(0,0,10,10);return c.toDataURL('image/png').split(',')[1];},engine==='chromium'?'#418bae':'#7938a1');
   await page.locator('#equipment_receipt_file').setInputFiles({name:'tablet-'+engine+'.png',mimeType:'image/png',buffer:Buffer.from(image,'base64')});await page.getByRole('button',{name:'Upload and link',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   let updated=(await assets(2025)).find(a=>a.id===ipad.id);assert.ok(updated.receipt_id);assert.equal(updated.expense_id,null);assert.equal(updated.current.amount_cents,179900);const rid=updated.receipt_id;assert.equal((await(await context.request.get(url+'/api/receipts?unfiled=1')).json()).some(r=>r.id===rid),false);
   const later=await post('expenses',{date:'2025-10-22',merchant:prefix+' tablet purchase',amount:1799,scope:'business',work_percent:0,business_percent:100,category:'Equipment',status:'ready'});
   await card.getByRole('button',{name:'Manage receipt',exact:true}).click();await page.getByText('Link an existing expense',{exact:true}).click();await page.getByLabel('Purchase',{exact:true}).selectOption(String(later.id));await page.getByRole('button',{name:'Link purchase',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   updated=(await assets(2025)).find(a=>a.id===ipad.id);assert.equal(updated.expense_id,later.id);assert.equal(updated.receipt_id,rid);assert.equal(updated.current.amount_cents,179900);
   await card.getByRole('button',{name:'Manage receipt',exact:true}).click();await page.screenshot({path:output+'/beta15-receipt-links-'+engine+'.png'});page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'Unlink receipt',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   updated=(await assets(2025)).find(a=>a.id===ipad.id);assert.equal(updated.receipt_id,null);assert.equal(updated.expense_id,later.id);assert.equal((await(await context.request.get(url+'/api/receipts?unfiled=1')).json()).some(r=>r.id===rid),true);
   await card.getByRole('button',{name:'Link receipt',exact:true}).click();await page.getByLabel('Saved receipt',{exact:true}).selectOption(rid);await page.getByRole('button',{name:'Link receipt',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
   await page.setViewportSize({width:390,height:844});await page.getByLabel('Financial year',{exact:true}).selectOption('2025');await page.screenshot({path:output+'/beta15-mobile-'+engine+'.png'});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);
   assert.deepEqual(errors,[]);console.log('PASS '+engine+': simple setup, saved annual amount, one-choice write-off, upload/link/unlink receipts, later purchase linking and mobile layout.');
  }catch(e){await page.screenshot({path:output+'/beta15-failure-'+engine+'.png',fullPage:true});console.error(errors);throw e;}finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
