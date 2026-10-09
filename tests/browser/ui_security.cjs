const {navigate}=require('./ui_navigation.cjs');
// Real security UI/API workflows against browser_server.py's disposable workspace.
const {chromium}=require('playwright');
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
function code(secret){
 const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';for(const c of secret)bits+=alphabet.indexOf(c).toString(2).padStart(5,'0');
 const key=Buffer.from(bits.match(/.{8}/g).map(x=>parseInt(x,2))),counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
 const digest=crypto.createHmac('sha1',key).update(counter).digest(),offset=digest.at(-1)&15;
 return ((digest.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,'0');
}
async function main(){
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(url);await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();
  await navigate(page,'expenses');await page.getByRole('button',{name:'Add expense',exact:false}).first().click();
  await page.getByLabel('Date',{exact:true}).fill('081026');await page.getByLabel('Merchant / payee').click();assert.equal(await page.getByLabel('Date',{exact:true}).inputValue(),'08/10/2026');
  await page.getByLabel('Date',{exact:true}).fill('8-10-26');await page.getByLabel('Merchant / payee').click();assert.equal(await page.getByLabel('Date',{exact:true}).inputValue(),'08/10/2026');
  await page.getByLabel('Date',{exact:true}).fill('31/2/26');await page.getByLabel('Merchant / payee').click();assert.equal(await page.getByLabel('Date',{exact:true}).evaluate(el=>el.checkValidity()),false);await page.locator('#close-modal').click();
  await navigate(page,'settings');await page.getByRole('button',{name:'Home base & receipt sorting',exact:false}).click();
  await page.getByLabel('Home base (city or suburb)').fill('Maroochydore');await page.getByRole('button',{name:'Maroochydore, QLD 4558',exact:true}).click();await page.getByText(/suburbs recognised as local/).waitFor();
  await page.getByText('Examples of nearby suburbs',{exact:true}).click();await page.screenshot({path:output+'/home-base-radius.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/home-base-mobile.png',fullPage:true});await page.setViewportSize({width:1440,height:1050});await page.getByRole('button',{name:'Save receipt preferences'}).click();
  await page.getByRole('button',{name:'Set up authenticator'}).click();await page.locator('#auth-start').getByLabel('Current password').fill('Browser-test-password-123');await page.getByRole('button',{name:'Show authenticator QR code'}).click();
  await page.getByAltText('Authenticator setup QR code').waitFor();assert.equal(await page.getByAltText('Authenticator setup QR code').evaluate(el=>el.complete&&el.naturalWidth>0),true);
  const secret=await page.locator('.auth-secret').textContent();
  await page.screenshot({path:output+'/authenticator-qr.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:output+'/authenticator-mobile.png',fullPage:true});await page.setViewportSize({width:1440,height:1050});
  await page.getByLabel('Six-digit authenticator code').fill(code(secret));await page.getByRole('button',{name:'Verify and enable 2FA'}).click();await page.getByRole('heading',{name:'Save your recovery codes'}).waitFor();
  const recovery=await page.locator('.recovery-codes code').allTextContents();assert.equal(recovery.length,10);await page.getByRole('button',{name:'I have saved my codes'}).click();await page.getByText('Enabled — sign-in requires a code from your authenticator.',{exact:true}).waitFor();
  await page.locator('#logout').click();await page.getByLabel('Email address').fill('owner@example.test');await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');await page.getByRole('button',{name:'Sign in',exact:false}).click();await page.getByRole('heading',{name:'Verify your sign-in'}).waitFor();
  assert.equal((await page.request.get(url+'/api/expenses')).status(),401);
  await page.getByLabel('Authenticator or recovery code').fill('bad-code');await page.getByRole('button',{name:'Verify and sign in'}).click();await page.getByText(/Invalid or already used code/).waitFor();
  await page.getByLabel('Authenticator or recovery code').fill(recovery[0]);await page.getByRole('button',{name:'Verify and sign in'}).click();await navigate(page,'settings');await page.getByText('9 unused recovery codes remaining.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Turn off 2FA',exact:true}).click();await page.locator('#auth-disable').getByLabel('Current password').fill('Browser-test-password-123');await page.locator('#auth-disable').getByLabel('Authenticator or recovery code').fill(recovery[1]);await page.locator('#auth-disable').getByRole('button',{name:'Turn off 2FA'}).click();await page.getByRole('button',{name:'Set up authenticator'}).waitFor();
  await page.screenshot({path:output+'/security-settings.png',fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS: automatic date formatting, invalid-date rejection, nearby suburbs, QR setup, recovery codes, 2FA login, access guard and disabling 2FA.');
 }catch(e){await page.screenshot({path:output+'/security-failure.png',fullPage:true});throw e;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
