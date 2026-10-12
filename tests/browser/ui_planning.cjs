const {navigate}=require('./ui_navigation.cjs');
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();await page.locator('[data-page="budgets"]').waitFor();
  const session=await(await page.request.get(url+'/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const post=async(path,data)=>{const r=await page.request.post(url+'/api/'+path,{headers,data});assert.ok(r.ok(),await r.text());return r.json();};
  const vid=(await post('vehicles',{name:'Planning test car'})).id;
  await post('expenses',{date:'2026-10-12',merchant:'Planning fuel receipt',amount:'120',scope:'personal',category:'Vehicle expenses',work_percent:0,business_percent:0,status:'ready',vehicle_id:vid});
  await navigate(page,'budgets');await page.getByLabel('Budget month',{exact:true}).fill('2026-10');await page.locator('#add-budget').click();await page.getByLabel('Category',{exact:true}).selectOption('Vehicle expenses');await page.getByLabel('Budget amount (AUD)').fill('100');await page.getByRole('button',{name:'Save budget',exact:true}).click();await page.getByText('$20.00 over budget',{exact:true}).waitFor();
  await page.screenshot({path:output+'/category-budgets.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/category-budgets-mobile.png',fullPage:true});await page.setViewportSize({width:1440,height:1050});
  await navigate(page,'vehicles');await page.locator('#log-journey').click();await page.getByLabel('Vehicle',{exact:true}).selectOption(String(vid));await page.getByLabel('Journey workspace').selectOption('personal');await page.getByLabel('Journey date').fill('12/10/2026');await page.getByLabel('Distance (km)',{exact:true}).fill('12.345');assert.equal(await page.locator('#purpose').getAttribute('required'),null);await page.getByRole('button',{name:'Save journey',exact:true}).click();await page.getByText('Journey saved',{exact:true}).waitFor();
  const journeys=await(await page.request.get(url+'/api/vehicle-journeys')).json();assert.equal(journeys.find(j=>j.vehicle_id===vid).distance_m,12345);assert.equal(journeys.find(j=>j.vehicle_id===vid).purpose,'');await page.getByText('12.3 km',{exact:true}).waitFor();
  await post('vehicle-journeys',{vehicle_id:vid,date:'2026-10-12',origin:'Home',destination:'Airport',purpose:'Flight test',scope:'business',percent:100,distance:'100'});
  await navigate(page,'vehicles');const card=page.locator('.card').filter({has:page.getByRole('heading',{name:'Planning test car',exact:true})});await card.getByRole('button',{name:'Compare vehicle methods',exact:true}).click();await page.getByLabel('Financial year',{exact:true}).selectOption('2026');await page.locator('#comparison-settings').click();await page.getByLabel('Employment use (%)').fill('20');await page.getByLabel('Business use (%)').fill('30');await page.getByLabel('Logbook start').fill('01/07/2026');await page.getByLabel('Logbook end').fill('22/09/2026');await page.getByRole('button',{name:'Save assumptions',exact:true}).click();await page.getByText('$60.00',{exact:true}).waitFor();assert.match(await page.locator('#modal').innerText(),/\$91.00/);assert.match(await page.locator('#modal').innerText(),/Planning fuel receipt/);
  await page.screenshot({path:output+'/vehicle-method-comparison.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/vehicle-method-comparison-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: monthly budgets, overspend, blank personal purpose, one-decimal display, precise storage and vehicle comparison');
 }catch(e){await page.screenshot({path:output+'/planning-failure.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
