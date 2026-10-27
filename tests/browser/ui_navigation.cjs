async function navigate(page,key){
 page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(30000);
 const target=page.locator(`[data-page="${key}"]`);await target.waitFor({state:'attached'});
 const popup=await target.evaluate(el=>el.closest('[popover]')?.id||'');
 if(popup&&!await target.isVisible())await page.locator(`[popovertarget="${popup}"]`).click();
 await target.click();
}
module.exports={navigate};
