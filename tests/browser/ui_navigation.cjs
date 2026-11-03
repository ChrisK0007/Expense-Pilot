async function navigate(page,key){
 page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(30000);
 if(['quotes','time','recurring','services'].includes(key)){await navigate(page,'invoices');await page.locator('.billing-tabs [data-billing-page="'+key+'"]').click();return;}if(key==='budgets'){await navigate(page,'expenses');await page.getByRole('link',{name:'Budgets',exact:true}).click();return;}if(key==='documents'){await navigate(page,'reports');await page.locator('.section-tools summary').click();await page.getByRole('link',{name:'Documents',exact:true}).click();return;}
 const target=page.locator(`[data-page="${key}"]`);await target.waitFor({state:'attached'});
 const group=target.locator('xpath=ancestor::details');if(await group.count()&&!await target.isVisible())await group.locator('summary').click();
 const popup=await target.evaluate(el=>el.closest('[popover]')?.id||'');
 if(popup&&!await target.isVisible())await page.locator(`[popovertarget="${popup}"]`).click();
 await target.click();
}
module.exports={navigate};
