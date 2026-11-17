const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 for(const engine of [chromium,webkit]){
  const browser=await engine.launch({headless:true});
  try{
   for(const locale of ['en-US','en-AU']){
    const context=await browser.newContext({locale,timezoneId:'America/Los_Angeles',viewport:{width:1440,height:1000}});
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const post=async(path,data,method='POST')=>{const s=await(await context.request.get(url+'/api/session')).json();const r=await context.request.fetch(url+'/api/'+path,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();};
    let prior='Australia/Brisbane';
    try{
     await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
     prior=(await(await context.request.get(url+'/api/workspace/settings')).json()).timezone;
     await post('workspace/settings',{timezone:'Australia/Sydney'},'PUT');
     const name='AU dates '+engine.name()+' '+locale;
     const vehicle=await post('vehicles',{name});
     const merchant='Synthetic <img src=x onerror="window.syntheticXss=1">';
     await post('expenses',{date:'2026-10-08',merchant,amount:'12.34',scope:'business',category:'Other',percent:100});
     await page.goto(url+'/#/expenses');await page.getByText(merchant,{exact:true}).first().waitFor();
     assert.equal(await page.locator('#content img[src=x]').count(),0);
     assert.equal(await page.evaluate(()=>window.syntheticXss),undefined);
     await page.goto(url+'/#/vehicles');
     await page.locator('.card').filter({has:page.getByRole('heading',{name,exact:true})}).getByRole('button',{name:'Odometer log',exact:true}).click();
     await page.locator('#add-odometer').click();
     assert.equal(await page.locator('#reading_date').getAttribute('placeholder'),'DD/MM/YYYY');
     assert.equal(await page.locator('#reading_time').getAttribute('type'),'time');
     await page.locator('#reading_date').fill('29/02/2025');await page.locator('#reading_time').fill('10:30');
     assert.equal(await page.locator('#reading_date').evaluate(el=>el.checkValidity()),false);
     await page.locator('#reading_date').fill('29/02/2024');await page.locator('#reading_date').blur();
     await page.locator('#reading_date').focus();await page.getByRole('dialog',{name:'Choose date',exact:true}).waitFor();
     await page.locator('[data-calendar-date="2024-02-29"]').click();
     assert.equal(await page.locator('#reading_date').inputValue(),'29/02/2024');
     await page.locator('#reading').fill('50000');
     const saved=page.waitForRequest(r=>r.url().endsWith('/api/vehicles/'+vehicle.id+'/odometer')&&r.method()==='POST');
     await page.getByRole('button',{name:'Save reading',exact:true}).click();
     assert.equal((await saved).postDataJSON().recorded_local,'2024-02-29T10:30');
     await page.getByText('Odometer reading saved.',{exact:true}).waitFor();
     const records=await(await context.request.get(url+'/api/vehicles/'+vehicle.id+'/odometer')).json();
     assert.equal(records.readings[0].recorded_at,Date.parse('2024-02-28T23:30:00Z')/1000);
     const journey=await post('vehicle-journeys',{vehicle_id:vehicle.id,date:'2026-04-05',date_timezone:'Australia/Sydney',origin:'Date test start',destination:'Date test end',scope:'personal',percent:0,purpose:'',distance:10,started_at:Date.parse('2026-04-04T14:00:00Z')/1000,ended_at:Date.parse('2026-04-04T18:00:00Z')/1000});
     await page.goto(url+'/#/drive_review');await page.locator('#drive-date').fill('05/04/2026');await page.locator('[data-workflow=day]').click();
     await page.locator('.drive-check[value="'+journey.id+'"]').check();await page.locator('[data-workflow=split]').click();
     assert.equal(await page.locator('#split_date').getAttribute('placeholder'),'DD/MM/YYYY');
     await page.locator('#split_place').fill('Test stop');await page.locator('#first_distance').fill('5');await page.locator('#split_date').fill('05/04/2026');await page.locator('#split_time').fill('02:30');
     await page.getByRole('button',{name:'Preview split',exact:true}).click();await page.locator('#drive-split .error').filter({hasText:'occurs twice'}).waitFor();
     await page.locator('#occurrence').selectOption('second');
     const preview=page.waitForResponse(r=>r.url().endsWith('/api/workflows/journeys/preview')&&r.request().method()==='POST');
     await page.getByRole('button',{name:'Preview split',exact:true}).click();
     const response=await preview;assert.equal(response.status(),200);assert.equal((await response.json()).after[0].ended_at,Date.parse('2026-04-04T16:30:00Z')/1000);
     await page.goto(url+'/#/settings');await page.locator('[data-settings-jump=security]').click();await page.getByRole('heading',{name:'Active sessions',exact:true}).waitFor();
     const rendered=await page.evaluate(()=>WorkspaceTime.stamp('2026-01-01T13:30:00Z'));
     assert.match(rendered,/02\/01\/2026/);assert.match(rendered,/00:30/);
     const sessions=await(await context.request.get(url+'/api/security/sessions')).json(),current=sessions.find(s=>s.current);
     const expected=await page.evaluate(t=>WorkspaceTime.stamp(t*1000),current.last_used);
     assert.ok((await page.locator('#security-settings').innerText()).includes(expected.slice(0,10)));
     if(engine===chromium&&locale==='en-US'&&await page.locator('#verify-email').count()){
      await page.locator('#verify-email').click();await page.locator('#verification_password').fill('Browser-test-password-123');await page.getByRole('button',{name:'Send verification code',exact:true}).click();
      await page.locator('#verification_code').waitFor();
      const captured=await(await context.request.get(url+'/test/invitations')).json(),code=/code is: ([0-9]{8})/.exec(captured['owner@example.test'])[1];
      await page.locator('#verification_code').fill(code);await page.getByRole('button',{name:'Verify email',exact:true}).click();await page.getByText('Email address verified.',{exact:true}).waitFor();
      assert.equal((await(await context.request.get(url+'/api/security/email')).json()).verified,true);
     }
     await page.screenshot({path:output+'/au-dates-'+engine.name()+'-'+locale+'.png',fullPage:true});
     assert.deepEqual(errors,[]);
    }finally{await post('workspace/settings',{timezone:prior},'PUT');await context.close();}
   }
  }finally{await browser.close();}
 }
 console.log('PASS: AU date fields, retained calendar, workspace timezone/DST and mailbox verification in Chromium/WebKit with US/AU locales.');
})().catch(e=>{console.error(e);process.exitCode=1;});
