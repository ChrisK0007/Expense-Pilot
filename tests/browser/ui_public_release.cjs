const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();await page.locator('[data-page=dashboard]').waitFor();
  const paid=await page.evaluate(async()=>{
   const client=(await api('billing/clients')).find(c=>!c.archived);
   const created=await api('billing/documents',{kind:'invoice',client_id:client.id,issue_date:today(),due_date:today(),tax_mode:'exclusive',lines:[{description:'Paid status check',quantity:1,unit_price:'10',tax:'gst'}]});
   let doc=await api(`billing/documents/${created.id}`);await api(`billing/documents/${doc.id}/action`,{action:'issue',version:doc.version});doc=await api(`billing/documents/${doc.id}`);
   await api(`billing/documents/${doc.id}/payments`,{version:doc.version,amount:'11',date:today(),request_key:crypto.randomUUID()});return doc.number;
  });
  await navigate(page,'dashboard');await page.locator('.recent-invoices tr').filter({hasText:paid}).getByText('Paid',{exact:true}).waitFor();
  await navigate(page,'settings');
  await page.locator('#mail-settings').waitFor();
  assert.deepEqual(await page.locator('.settings-group > header h2').allTextContents(),['Workspace','Receipts & AI','Business & email','Bank feeds','Access & security','Data & privacy']);
  assert.equal(await page.locator('#settings-receipts #configure-ai').count(),1);
  assert.equal(await page.locator('#settings-business #mail-settings').count(),1);
  assert.equal(await page.locator('#settings-security #manage-tax-agents').count(),1);
  assert.equal(await page.locator('#settings-data #full-backup').count(),1);
  assert.doesNotMatch(await page.locator('#setup-checklist').innerText(),/backup/i);
  await page.getByRole('navigation',{name:'Settings sections'}).getByRole('button',{name:'Data & privacy',exact:true}).click();
  assert.equal(await page.evaluate(()=>document.activeElement.id),'settings-title-data');
  await page.locator('#configure-timezone').click();
  await page.locator('#timezone').fill('America/Los_Angeles');await page.getByRole('button',{name:'Save timezone',exact:true}).click();await page.getByText('Workspace timezone saved.',{exact:false}).waitFor();
  assert.equal(await page.evaluate(()=>WorkspaceTime.day(new Date('2026-01-01T01:00:00Z'))),'2025-12-31');
  await page.reload();await page.locator('#configure-timezone').click();assert.equal(await page.locator('#timezone').inputValue(),'America/Los_Angeles');
  await page.locator('#timezone').fill('Australia/Sydney');await page.getByRole('button',{name:'Save timezone',exact:true}).click();await page.getByText('Workspace timezone saved.',{exact:false}).waitFor();
  assert.deepEqual(await page.evaluate(()=>['2026-01-01T13:30:00Z','2026-07-01T13:30:00Z'].map(d=>WorkspaceTime.day(new Date(d)))),['2026-01-02','2026-07-01']);
  await page.locator('#configure-timezone').click();await page.locator('#timezone').fill('Australia/Brisbane');await page.getByRole('button',{name:'Save timezone',exact:true}).click();await page.getByText('Workspace timezone saved.',{exact:false}).waitFor();
  await page.locator('#configure-ai').click();
  for(const mode of ['none','local_ollama','remote_ollama','cloud']){
   await page.locator('#ai_mode').selectOption(mode);
   assert.equal(await page.locator('#ai-cloud').isVisible(),mode==='cloud');assert.equal(await page.locator('#ai-remote').isVisible(),mode==='remote_ollama');
  }
  await page.locator('#ai_mode').selectOption('none');await page.getByRole('button',{name:'Save AI settings',exact:true}).click();await page.getByText('AI settings saved.',{exact:true}).waitFor();
  await page.locator('#ai-test').click();await page.getByText('AI is disabled.',{exact:true}).waitFor();await page.locator('#close-modal').click();
  await page.evaluate(()=>Billing.emailDelivery());await page.getByLabel('Send me a copy of client emails',{exact:true}).check();await page.getByLabel('Copy email address',{exact:true}).fill('copies@example.test');await page.getByRole('button',{name:'Save email settings',exact:true}).click();await page.getByText('Email settings saved.',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Send me a copy of client emails',{exact:true}).isChecked(),true);assert.equal(await page.getByLabel('Copy email address',{exact:true}).inputValue(),'copies@example.test');await page.locator('#close-modal').click();
  await page.reload();await page.locator('#configure-ai').waitFor();await page.locator('#full-backup').click();await page.locator('#modal').getByLabel('Current password',{exact:true}).waitFor();await page.locator('#close-modal').click();
  await page.locator('#delete-my-account').click();await page.getByLabel('Type DELETE WORKSPACE',{exact:true}).waitFor();await page.locator('#close-modal').click();
  await page.screenshot({path:output+'/public-release-settings.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/public-release-settings-mobile.png',fullPage:true});
  const privacy=await page.request.get(url+'/privacy');assert.equal(privacy.status(),200);assert.match(await privacy.text(),/Privacy/);
  const publicPage=await browser.newPage();await publicPage.goto(url+'/about');await publicPage.getByRole('heading',{name:'Source code & licences',exact:true}).waitFor();assert.equal(await publicPage.getByRole('link',{name:'Download application source',exact:true}).getAttribute('href'),'/source');assert.equal((await publicPage.request.get(url+'/source')).status(),200);await publicPage.close();
  assert.deepEqual(errors,[]);console.log('PASS: Paid dashboard status, four AI modes, no-AI persistence, saved email copy destination, backup/deletion entry points and responsive Settings.');
 }catch(e){await page.screenshot({path:output+'/public-release-failure.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
