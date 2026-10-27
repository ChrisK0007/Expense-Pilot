const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const url=process.env.APP_URL||'http://127.0.0.1:8788',output=process.env.UI_OUTPUT||'/tmp/expense-pilot-ui';
// Minimal synthetic text PDF: all amounts/names are test data.
function pdf(lines){
 const stream='BT /F1 12 Tf 40 800 Td 18 TL '+lines.map(x=>'('+x.replace(/[\\()]/g,'\\$&')+') Tj T*').join(' ')+' ET';
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`];
 let out='%PDF-1.4\n',offsets=[0];objects.forEach((o,i)=>{offsets.push(Buffer.byteLength(out));out+=`${i+1} 0 obj\n${o}\nendobj\n`;});const xref=Buffer.byteLength(out);out+=`xref\n0 6\n0000000000 65535 f \n`+offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n \n').join('')+`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;return Buffer.from(out);
}
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,args:['--no-sandbox']}),context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const post=async(endpoint,data,method='POST')=>{const s=await(await context.request.get(url+'/api/session')).json();const r=await context.request.fetch(url+'/api/'+endpoint,{method,data,headers:{'X-CSRF-Token':s.csrf}});assert.equal(r.status(),200,await r.text());return r.json();};
 const get=async endpoint=>(await context.request.get(url+'/api/'+endpoint)).json();
 try{
  await post('login',{email:'owner@example.test',password:'Browser-test-password-123'});
  const connection=await post('pocketsmith',{key:'browser-pocketsmith-test-key'});
  await post('pocketsmith',{version:connection.version,start_date:'2026-01-01',accounts:[{id:connection.accounts[0].id}],auto_sync:false},'PUT');await post('pocketsmith/sync',{});
  const transactions=(await get('bank-transactions?state=all')).items,purchase=transactions.find(t=>t.payee==='PocketSmith browser purchase'),bill=transactions.find(t=>t.payee==='PocketSmith browser matching receipt');
  const previous=await post('expenses',{date:purchase.date,merchant:purchase.payee,amount:36.75,scope:'personal',work_percent:0,business_percent:0,category:'Other',status:'ready'});
  await page.goto(url+'/#/banks');await page.getByRole('button',{name:'Review suggested matches',exact:true}).click();
  await page.getByRole('heading',{name:'Match previous expenses',exact:true}).waitFor();
  assert.equal(await page.locator('[data-match]:checked').count(),1);
  await page.screenshot({path:output+'/match-previous-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('#modal').evaluate(el=>el.scrollWidth>el.clientWidth),false);await page.screenshot({path:output+'/match-previous-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Apply selected matches',exact:true}).click();await page.getByText('1 previous expenses matched.',{exact:true}).waitFor();
  assert.equal((await get('bank-transactions/'+purchase.id)).transaction.expense_id,previous.id);
  await page.setViewportSize({width:1440,height:1050});
  const session=await get('session'),upload=await context.request.post(url+'/api/receipts',{headers:{'X-CSRF-Token':session.csrf},multipart:{document_kind:'home_office',file:{name:'synthetic-internet-bill.pdf',mimeType:'application/pdf',buffer:pdf(['Synthetic internet bill',bill.payee,'Total AUD 82.19'])}}});
  assert.equal(upload.status(),200,await upload.text());const rid=(await upload.json()).id;
  await post('receipts/'+rid+'/draft',{document_kind:'home_office',merchant:bill.payee,date:bill.date,amount:82.19,home_office_kind:'internet'},'PUT');
  await page.goto(url+'/#/receipts');await page.getByRole('heading',{name:'Document inbox',exact:true}).waitFor();
  await page.locator('.receipt-card').filter({hasText:'synthetic-internet-bill.pdf'}).getByRole('button',{name:'Review & categorise',exact:false}).click();
  await page.waitForFunction(()=>document.querySelector('#receipt-bank-status')?.textContent.includes('This transaction will be linked'));
  assert.equal(await page.getByLabel('Employment (%)').isVisible(),false);assert.equal(await page.getByLabel('Business (%)').isVisible(),false);
  await page.locator('#receipt-personally-paid').check();
  await page.screenshot({path:output+'/inbox-home-office-bill-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('#modal').evaluate(el=>el.scrollWidth>el.clientWidth),false);await page.screenshot({path:output+'/inbox-home-office-bill-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Save home-office bill',exact:true}).click();await page.getByText('Home-office bill evidence saved.',{exact:true}).waitFor();
  const expense=(await get('expenses')).find(e=>e.receipt_id===rid);assert.ok(expense.account_id);assert.equal(expense.work_percent+expense.business_percent,0);assert.equal((await get('bank-transactions/'+bill.id)).transaction.expense_id,expense.id);
  await page.setViewportSize({width:1440,height:1050});await page.goto(url+'/#/employment');await page.getByRole('button',{name:'Upload payslip / statement',exact:true}).click();
  const slip=pdf(['PAYSLIP','Employer: Synthetic Aviation Pty Ltd','Payment date: 16/10/2026','Pay period: 01/10/2026 to 14/10/2026','This pay Gross taxable pay: AUD 3000.00','This pay PAYG tax withheld: AUD 650.00','Net pay: AUD 2350.00','YTD gross: AUD 21000.00','YTD tax: AUD 4550.00']);
  await page.locator('#inbox-files').setInputFiles({name:'synthetic-payslip.pdf',mimeType:'application/pdf',buffer:slip});
  await page.locator('#capture-progress').getByText('synthetic-payslip.pdf — ready to categorise',{exact:true}).waitFor();
  assert.equal((await get('employment')).length,0);
  await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.locator('.receipt-card').filter({hasText:'synthetic-payslip.pdf'}).getByRole('button',{name:'Review & categorise',exact:false}).click();
  await page.getByRole('heading',{name:'Review employment document',exact:true}).waitFor();
  assert.equal(await page.getByLabel('Gross taxable pay (AUD)',{exact:true}).inputValue(),'3000');assert.equal(await page.getByLabel('PAYG tax withheld (AUD)',{exact:true}).inputValue(),'650');
  assert.equal(await page.getByLabel('Payment date',{exact:true}).inputValue(),'16/10/2026');
  await page.screenshot({path:output+'/payslip-review-desktop.png',fullPage:true});await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('#modal').evaluate(el=>el.scrollWidth>el.clientWidth),false);await page.screenshot({path:output+'/payslip-review-mobile.png',fullPage:true});
  await page.locator('#income-reviewed').check();await page.getByRole('button',{name:'Save employment income',exact:true}).click();await page.getByText('Employment income saved. Original available in Employment income.',{exact:true}).waitFor();
  const income=await get('employment');assert.equal(income.length,1);assert.equal(income[0].gross_cents,300000);assert.equal(income[0].withheld_cents,65000);assert.ok(income[0].receipt_id);assert.equal((await get('expenses')).filter(e=>e.receipt_id===income[0].receipt_id).length,0);
  await page.goto(url+'/#/employment');await page.getByRole('button',{name:'View document',exact:true}).click();await page.locator('#receipt-viewer img').waitFor();
  await page.screenshot({path:output+'/payslip-source-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: document inbox, local payslip extraction/review, income source, home-office filing, automatic bank links and previous-expense matching on desktop/mobile.');
 }catch(e){console.error('Browser errors:',errors);await page.screenshot({path:output+'/document-inbox-failure.png',fullPage:true});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
