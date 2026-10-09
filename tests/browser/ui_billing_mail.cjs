// Called by the disposable smoke test; browser_server.py captures all SMTP delivery.
const assert=require('node:assert/strict');
const {navigate}=require('./ui_navigation.cjs');

async function billingMailChecks(page,output){
  await navigate(page,'settings');
  await page.getByRole('button',{name:'Email templates',exact:false}).click();
  await page.getByRole('tab',{name:'Invoices',exact:true}).waitFor();
  assert.equal(await page.getByLabel('Invoice subject',{exact:true}).inputValue(),'Invoice from {business}');
  await page.getByLabel('Invoice email body',{exact:true}).click();
  await page.getByRole('button',{name:'Invoice outstanding amount',exact:true}).click();
  assert.match(await page.getByLabel('Invoice email body',{exact:true}).inputValue(),/\{balance\}/);
  await page.getByRole('button',{name:'Use default wording',exact:true}).click();
  for(const [tab,heading] of [['Quotes','Quote'],['Reminders','Auto overdue invoice reminder'],['Receipts','Paid in full receipt'],['Statements','Outstanding invoices statement']]){
    await page.getByRole('tab',{name:tab,exact:true}).click();
    await page.getByRole('heading',{name:heading,exact:true}).waitFor();
  }
  await page.screenshot({path:output+'/statement-email-templates.png',fullPage:true});
  await page.getByRole('tab',{name:'Signature',exact:true}).click();
  const editor=page.getByRole('textbox',{name:'Email signature',exact:true});
  await editor.fill('Browser Test Owner');
  await editor.press('ControlOrMeta+A');
  await page.getByRole('button',{name:'Bold',exact:true}).click();
  await page.getByRole('button',{name:'Save email templates',exact:true}).click();
  await page.getByText('Email templates saved.',{exact:true}).waitFor();
  const templates=await page.evaluate(()=>api('billing/email-templates'));
  assert.match(templates.signature_html,/<(?:b|strong)>Browser Test Owner<\/(?:b|strong)>/);
  await page.screenshot({path:output+'/email-signature.png',fullPage:true});
  await page.locator('#close-modal').click();
  await page.getByRole('button',{name:'Automatic reminders',exact:false}).click();
  assert.equal(await page.getByLabel('Enable automatic reminder emails').isChecked(),false);
  await page.getByLabel('Days before due (0 to skip)').fill('5');
  await page.getByRole('button',{name:'Save reminder schedule',exact:true}).click();
  await page.getByText('Reminder schedule saved.',{exact:true}).waitFor();
  assert.equal((await page.evaluate(()=>api('billing/reminder-settings'))).before_days,5);
  await navigate(page,'invoices');
  const row=page.locator('#billing-table tbody tr').filter({hasText:'INV-0001'});
  await row.getByRole('button',{name:'Open ↗',exact:true}).click();
  await page.getByRole('button',{name:'Email payment receipt',exact:true}).click();
  assert.equal(await page.getByLabel('Subject',{exact:true}).inputValue(),'$200.00 payment receipt');
  assert.match(await page.getByLabel('Message',{exact:true}).inputValue(),/outstanding balance of \$845\.00/);
  await page.getByLabel('Include email signature').uncheck();
  assert.equal(await page.locator('#compose-signature').isVisible(),false);
  await page.getByLabel('Include email signature').check();
  await page.screenshot({path:output+'/payment-receipt-email.png',fullPage:true});
  await page.getByRole('button',{name:'Send email',exact:true}).click();
  await page.locator('#modal').getByText('Sent / mail server accepted',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Send reminder',exact:true}).click();
  assert.match(await page.getByLabel('Subject',{exact:true}).inputValue(),/is due/);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.locator('#close-modal').click();
  await navigate(page,'clients');
  await page.getByRole('button',{name:'Statement ↗',exact:true}).first().click();
  assert.match(await page.locator('.statement-summary').innerText(),/845\.00/);
  await page.getByLabel('Statement type',{exact:true}).selectOption('outstanding');
  await page.locator('.statement-summary').filter({hasText:/Total outstanding\s+\$845\.00/}).waitFor();
  await page.screenshot({path:output+'/client-statement.png',fullPage:true});
  await page.getByRole('button',{name:'Email statement',exact:true}).click();
  assert.equal(await page.getByLabel('Subject',{exact:true}).inputValue(),'Statement of Accounts');
  await page.getByRole('button',{name:'Send statement',exact:true}).click();
  await page.locator('#modal').getByText('Sent / mail server accepted',{exact:true}).waitFor();
  await page.locator('#close-modal').click();
}

module.exports={billingMailChecks};
