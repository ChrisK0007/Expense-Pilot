'use strict';
const Merchants=(()=>{
 const search=q=>api('merchants?'+new URLSearchParams({q}));
 const display=expense=>expense.merchant_display||expense.merchant;

 async function suggestions(input,list,fill=false){
  const query=input.value;
  const result=await search(query);
  if(!input.isConnected||input.value!==query)return;
  list.replaceChildren(...result.items.map(merchant=>new Option(merchant.name,merchant.name)));
  if(fill&&result.match)input.value=result.match.name;
 }

 function bindInput(input,prefill=true){
  if(!owner())return;
  const list=document.createElement('datalist');
  list.id=input.id+'-merchant-list';
  input.setAttribute('list',list.id);
  input.after(list);
  let timer;
  const update=fill=>suggestions(input,list,fill).catch(()=>{});
  input.addEventListener('input',()=>{
   clearTimeout(timer);
   timer=setTimeout(()=>update(false),180);
  });
  input.addEventListener('change',()=>{
   clearTimeout(timer);
   update(true);
  });
  update(prefill);
 }

 function directory(query=''){
  modal('Saved merchants and payees',`<div class="merchant-directory">
   <div class="field"><label for="merchant-directory-search">Search merchants and alternate names</label>
   <input id="merchant-directory-search" type="search" value="${esc(query)}" autocomplete="off"></div>
   <div id="merchant-directory-results" aria-live="polite">Loading merchants…</div></div>`);
  const field=$('#merchant-directory-search'),results=$('#merchant-directory-results');
  let timer;
  async function draw(){
   const value=field.value;
   try{
    const result=await search(value);
    if(!results.isConnected||field.value!==value)return;
    results.innerHTML=result.items.length?`<ul class="merchant-list">${result.items.map(merchant=>`<li>
     <strong>${esc(merchant.name)}</strong><div class="actions">
     <button type="button" class="secondary" data-merchant-expense="${merchant.id}">Add expense</button>
     <button type="button" class="ghost" data-merchant-edit="${merchant.id}">Edit names</button>
     </div></li>`).join('')}</ul>`:'<p class="muted">No saved merchants match. Saving an expense adds its name here.</p>';
    for(const merchant of result.items){
     results.querySelector(`[data-merchant-expense="${merchant.id}"]`).onclick=()=>expenseModal(null,null,{merchant:merchant.name});
     results.querySelector(`[data-merchant-edit="${merchant.id}"]`).onclick=()=>edit(merchant.id,value).catch(e=>toast(e.message));
    }
   }catch(e){if(results.isConnected)results.textContent=e.message;}
  }
  field.oninput=()=>{clearTimeout(timer);timer=setTimeout(draw,180);};
  draw();
 }

 async function edit(id,query){
  const merchant=await api('merchants/'+id);
  modal('Edit merchant names',`<form id="merchant-name-form">
   ${field('Preferred name','name','text',merchant.name,'maxlength="200" required')}
   ${merchant.aliases.length?`<p class="muted">Also recognised as ${merchant.aliases.map(esc).join(', ')}</p>`:''}
   ${field('Add an alternate name (optional)','alias','text','','maxlength="200"')}
   <p class="footnote">Use an alternate name to group an existing merchant or bank description under this preferred name.</p>
   <div class="modal-footer"><button type="button" class="ghost" id="merchant-directory-back">Back</button><button type="submit">Save merchant</button></div></form>`);
  bind('#merchant-directory-back',()=>directory(query));
  formHandler('#merchant-name-form',async data=>{
   await api('merchants/'+id,data,'PUT');
   await refresh();
   if(page==='expenses')expensePage();
   directory(merchant.name===data.name?query:data.name);
   toast('Merchant names saved.');
  });
 }
 return {bindInput,directory,display};
})();
