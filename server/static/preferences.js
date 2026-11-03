'use strict';
const Features=(()=>{
 const labels={home_office:'Home office',employment:'Employment tracking',business:'Business features',trips:'Trips & meals',vehicles:'Vehicle tracking',banks:'Bank accounts & imports',tax:'Tax forecast'};
 const enabled=key=>S.features?.[key]!==false;
 const defaultScope=()=>role()==='employee'?'business':enabled('employment')?'work':'business';
 function scopes(current='',personal=true,split=false){
  const opts=[['work','Employment'],['business','Business'],...(split?[['split','Split employment / business']]:[]),...(personal?[['personal','Personal']]:[])];
  return opts.filter(([v])=>v===current||(role()==='employee'?v==='business':v==='personal'||v==='work'&&enabled('employment')||v==='business'&&enabled('business')||v==='split'&&enabled('employment')&&enabled('business')));
 }
 function settings(){
  const keys=Object.keys(labels).filter(k=>role()!=='employee'||['trips','vehicles'].includes(k));
  $('#settings-workspace-cards').insertAdjacentHTML('beforeend',`<section class="card feature-settings"><h3>Features</h3><p class="muted">Choose what appears in your workspace. Saved to your login and available on every device.</p><form id="feature-form"><div class="feature-switches">${keys.map(k=>`<label class="check"><input type="checkbox" name="${k}" ${enabled(k)?'checked':''}>${labels[k]}</label>`).join('')}</div>${role()!=='employee'?'<button type="button" class="secondary" id="employment-only">Employment expenses only</button>':''}<button type="submit">Save features</button><p class="footnote">Hidden features keep their records. Existing allocations remain in reports and tax calculations. Access permissions stay the same.</p></form></section>`);
  bind('#employment-only',()=>{for(const k of keys)$('#feature-form').elements[k].checked=k==='employment'||k==='trips';});
  formHandler('#feature-form',async(_d,f)=>{S.features=await api('features',Object.fromEntries(keys.map(k=>[k,f.elements[k].checked])),'PUT');render();toast('Feature preferences saved.');});
 }
 return {enabled,defaultScope,scopes,settings};
})();
const Splits=(()=>{
 function percentages(e){return {work:Number(e.work_percent??(e.scope==='work'?(e.percent??100):0)),business:Number(e.business_percent??(e.scope==='business'?(e.percent??100):0))};}
 function scope(e,employee=false){const p=percentages(e);return p.work&&p.business?'split':p.work?'work':p.business||employee?'business':'personal';}
 function amounts(e){if(e.reimbursed)return {work:0,business:0};const lines=JSON.parse(e.items_json||'[]');if(lines.length)return lines.reduce((a,line)=>{const p=amounts({...e,...line,items_json:'[]'});return {work:a.work+p.work,business:a.business+p.business};},{work:0,business:0});const p=percentages(e),sign=Math.sign(e.amount_cents||0),a=Math.abs(e.amount_cents||0),total=sign*Math.round(a*(p.work+p.business)/100),work=sign*Math.round(a*p.work/100);return {work,business:total-work};}
 function matches(e,scope){const p=percentages(e);return scope==='all'||scope==='split'&&p.work>0&&p.business>0||scope==='work'&&(p.work>0||e.scope==='work')||scope==='business'&&(p.business>0||e.scope==='business')||scope==='personal'&&100-p.work-p.business>0;}
 function label(e){const p=percentages(e);return p.work&&p.business?`${p.work}% Employment · ${p.business}% Business`:scopeName(e.scope);}
 function badges(e){
  const p=percentages(e);
  return p.work&&p.business?`<span class="workspace-badges"><span class="pill work">${esc(p.work)}% Employment</span> <span class="pill business">${esc(p.business)}% Business</span></span>`:`<span class="pill ${esc(e.scope)}">${esc(label(e))}</span>`;
 }
 function fields(e,prefix='',employee=false){
  const p=percentages(e);
  return `<fieldset class="allocation-fields span2" data-split-prefix="${prefix}"><legend>Expense allocation</legend><div class="allocation-grid">${!employee&&(Features.enabled('employment')||p.work)?field('Employment (%)',prefix+'work_percent','number',p.work,'required min="0" max="100" step="1"'): `<input type="hidden" id="${prefix}work_percent" name="${prefix}work_percent" value="${p.work}">`}${Features.enabled('business')||p.business||employee?field('Business (%)',prefix+'business_percent','number',p.business,'required min="0" max="100" step="1"'):`<input type="hidden" id="${prefix}business_percent" name="${prefix}business_percent" value="${p.business}">`}<div class="field"><label>Personal (%)</label><output id="${prefix}personal_percent">${100-p.work-p.business}%</output></div></div><p class="allocation-summary" id="${prefix}allocation_summary" aria-live="polite"></p></fieldset>`;
 }
 function bindFields(prefix='',amountId='amount'){
  const work=$('#'+prefix+'work_percent'),business=$('#'+prefix+'business_percent');
  const draw=()=>{const w=Number(work.value),b=Number(business.value),personal=100-w-b;work.setCustomValidity(personal<0?'Employment and business cannot total more than 100%.':'');business.setCustomValidity(personal<0?'Employment and business cannot total more than 100%.':'');$('#'+prefix+'personal_percent').textContent=personal+'%';const a=amounts({amount_cents:Math.round(Number($('#'+amountId)?.value||0)*100),work_percent:w,business_percent:b});$('#'+prefix+'allocation_summary').textContent=personal<0?'Reduce the allocation to 100% or less.':`${money(a.work)} employment · ${money(a.business)} business · ${personal}% personal`;};
  work.addEventListener('input',draw);business.addEventListener('input',draw);$('#'+amountId)?.addEventListener('input',draw);draw();
 }
 return {percentages,scope,amounts,matches,label,badges,fields,bindFields};
})();
