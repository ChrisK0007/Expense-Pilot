'use strict';
// Apply before the stylesheet paints; no inline script or relaxed CSP required.
const Theme=(()=>{
 const key='expense-pilot-theme',media=window.matchMedia('(prefers-color-scheme: dark)');
 let choice='system';try{choice=localStorage.getItem(key)||'system';}catch{}
 if(!['light','dark','system'].includes(choice))choice='system';
 function apply(){document.documentElement.dataset.theme=choice==='system'?(media.matches?'dark':'light'):choice;document.documentElement.style.colorScheme=document.documentElement.dataset.theme;}
 function set(value){choice=['light','dark','system'].includes(value)?value:'system';try{localStorage.setItem(key,choice);}catch{}apply();document.querySelectorAll('[data-theme-select]').forEach(el=>el.value=choice);}
 function control(id='theme-choice'){return `<label class="theme-control" for="${id}"><span>Appearance</span><select id="${id}" data-theme-select aria-label="Appearance">${['light','dark','system'].map(v=>`<option value="${v}" ${choice===v?'selected':''}>${v[0].toUpperCase()+v.slice(1)}</option>`).join('')}</select></label>`;}
 document.addEventListener('change',e=>{if(e.target.matches('[data-theme-select]'))set(e.target.value);});
 media.addEventListener('change',()=>{if(choice==='system')apply();});
 window.addEventListener('storage',e=>{if(e.key===key)set(e.newValue);});apply();return {control,set};
})();
