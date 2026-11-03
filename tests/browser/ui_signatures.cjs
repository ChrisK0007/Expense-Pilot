const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8792',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
const fixtures={
 '/s/photo/preview':'iVBORw0KGgoAAAANSUhEUgAAAFAAAACgCAIAAAAU4XzjAAAAyklEQVR4nO3PAQ0AIRDAsOP9ewYXfDJaBdua2fOS7++A2wzXGa4zXGe4znCd4TrDdYbrDNcZrjNcZ7jOcJ3hOsN1husM1xmuM1xnuM5wneE6w3WG6wzXGa4zXGe4znCd4TrDdYbrDNcZrjNcZ7jOcJ3hOsN1husM1xmuM1xnuM5wneE6w3WG6wzXGa4zXGe4znCd4TrDdYbrDNcZrjNcZ7jOcJ3hOsN1husM1xmuM1xnuM5wneE6w3WG6wzXGa4zXGe4znCd4TrDdQfPTwI//yjZBwAAAABJRU5ErkJggg==',
 '/one.png':'iVBORw0KGgoAAAANSUhEUgAAACgAAAAUCAIAAABwJOjsAAAAJElEQVR4nO3NMQEAAAgDoGlyoxtjDxRgcqnYTisWi8VisVjc8H/PAKhjC+h7AAAAAElFTkSuQmCC',
 '/two.png':'iVBORw0KGgoAAAANSUhEUgAAACgAAAAUCAIAAABwJOjsAAAAJUlEQVR4nO3NMQEAAAgDIDX5ohtjDxRgM5mGq6xisVgsFovFFQ85GgEoWQ9ZQgAAAABJRU5ErkJggg=='
};
(async()=>{
 for(const [engine,type] of [['chromium',chromium],['webkit',webkit]]){
  const browser=await type.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],imageRequests=[];
  context.setDefaultTimeout(25000);page.on('pageerror',e=>errors.push(e.message));fs.mkdirSync(output,{recursive:true});
  await context.route('https://signature.example.test/**',route=>{const request=route.request(),data=fixtures[new URL(request.url()).pathname];imageRequests.push(request.headers());return data?route.fulfill({contentType:'image/png',body:Buffer.from(data,'base64')}):route.fulfill({status:404,body:'No image'});});
  await context.route('**/api/billing/signature-paste',async route=>{await new Promise(resolve=>setTimeout(resolve,200));await route.continue();});
  async function open(){await page.goto(url+'/#/invoices');await page.getByRole('button',{name:'Email settings',exact:true}).click();await page.getByRole('button',{name:'Email templates & signature',exact:false}).click();await page.getByRole('tab',{name:'Signature',exact:true}).click();}
  const html=photo=>`<table><tr><td><img alt="Photo" style="width:90px;height:90px" src="https://signature.example.test/${photo}"></td><td style="padding-left:12px;font-family:Arial"><b>Example Pilot</b><br>Flight examiner<br><a href="mailto:pilot@example.test">Email</a><br><a href="https://social.example.test/profile"><img width="20" height="20" alt="Social one" src="https://signature.example.test/one.png"></a> <a href="https://social.example.test/second"><img style="width:20px" alt="Social two" src="https://signature.example.test/two.png"></a></td></tr></table>`;
  async function paste(value){await page.locator('#signature-editor').fill('');await page.locator('#signature-editor').evaluate((el,value)=>{const data=new DataTransfer();data.setData('text/html',value);el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));},value);}
  async function loaded(n){await page.waitForFunction(n=>[...document.querySelectorAll('#signature-editor img')].filter(img=>img.complete&&img.naturalWidth>0).length===n,n);}
  async function proportions(){
   const dimensions=await page.locator('#signature-editor img').evaluateAll(imgs=>imgs.map(img=>({width:img.getBoundingClientRect().width,height:img.getBoundingClientRect().height,src:img.getAttribute('src')})));
   assert.equal(dimensions.length,3);assert.deepEqual(dimensions.map(({width,height})=>[width,height]),[[90,180],[20,10],[20,10]]);assert(dimensions.every(img=>img.src.startsWith('https://signature.example.test/')));
   assert.equal(await page.locator('#signature-editor td').nth(1).evaluate(el=>getComputedStyle(el).paddingLeft),'12px');
  }
  try{
   const session=await(await context.request.get(url+'/api/session')).json(),login=await context.request.post(url+'/api/login',{data:{email:'owner@example.test',password:'Browser-test-password-123'},headers:{'X-CSRF-Token':session.csrf}});assert.equal(login.status(),200,await login.text());
   await open();await paste(html('s/photo/preview'));assert.equal(await page.getByRole('button',{name:'Save email templates',exact:true}).isDisabled(),true);
   await page.getByText('Signature pasted with its available images. Save email templates to keep it.',{exact:true}).waitFor();await loaded(3);await proportions();
   assert.equal(await page.locator('#signature-editor a[href="https://social.example.test/profile"] img').count(),1);
   await page.screenshot({path:output+'/beta17-signature-'+engine+'.png'});await page.getByRole('button',{name:'Save email templates',exact:true}).click();await page.getByText('Email templates saved.',{exact:true}).waitFor();await loaded(3);await proportions();await page.locator('#close-modal').click();await open();await loaded(3);await proportions();
   const saved=await(await context.request.get(url+'/api/billing/email-templates')).json();assert.match(saved.signature_html,/https:\/\/signature\.example\.test\/s\/photo\/preview/);assert.doesNotMatch(saved.signature_html,/data:image/);
   await page.setViewportSize({width:390,height:844});await loaded(3);await proportions();await page.screenshot({path:output+'/beta17-signature-mobile-'+engine+'.png'});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);await page.setViewportSize({width:1440,height:1000});
   await paste(html('unavailable.png'));await page.locator('#signature-import-status').filter({hasText:'Photo: The linked image could not load.'}).waitFor();await loaded(2);assert.equal(await page.locator('#signature-editor img').count(),3);
   await page.locator('#signature-editor').evaluate(el=>{const range=document.createRange();range.selectNode(el.querySelector('img'));const selected=getSelection();selected.removeAllRanges();selected.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
   await page.locator('#signature-image-file').setInputFiles({name:'replacement.png',mimeType:'image/png',buffer:fs.readFileSync('server/static/expense-pilot-logo.png')});await page.getByText('Image added. Save email templates to keep it.',{exact:true}).waitFor();await loaded(3);
   assert.equal(await page.locator('#signature-editor img').count(),3);assert.equal(await page.locator('#signature-editor img').evaluateAll(imgs=>imgs.filter(i=>i.src.startsWith('data:image/png;base64,')).length),1);
   await page.getByRole('button',{name:'Save email templates',exact:true}).click();await page.getByText('Email templates saved.',{exact:true}).waitFor();await loaded(3);assert.deepEqual(errors,[]);assert(imageRequests.length>=3);assert(imageRequests.every(headers=>!headers.referer));
   console.log('PASS '+engine+': linked signature URLs, original proportions and spacing, save/reopen, mobile, failed linked image and embedded replacement.');
  }catch(e){await page.screenshot({path:output+'/beta17-failure-'+engine+'.png',fullPage:true});console.error(errors);throw e;}finally{await browser.close();}
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
