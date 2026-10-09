// Regression: create/reuse overnight trips from the receipt dialog itself.
const {chromium}=require('playwright');
const {navigate}=require('./ui_navigation.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8788';
const output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:1100}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
 let previousPrefs,headers;
 fs.mkdirSync(output,{recursive:true});
 const api=async(path,data,method='post')=>{
  const result=data===undefined?await page.request.get(url+'/api/'+path):await page.request[method](url+'/api/'+path,{headers,data});
  assert.ok(result.ok(),await result.text());return result.json();
 };
 try{
  let session=await api('session');headers={'X-CSRF-Token':session.csrf};
  if(session.setup)await api('setup',{token:'browser-test-setup-token-123456789',name:'Browser Test Owner',email:'owner@example.test',password:'Browser-test-password-123'});
  await api('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  session=await api('session');headers={'X-CSRF-Token':session.csrf};
  previousPrefs=await api('receipt-preferences');
  await api('receipt-preferences',{home_base:'',home_aliases:'',scope:'work'},'put');
  await page.goto(url);await navigate(page,'receipts');
  const upload=async(color,when,amount)=>{
   const encoded=await page.evaluate(color=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=32;const c=canvas.getContext('2d');c.fillStyle=color;c.fillRect(0,0,32,32);return canvas.toDataURL().split(',')[1];},color);
   const result=await page.request.post(url+'/api/receipts',{headers,multipart:{file:{name:'trip-review-'+color+'.png',mimeType:'image/png',buffer:Buffer.from(encoded,'base64')}}});
   assert.ok(result.ok(),await result.text());const {id}=await result.json();
   await api('receipts/'+id+'/draft',{merchant:'Receipt trip '+color,date:when,amount,currency:'AUD',category:'Meals',meal:'Breakfast',merchant_city:'Cawdor',scope:'work'},'put');
   return id;
  };
  const first=await upload('cyan','2025-10-08',29.50),second=await upload('magenta','2025-10-09',36.69);
  const initialTrips=(await api('trips')).length,initialExpenses=(await api('expenses')).length;
  assert.equal((await api('receipt-trip-proposals')).filter(g=>g.receipts.some(r=>r.id===first)).length,0,'No automatic away inference without home base');
  await navigate(page,'receipts');
  const open=async name=>page.locator('.receipt-card').filter({has:page.getByRole('heading',{name,exact:true})}).getByRole('button',{name:'Review & categorise',exact:false}).click();
  await open('Receipt trip cyan');
  await page.getByLabel('Amount paid (AUD)',{exact:true}).fill('30.08');
  await page.getByLabel('What was it for?').fill('Includes payment service fee');
  // Saving a meal with no trip opens the review instead of the previous error.
  await page.getByRole('button',{name:'Save expense',exact:true}).click();
  await page.getByRole('heading',{name:'Review draft overnight trip',exact:true}).waitFor();
  assert.equal(await page.locator('#receipt-trip-review select[name=scope]').count(),0);
  assert.equal(await page.locator('.proposal-receipt').count(),2);
  assert.equal(await page.locator('#proposal_amount_0').inputValue(),'30.08');
  assert.equal(await page.locator('#proposal_notes_0').inputValue(),'Includes payment service fee');
  assert.equal((await api('trips')).length,initialTrips);
  assert.equal((await api('expenses')).length,initialExpenses);
  await page.locator('#close-modal').click();
  assert.equal((await api('trips')).length,initialTrips,'Closing a draft must not create a trip');
  await navigate(page,'receipts');await open('Receipt trip cyan');
  await page.locator('#review-receipt-trip').click();
  await page.getByRole('heading',{name:'Review draft overnight trip',exact:true}).waitFor();
  await page.getByLabel('Trip purpose').fill('Overnight flying duties');
  await page.screenshot({path:output+'/receipt-create-trip.png',fullPage:true});
  const acceptTrip=async label=>{
   const [saved]=await Promise.all([
    page.waitForResponse(response=>response.url()===url+'/api/receipt-trip-proposals/accept'&&response.request().method()==='POST'),
    page.getByRole('button',{name:label,exact:true}).click()
   ]);
   assert.ok(saved.ok(),await saved.text());
   await page.locator('#modal').waitFor({state:'hidden'});
  };
  await acceptTrip('Accept trip & meals');
  let trips=await api('trips'),expenses=await api('expenses');
  assert.equal(trips.length,initialTrips+1);
  const trip=trips.find(t=>t.location==='Cawdor'&&t.scope==='work'&&t.start==='2025-10-08');assert.ok(trip);
  const meals=expenses.filter(e=>e.receipt_id===first||e.receipt_id===second);
  assert.equal(meals.length,2);assert.ok(meals.every(e=>e.trip_id===trip.id));
  assert.equal(meals.reduce((sum,e)=>sum+e.amount_cents,0),6677);
  // A subsequent matching receipt reuses that trip, even without a home base.
  const third=await upload('lime','2025-10-09',12.50);
  await navigate(page,'receipts');await open('Receipt trip lime');
  await page.locator('#receipt-to-trip').click();
  await page.getByRole('heading',{name:'Review meals for existing trip',exact:true}).waitFor();
  assert.equal(await page.locator('#receipt-trip-review select[name=scope]').count(),0);
  assert.equal(await page.getByLabel('Trip purpose').inputValue(),'Overnight flying duties');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:output+'/receipt-existing-trip-mobile.png',fullPage:true});
  await acceptTrip('Accept meals');
  assert.equal((await api('trips')).length,initialTrips+1);
  assert.equal((await api('expenses')).find(e=>e.receipt_id===third).trip_id,trip.id);
  await page.setViewportSize({width:1280,height:1100});
  await navigate(page,'expenses');await page.getByLabel('Financial year').selectOption('all');await page.getByLabel('Search expenses').fill('Receipt trip cyan');
  assert.match(await page.locator('#expense-table').innerText(),/Receipt trip cyan/,'Accepted meals are also available in Expenses');
  assert.doesNotMatch(await page.locator('#count').innerText(),/tax agent/i);
  // Review both attached and unattached matches without losing unsaved edits.
  const attached=await upload('navy','2026-10-08',44.35),candidate=await upload('orange','2026-10-08',44.35);
  const payload={date:'2026-10-08',amount:44.35,scope:'work',category:'Equipment',percent:100,status:'ready',notes:'Compare this expense before attaching'};
  const withReceipt=await api('expenses',{...payload,merchant:'Already filed matching expense',receipt_id:attached});
  const withoutReceipt=await api('expenses',{...payload,merchant:'Unattached matching expense'});
  await api('receipts/'+candidate+'/draft',{category:'Equipment',meal:'',work_percent:40,business_percent:50,scope:'split'},'put');
  await navigate(page,'receipts');
  assert.equal(await page.getByText('All receipts',{exact:true}).count(),0);
  await open('Receipt trip orange');
  assert.equal(await page.locator('#receipt_scope').count(),0);
  await page.getByLabel('Amount paid (AUD)',{exact:true}).fill('46.00');
  const attachedLink=page.locator(`.match-view-expense[data-eid="${withReceipt.id}"]`);
  assert.equal(await attachedLink.evaluate(el=>getComputedStyle(el).cursor),'pointer');
  await attachedLink.click();await page.getByRole('heading',{name:'Existing expense',exact:true}).waitFor();
  assert.match(await page.locator('#expense-match-viewer').innerText(),/Already filed matching expense/);
  assert.equal(await page.locator('#attach-viewed-expense').count(),0);
  await page.getByRole('button',{name:'Back to receipt',exact:true}).click();
  assert.equal(await page.getByLabel('Amount paid (AUD)',{exact:true}).inputValue(),'46.00');
  assert.equal(await page.getByLabel('Employment (%)').inputValue(),'40');assert.equal(await page.getByLabel('Business (%)').inputValue(),'50');
  await page.locator(`.match-view-expense[data-eid="${withoutReceipt.id}"]`).click();
  await page.getByRole('heading',{name:'Existing expense',exact:true}).waitFor();
  await page.screenshot({path:output+'/receipt-existing-expense-link.png',fullPage:true});
  const beforeAttach=(await api('expenses')).length;
  await page.getByRole('button',{name:'Attach receipt to this expense',exact:true}).click();
  await page.getByText('Receipt attached. No duplicate expense created.',{exact:true}).waitFor();
  assert.equal((await api('expenses')).length,beforeAttach);
  assert.equal((await api('expenses')).find(e=>e.id===withoutReceipt.id).receipt_id,candidate);
  assert.equal(await page.locator('.receipt-card').filter({hasText:'Receipt trip orange'}).count(),0);
  // Percentages alone determine the workspace of a newly filed receipt.
  const splitReceipt=await upload('teal','2026-10-08',20);
  await api('receipts/'+splitReceipt+'/draft',{category:'Equipment',meal:''},'put');
  await navigate(page,'receipts');await open('Receipt trip teal');
  await page.getByLabel('Employment (%)').fill('40');await page.getByLabel('Business (%)').fill('50');
  await page.getByRole('button',{name:'Save expense',exact:true}).click();await page.getByText('Expense saved.',{exact:true}).waitFor();
  const split=(await api('expenses')).find(e=>e.receipt_id===splitReceipt);
  assert.equal(split.scope,'split');assert.equal(split.work_percent,40);assert.equal(split.business_percent,50);
  assert.deepEqual(errors,[]);
  console.log('PASS: receipt-to-trip review, ambiguous suburb/missing home base, grouped meals, edited amounts/notes, cancelled draft, existing-trip reuse, draft-only inbox, matching expense links, percentage allocation and mobile layout.');
 }catch(error){await page.screenshot({path:output+'/receipt-trip-failure.png',fullPage:true});throw error;}
 finally{if(previousPrefs)await api('receipt-preferences',previousPrefs,'put');await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
