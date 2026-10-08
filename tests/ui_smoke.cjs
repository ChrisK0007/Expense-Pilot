// Real browser / API smoke test against an empty, disposable test container.
// This script never clicks Send email or sends a test email.
const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const url = process.env.APP_URL || 'http://127.0.0.1:8788';
const output = process.env.UI_OUTPUT || '/tmp/expense-pilot-ui';
async function main() {
  fs.mkdirSync(output,{recursive:true});
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const page = await browser.newPage({viewport:{width:1440,height:1050}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog', dialog=>dialog.accept());
  try {
    for(let n=0;n<30;n++) {
      try {const response=await page.request.get(url+'/api/session');if(response.ok())break;}catch{}
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    await page.goto(url);
    await page.getByLabel('Setup token').fill('browser-test-setup-token-123456789');
    await page.getByLabel('Your name').fill('Browser Test Owner');
    await page.getByLabel('Email address').fill('owner@example.test');
    await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');
    await page.getByRole('button',{name:'Create workspace'}).click();
    await page.getByRole('button',{name:'Sign in',exact:false}).waitFor();
    await page.getByLabel('Email address').fill('owner@example.test');
    await page.getByLabel('Password',{exact:true}).fill('Browser-test-password-123');
    await page.getByRole('button',{name:'Sign in',exact:false}).click();
    // Save several receipts without creating expenses, close and return later.
    await page.getByRole('button',{name:'Capture receipts',exact:false}).click();
    const receiptPdf=Buffer.from('JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Cj4+Ci9NZWRpYUJveCBbIDAuMCAwLjAgMjAwIDIwMCBdCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCnhyZWYKMCA1CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDU0IDAwMDAwIG4gCjAwMDAwMDAxMTMgMDAwMDAgbiAKMDAwMDAwMDE2MiAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDUKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3RhcnR4cmVmCjI1NgolJUVPRgo=','base64');
    await page.locator('#inbox-files').setInputFiles([{name:'receipt.pdf',mimeType:'application/pdf',buffer:receiptPdf},{name:'second.pdf',mimeType:'application/pdf',buffer:Buffer.concat([receiptPdf,Buffer.from('\n%second')])}]);
    await page.getByText('second.pdf — saved',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Done',exact:true}).click();
    await page.getByRole('button',{name:'Review & categorise',exact:false}).first().waitFor();
    await page.reload();
    await page.locator('[data-page=receipts]').click();
    await page.getByRole('button',{name:'Review & categorise',exact:false}).nth(1).waitFor();
    assert.equal(await page.getByRole('button',{name:'Review & categorise',exact:false}).count(),2);
    await page.screenshot({path:output+'/receipts-desktop.png',fullPage:true});
    await page.getByRole('button',{name:'Review & categorise',exact:false}).first().click();
    await page.getByLabel('Merchant / payee').fill('Example receipt merchant');
    await page.getByLabel('Receipt date').fill('2026-10-08');
    await page.getByLabel('Amount paid (AUD)').fill('25.50');
    await page.getByLabel('Workspace',{exact:true}).selectOption('work');
    await page.getByLabel('Category',{exact:true}).selectOption('Equipment');
    await page.getByLabel('Work / business use (%)').fill('50');
    await page.getByRole('button',{name:'Save expense',exact:true}).click();
    await page.getByText('Expense saved.',{exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Review & categorise',exact:false}).count(),1);
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:output+'/receipts-mobile.png',fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'Receipt inbox overflows');
    await page.setViewportSize({width:1440,height:1050});
    await page.locator('[data-page=dashboard]').click();
    await page.screenshot({path:output+'/overview-desktop.png',fullPage:true});
    await page.locator('[data-page=settings]').click();
    await page.getByRole('button',{name:'Business profile & branding'}).click();
    await page.getByLabel('Business / trading name').fill('Example Flight Testing');
    await page.getByLabel('ABN',{exact:true}).fill('12 345 678 901');
    await page.getByLabel('My business is registered for GST').check();
    await page.getByLabel('Business email shown on invoices').fill('billing@example.test');
    await page.getByLabel('Default payment instructions').fill('Example bank details\nUse the invoice number as your reference.');
    await page.getByRole('button',{name:'Save business details'}).click();
    await page.locator('[data-page=clients]').click();
    await page.getByRole('button',{name:'Add client',exact:false}).click();
    await page.getByLabel('Client / business name').fill('Example Aviation');
    await page.getByLabel('Billing email').fill('client@example.test');
    await page.getByRole('button',{name:'Save client'}).click();
    await page.getByText('Example Aviation',{exact:true}).waitFor();
    await page.locator('[data-page=invoices]').click();
    await page.getByRole('button',{name:'New invoice',exact:false}).click();
    await page.getByLabel('Line description').fill('Flight examiner services');
    await page.getByLabel('Quantity',{exact:true}).fill('1');
    await page.getByLabel('Unit price',{exact:true}).fill('950');
    await page.screenshot({path:output+'/invoice-editor.png',fullPage:true});
    await page.getByRole('button',{name:'Save draft'}).click();
    await page.locator('#issue-document').waitFor();
    assert.match(await page.locator('#modal').innerText(),/1,045\.00/);
    await page.locator('#issue-document').click();
    await page.getByRole('button',{name:'Record payment',exact:true}).waitFor();
    await page.getByRole('button',{name:'Record payment',exact:true}).click();
    await page.getByLabel('Amount received (AUD)').fill('200');
    await page.getByRole('button',{name:'Record payment',exact:true}).click();
    await page.locator('#modal').getByText('Part paid',{exact:true}).waitFor();
    assert.match(await page.locator('#modal').innerText(),/845\.00/);
    await page.screenshot({path:output+'/invoice-detail.png',fullPage:true});
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('link',{name:'Download PDF',exact:false}).click();
    await (await downloadPromise).saveAs(output+'/invoice.pdf');
    // Hold the sharing response until after closing the dialog and navigating away.
    // A completed background save must not reopen the invoice window.
    let releaseSharing;
    const sharingGate=new Promise(resolve=>{releaseSharing=resolve;});
    await page.route('**/api/billing/documents/*/sharing',async route=>{
      const response=await route.fetch();await sharingGate;await route.fulfill({response});
    });
    await page.getByLabel('Share this document and payment history').check();
    await page.locator('#close-modal').click();
    await page.locator('[data-page=income]').click();
    await page.getByText('Payments received',{exact:true}).waitFor();
    assert.match(await page.locator('#income-result').innerText(),/200\.00/);
    releaseSharing();
    await page.getByText('Sharing updated.',{exact:true}).waitFor();
    assert.equal(await page.locator('#modal').evaluate(dialog=>dialog.open),false,'A background sharing save reopened the closed dialog');
    await page.unroute('**/api/billing/documents/*/sharing');
    await page.locator('[data-page=quotes]').click();
    await page.getByRole('button',{name:'New quote',exact:false}).click();
    await page.getByLabel('Line description').fill('Training session');
    await page.getByLabel('Unit price',{exact:true}).fill('150');
    await page.getByRole('button',{name:'Save draft'}).click();
    await page.locator('#issue-document').click();
    await page.getByRole('button',{name:'Mark accepted'}).click();
    await page.getByRole('button',{name:'Convert to invoice'}).click();
    await page.getByRole('button',{name:'Make recurring'}).click();
    await page.getByRole('button',{name:'Create recurring schedule'}).click();
    await page.getByRole('button',{name:'Pause',exact:true}).waitFor();
    await page.locator('[data-page=settings]').click();
    await page.getByRole('button',{name:'Email delivery & templates'}).click();
    await page.getByLabel('SMTP host').fill('smtp.example.test');
    await page.getByLabel('SMTP username').fill('owner@example.test');
    await page.getByLabel('SMTP password / app password').fill('Never-a-real-secret');
    await page.getByLabel('Sender email',{exact:true}).fill('billing@example.test');
    await page.getByRole('button',{name:'Save email settings'}).click();
    await page.getByLabel('Password saved — leave blank to keep').waitFor();
    assert.equal(await page.getByLabel('Password saved — leave blank to keep').inputValue(),'');
    await page.screenshot({path:output+'/email-settings.png',fullPage:true});
    await page.locator('#close-modal').click();
    await page.locator('[data-page=invoices]').click();
    await page.getByText('Outstanding',{exact:true}).waitFor();
    await page.screenshot({path:output+'/invoices-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'New invoice',exact:false}).click();
    await page.getByLabel('Line description').fill('Mobile invoice entry');
    await page.getByLabel('Unit price',{exact:true}).fill('50');
    await page.screenshot({path:output+'/invoice-mobile.png',fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false,'Mobile page overflows horizontally');
    assert.deepEqual(errors,[],'Browser JavaScript errors');
    console.log('PASS: setup, login, business profile, client, invoice/GST, issue, partial payment, PDF, sharing, income, quote conversion, recurrence, SMTP secret retention, desktop/mobile. No real email sent.');
  } catch(error) {
    await page.screenshot({path:output+'/failure.png',fullPage:true});
    throw error;
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
