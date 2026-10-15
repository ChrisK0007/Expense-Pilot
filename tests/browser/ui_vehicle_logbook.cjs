const {navigate}=require('./ui_navigation.cjs');
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await navigate(page,'vehicles');
  const session=await(await page.request.get(url+'/api/session')).json(),headers={'X-CSRF-Token':session.csrf};
  const created=await page.request.post(url+'/api/vehicles',{headers,data:{name:'Odometer test car'}});assert.ok(created.ok());const vid=(await created.json()).id;
  await navigate(page,'vehicles');
  const open=async()=>{await page.locator('.card').filter({has:page.getByRole('heading',{name:'Odometer test car',exact:true})}).getByRole('button',{name:'Odometer log',exact:true}).click();await page.locator('#add-odometer').waitFor();};
  await open();await page.locator('#add-odometer').click();
  const when=new Date(Date.now()-3*86400000);when.setHours(8,0,0,0);const local=await page.evaluate(t=>WorkspaceTime.local(t),when.getTime());
  await page.getByLabel('Dashboard odometer (km)').fill('52000');await page.getByLabel('Reading taken').fill(local);await page.getByLabel('Notes',{exact:true}).fill('Dashboard baseline');await page.getByRole('button',{name:'Save reading',exact:true}).click();
  await page.getByText('Odometer reading saved.',{exact:true}).waitFor();assert.match(await page.locator('#modal').innerText(),/52,000/);
  const end=when.getTime()/1000+7200,date=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Brisbane',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(end*1000));
  const trip=await page.request.post(url+'/api/vehicle-journeys',{headers,data:{vehicle_id:vid,date,origin:'Home',destination:'Airport',purpose:'Personal journey',scope:'personal',percent:0,distance:'28.6',started_at:end-1800,ended_at:end,client_ref:'5857d129-dc08-49d1-8b40-42cb9eaf89b1'}});assert.ok(trip.ok(),await trip.text());const jid=(await trip.json()).id;
  await page.locator('#close-modal').click();await navigate(page,'vehicles');await open();assert.match(await page.locator('#modal .metric').innerText(),/52,028.6/);
  await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByLabel('Dashboard odometer (km)').fill('52001');await page.getByRole('button',{name:'Save reading',exact:true}).click();await page.getByText('Odometer reading saved.',{exact:true}).waitFor();assert.match(await page.locator('#modal .metric').innerText(),/52,029.6/);
  await page.screenshot({path:output+'/vehicle-odometer.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/vehicle-odometer-mobile.png',fullPage:true});
  await page.locator('#close-modal').click();const deleted=await page.request.delete(url+'/api/vehicle-journeys/'+jid,{headers,data:{}});assert.ok(deleted.ok());await navigate(page,'vehicles');await open();assert.match(await page.locator('#modal .metric').innerText(),/52,001/);
  assert.deepEqual(errors,[]);console.log('PASS: actual odometer add/edit, complete personal kilometres, trip deletion recalculation and mobile logbook');
 }catch(e){await page.screenshot({path:output+'/vehicle-odometer-failure.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
