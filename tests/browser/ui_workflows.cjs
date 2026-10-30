const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));context.setDefaultTimeout(30000);
 const post=async(path,data,method='POST')=>{const s=await(await context.request.get(url+'/api/session')).json();const r=await context.request.fetch(url+'/api/'+path,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();};
 try{
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  const e=await post('expenses',{date:'2026-10-08',merchant:'Workflow Stationery',amount:100,scope:'business',work_percent:0,business_percent:100,category:'Other',status:'ready'});
  await page.goto(url+'/#/banks');await page.locator('#content h1').filter({hasText:'Bank accounts'}).waitFor();
  assert.equal(await page.locator('nav [data-page=review_tools]').count(),0);await page.locator('.section-tools summary').click();await page.getByRole('link',{name:'Reconcile payments',exact:true}).click();await page.locator('#content h1').filter({hasText:'Bank reconciliation'}).waitFor();
  await page.goto(url+'/#/expenses');await page.locator('.section-tools summary').click();await page.getByRole('link',{name:'Categorisation rules',exact:true}).click();await page.getByRole('button',{name:'Create rule',exact:true}).click();
  await page.getByLabel('Merchant (exact name)').fill('Workflow Stationery');await page.locator('#rule-form #category').selectOption('Training');await page.locator('#rule-form #work_percent').fill('80');await page.locator('#rule-form #business_percent').fill('10');await page.getByRole('button',{name:'Save rule',exact:true}).click();
  await page.getByRole('button',{name:'Preview affected expenses',exact:true}).click();await page.getByRole('heading',{name:'Preview rule application',exact:true}).waitFor();
  await page.screenshot({path:output+'/workflow-rule-preview-desktop.png',fullPage:true});await page.getByRole('button',{name:'Apply changes',exact:true}).click();
  await page.getByRole('button',{name:'Undo',exact:true}).click();await page.getByText('Undone',{exact:true}).waitFor();
  // Item editor is reachable with the same original payment; pre-fill one line
  // through the API so the review tab lists a synthetic manual expense too.
  const p=await(await context.request.get(url+`/api/workflows/items/${e.id}`)).json();
  await post(`workflows/items/${e.id}`,{token:p.token,items:[{description:'Business stationery',amount:60,category:'Other',work_percent:0,business_percent:100},{description:'Private item',amount:40,category:'Other',work_percent:0,business_percent:0}]},'PUT');
  await page.goto(url+'/#/receipt_items');await page.locator('#workflow-body tr').filter({hasText:'Workflow Stationery'}).getByRole('button',{name:'Edit items',exact:true}).click();
  await page.locator('#items-form .workflow-item').nth(1).waitFor();assert.equal(await page.locator('#items-form .workflow-item').count(),2);await page.getByRole('button',{name:'Save item breakdown',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
  for(const [parent,route,title] of [['employment','payslip_checks','Payslip checks'],['vehicles','drive_review','Drive review'],['expenses','equipment','Equipment'],['reports','annual_handover','Annual handover'],['reports','adviser_questions','Adviser questions']]){await page.goto(url+'/#/'+parent);await page.locator('.section-tools summary').click();await page.getByRole('link',{name:title,exact:true}).click();await page.locator('#workflow-body').waitFor();await page.waitForFunction(()=>!document.querySelector('#workflow-body').textContent.includes('Loading…'));assert.equal(await page.locator('#workflow-body>.error').count(),0,title);assert.ok(page.url().endsWith('/'+route));}
  await page.screenshot({path:output+'/workflow-adviser-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Ask a question',exact:true}).click();
  await page.locator('#question-new #record_id').selectOption(String(e.id));await page.getByLabel('Question',{exact:true}).fill('Check this use percentage.');await page.getByRole('button',{name:'Save question',exact:true}).click();await page.getByText('Check this use percentage.',{exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/workflow-questions-mobile.png',fullPage:true});
  await page.goto(url+'/#/attention');await page.getByRole('heading',{name:'Needs attention',exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('#attention-list')?.textContent.includes('server'));
  await page.screenshot({path:output+'/workflow-attention-mobile.png',fullPage:true});assert.equal(await page.locator('body').evaluate(el=>el.scrollWidth>innerWidth),false);
  await page.goto(url+'/#/settings');await page.getByRole('heading',{name:'Active sessions',exact:true}).waitFor();await page.getByLabel('Email me when a successful sign-in uses a new IP address').uncheck();await page.getByText('Sign-in alert preference saved.',{exact:true}).waitFor();
  assert.deepEqual(errors,[]);console.log('PASS: integrated tools, rule preview/apply/undo, receipt items, adviser questions, attention queue and sign-in controls on desktop/mobile.');
 }catch(e){await page.screenshot({path:output+'/workflow-failure.png',fullPage:true});console.error(errors);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
