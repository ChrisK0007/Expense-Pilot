const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',out=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{fs.mkdirSync(out,{recursive:true});for(const engine of [chromium,webkit]){
 const browser=await engine.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const post=async(path,data,method='POST')=>{const s=await(await context.request.get(url+'/api/session')).json(),r=await context.request.fetch(url+'/api/'+path,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();};
 try{
  if(engine===webkit)await context.addInitScript(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined}));
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  await page.goto(url);await page.locator('nav [data-page=trips]').click();await page.getByRole('heading',{name:'Overnight spending',exact:true}).waitFor();
  for(const [place,scope,foreign] of [['Brisbane','work',false],['Singapore','work',true],['London','business',true]]){
   const location=place+' manual '+engine.name(),merchant='Actual cafe '+location;
   await page.locator('#add-trip').click();await page.getByLabel('Location',{exact:true}).fill(location);await page.getByLabel('Workspace',{exact:true}).selectOption(scope);await page.getByLabel('Departure date',{exact:true}).fill('07/10/2026');await page.getByLabel('Return date',{exact:true}).fill('09/10/2026');await page.getByLabel('Work / business purpose',{exact:true}).fill('Synthetic overnight work');await page.getByRole('button',{name:'Save trip',exact:true}).click();await page.getByText('Overnight trip added',{exact:true}).waitFor();
   const card=()=>page.locator('.card.trip').filter({has:page.getByRole('heading',{name:location,exact:true})});
   await card().getByRole('button',{name:'+ Log actual cost (no receipt)',exact:true}).click();
   assert.equal(await page.locator('#manual-trip-cost input[type=file]').count(),0);
   const fill=async()=>{await page.getByLabel('Merchant / payee',{exact:true}).fill(merchant);await page.getByLabel('Cost date',{exact:true}).fill('08/10/2026');await page.getByLabel('Cost type',{exact:true}).selectOption('Lunch');await page.getByLabel('Actual amount paid (AUD)',{exact:true}).fill('25.50');};await fill();
   if(foreign){await page.getByText('Foreign currency (optional)',{exact:true}).click();await page.getByLabel('Original currency code',{exact:true}).fill('SGD');await page.getByLabel('Original amount paid',{exact:true}).fill('20');await page.getByLabel('Conversion source / rate / date (optional)',{exact:true}).fill('Card statement 08/10/2026');}
   await page.getByRole('button',{name:'Save actual cost',exact:true}).click();await page.getByText('Actual trip cost saved for review.',{exact:true}).waitFor();await page.locator('#modal').waitFor({state:'hidden'});
   let records=await(await context.request.get(url+'/api/expenses')).json(),record=records.find(e=>e.merchant===merchant);assert.ok(record);assert.equal(record.receipt_id,null);assert.equal(record.amount_cents,2550);assert.equal(record.status,'review');if(foreign)assert.match(record.notes,/20 SGD/);else assert.equal(record.notes,'');
   const comparison=await(await context.request.get(url+'/api/trips/'+record.trip_id+'/overnight')).json();assert.equal(comparison.claim_current,false);assert.equal(comparison.claim_cents,0);assert.equal(comparison.allowance_cents,0);assert.equal(comparison.reasonable_cents,null);
   await page.reload();await page.getByRole('button',{name:'Edit '+merchant,exact:true}).click();assert.equal(await page.getByLabel('Amount paid (AUD)',{exact:true}).inputValue(),'25.50');if(foreign)assert.match(await page.getByLabel('Notes / business purpose',{exact:true}).inputValue(),/20 SGD/);await page.locator('#close-modal').click();
   await card().getByRole('button',{name:'+ Log actual cost (no receipt)',exact:true}).click();await fill();let warned=false;page.once('dialog',async d=>{warned=true;assert.match(d.message(),/matching cost/);await d.dismiss();});await page.getByRole('button',{name:'Save actual cost',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#manual-trip-cost button[type=submit]').disabled);assert.equal(warned,true);await page.locator('#close-modal').click();records=await(await context.request.get(url+'/api/expenses')).json();assert.equal(records.filter(e=>e.merchant===merchant).length,1);
   await card().getByRole('button',{name:'Spending & allowances',exact:true}).click();await page.locator('#log-actual-trip-cost').click();await page.getByRole('heading',{name:'Log actual trip cost — no receipt needed to save',exact:true}).waitFor();await page.locator('#close-modal').click();
   await post('expenses/'+record.id,{},'DELETE');await post('trips/'+record.trip_id,{},'DELETE');await page.reload();
  }
  await page.screenshot({path:out+'/manual-overnights-'+engine.name()+'.png',fullPage:true});assert.deepEqual(errors,[]);console.log('PASS '+engine.name()+': domestic/overseas/business manual costs, optional notes, FX persistence, no automatic claim and duplicate warning.');
 }catch(e){await page.screenshot({path:out+'/manual-overnights-failure-'+engine.name()+'.png',fullPage:true});throw e;}finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1;});
