// Isolated fresh container with SETUP_TOKEN unset. The main smoke suite covers configured-token setup.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');
const url=process.env.APP_URL||'http://127.0.0.1:8790',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  for(let i=0;i<30;i++){try{if((await page.request.get(url+'/api/session')).ok())break;}catch{}await new Promise(r=>setTimeout(r,500));}
  await page.goto(url);
  await page.getByRole('button',{name:'Create workspace'}).waitFor();
  assert.equal(await page.getByLabel('Setup token',{exact:true}).count(),0);
  await page.getByLabel('Your name').fill('New owner');
  await page.getByLabel('Email address').fill('new@example.test');
  await page.getByLabel('Password',{exact:true}).fill('New-owner-password-123');
  await page.locator('#timezone').fill('Europe/London');
  await page.screenshot({path:output+'/setup-without-token.png',fullPage:true});
  await page.getByRole('button',{name:'Create workspace'}).click();
  await page.getByRole('button',{name:'Sign in',exact:false}).waitFor();
  await page.getByLabel('Email address').fill('new@example.test');await page.getByLabel('Password',{exact:true}).fill('New-owner-password-123');
  await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await navigate(page,'settings');await page.locator('#mail-settings').waitFor();
  assert.equal(await page.evaluate(()=>S.timezone),'Europe/London');
  assert.doesNotMatch(await page.locator('#setup-checklist').innerText(),/backup/i);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:output+'/new-workspace-settings-mobile.png',fullPage:true});
  await page.locator('#signout').click();await page.getByRole('button',{name:'Sign in',exact:false}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Create workspace'}).count(),0);
  assert.deepEqual(errors,[]);console.log('PASS: fresh token-free setup, login, regional setting, optional backups and owner creation closes.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
