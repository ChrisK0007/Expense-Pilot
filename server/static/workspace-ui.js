'use strict';
const WorkspaceUI=(()=>{
 const icons={
  overview: "<rect x=\"3.5\" y=\"3.5\" width=\"7\" height=\"7\" rx=\"1.3\"/><rect x=\"13.5\" y=\"3.5\" width=\"7\" height=\"7\" rx=\"1.3\"/><rect x=\"3.5\" y=\"13.5\" width=\"7\" height=\"7\" rx=\"1.3\"/><rect x=\"13.5\" y=\"13.5\" width=\"7\" height=\"7\" rx=\"1.3\"/>",
  card: "<rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"2.5\"/><path d=\"M3 10h18M7 15h4\"/>",
  bank: "<path d=\"M3 9h18L12 4 3 9Zm1 11h16M6 12v5m6-5v5m6-5v5\"/>",
  inbox: "<path d=\"M3 13 6.5 5h11L21 13v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-5Zm0 0h5l2 3h4l2-3h5\"/>",
  deduct: "<rect x=\"5\" y=\"4\" width=\"14\" height=\"12\" rx=\"2\"/><path d=\"M3 18h18l-1 2H4l-1-2Zm6-9h6m-3-3v6\"/>",
  car: "<path d=\"m5 10 2-5h10l2 5M5 17v2m14-2v2M3 11a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v5H3v-5Zm4 2h1m8 0h1\"/>",
  vehicles: "<path d=\"M4 16H2v-4l3-2 3-4h8l3 4 3 2v4h-2m-4 0H8m-3-6h14\"/><circle cx=\"6\" cy=\"16\" r=\"2\"/><circle cx=\"18\" cy=\"16\" r=\"2\"/>",
  home: "<path d=\"m3 11 9-7 9 7M5 10v10h14V10M10 20v-6h4v6\"/>",
  moon: "<path d=\"M20.5 14a8.5 8.5 0 1 1-10.3-10.4A7 7 0 0 0 20.5 14ZM17 4v5m-2.5-2.5h5\"/>",
  file: "<path d=\"M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6\"/>",
  money: "<rect x=\"3\" y=\"6\" width=\"18\" height=\"12\" rx=\"2\"/><circle cx=\"12\" cy=\"12\" r=\"2.6\"/><path d=\"M6 10v4m12-4v4\"/>",
  reports: "<rect x=\"4\" y=\"3\" width=\"16\" height=\"18\" rx=\"2\"/><path d=\"M8 16v-3m4 3V9m4 7v-5\"/>",
  folder: "<path d=\"M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z\"/>",
  chat: "<path d=\"M20 11a7 7 0 0 1-7 7H9l-5 3v-5a7 7 0 0 1 4-12h5a7 7 0 0 1 7 7ZM8 10h8m-8 4h5\"/>",
  settings: "<circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4\"/><circle cx=\"12\" cy=\"12\" r=\"7\"/>",
  chev: "<path d=\"m9 6 6 6-6 6\"/>",
  down: "<path d=\"m6 9 6 6 6-6\"/>",
  bell: "<path d=\"M5 16h14l-2-3V9a5 5 0 0 0-10 0v4l-2 3Zm5 3a2 2 0 0 0 4 0\"/>",
  plus: "<path d=\"M12 5v14M5 12h14\"/>",
  filter: "<path d=\"M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-6 0v6\"/>",
  scan: "<path d=\"M4 9V5a1 1 0 0 1 1-1h4m6 0h4a1 1 0 0 1 1 1v4m0 6v4a1 1 0 0 1-1 1h-4m-6 0H5a1 1 0 0 1-1-1v-4m4-3h8\"/>",
  calendar: "<rect x=\"4\" y=\"6\" width=\"16\" height=\"14\" rx=\"2\"/><path d=\"M8 4v4m8-4v4M4 10h16m-11 5h1m4 0h1\"/>",
  dots: "<circle cx=\"5\" cy=\"12\" r=\"1\"/><circle cx=\"12\" cy=\"12\" r=\"1\"/><circle cx=\"19\" cy=\"12\" r=\"1\"/>",
  search: "<circle cx=\"10.5\" cy=\"10.5\" r=\"5.5\"/><path d=\"m15 15 4 4\"/>",
  download: "<path d=\"M12 4v11m-4-4 4 4 4-4M5 16v4h14v-4\"/>",
  upload: "<path d=\"M12 16V5m-4 4 4-4 4 4M5 16v4h14v-4\"/>",
  sparkle: "<path d=\"m11 3 2.2 5.8L19 11l-5.8 2.2L11 19l-2.2-5.8L3 11l5.8-2.2L11 3Zm8 0v4m-2-2h4m-1 11v4m-2-2h4\"/>",
  clock: "<circle cx=\"12\" cy=\"12\" r=\"8\"/><path d=\"M12 7v5l3 2\"/>",
  shield: "<path d=\"M12 3 5 6v5c0 4 3 8 7 10 4-2 7-6 7-10V6l-7-3Zm-3 9 2 2 4-4\"/>",
  user: "<circle cx=\"12\" cy=\"8\" r=\"3\"/><path d=\"M5 20v-2a7 5 0 0 1 14 0v2\"/>",
  mail: "<rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"2\"/><path d=\"m3 7 9 6 9-6\"/>",
  server: "<rect x=\"4\" y=\"4\" width=\"16\" height=\"7\" rx=\"1.5\"/><rect x=\"4\" y=\"13\" width=\"16\" height=\"7\" rx=\"1.5\"/><path d=\"M7 7.5h.5m-.5 9h.5m5-9H17m-4.5 9H17\"/>",
  screen: "<rect x=\"3\" y=\"4\" width=\"18\" height=\"13\" rx=\"2\"/><path d=\"M8 21h8m-4-4v4\"/>",
  check: "<path d=\"m5 12 5 5L19 7\"/>",
 };
 function icon(name){
  return `<svg class="workspace-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]||''}</svg>`;
 }
 const mainTabs=['dashboard','expenses','receipts','drive_review'];
 const billingPages=['invoices','quotes','clients','recurring','services','time'];
 function active(key){
  return page===key||key==='invoices'&&billingPages.includes(page)||key==='settings'&&page==='team'||
   key===pageParents[page]&&!['adviser_questions','drive_review'].includes(page);
 }
 function sections(){
  const workspace=[['dashboard','Overview','overview'],['expenses','Expenses','card']];
  const tracking=[],income=[],records=[];
  if(owner()&&Features.enabled('banks'))workspace.push(['banks','Bank accounts','bank']);
  workspace.push(['receipts','Inbox','inbox']);
  if(owner())workspace.push(['equipment','Deductions','deduct']);
  if(Features.enabled('vehicles'))tracking.push(['drive_review','Drives','car'],['vehicles','Vehicles','vehicles']);
  if(owner()&&Features.enabled('home_office'))tracking.push(['home_office','Home office','home']);
  if(Features.enabled('trips'))tracking.push(['trips','Overnight spending','moon']);
  if(owner()&&Features.enabled('business'))income.push(['invoices','Billing','file'],['income','Business income','money']);
  if(owner()&&Features.enabled('employment'))income.push(['employment','Employment','money']);
  if(owner()){
   records.push(['reports','Reports','reports'],['documents','Documents','folder'],['adviser_questions','Adviser questions','chat']);
   if(Features.enabled('tax'))records.push(['tax','Tax forecast','reports']);
  }
  return [['Workspace',workspace],['Tracking',tracking],['Income',income],['Records',records],['',[['settings','Settings','settings']]]];
 }
 function navigation(more=false){
  return sections().map(([label,items])=>{
   const visible=items.filter(([key])=>!more||!mainTabs.includes(key));
   if(!visible.length)return '';
   return `<div class="workspace-nav-group ${label?'':'workspace-nav-settings'}">
    ${label?`<p class="nav-group-label">${label}</p>`:''}
    ${visible.map(([key,title,glyph])=>{
     const current=active(key),tab=mainTabs.indexOf(key);
     return `<button type="button" ${more?'data-more-page':'data-page'}="${key}" class="${current?'active':''}" ${current?'aria-current="page"':''}
      ${!more&&tab>=0?`data-tab="${tab}"`:''}>${icon(glyph)}<span>${title}</span></button>`;
    }).join('')}
   </div>`;
  }).join('');
 }
 function moreMenu(){
  return `<dialog id="workspace-more-menu" aria-labelledby="workspace-more-title">
    <div class="modal-title"><h2 id="workspace-more-title">More</h2><button type="button" class="ghost" id="workspace-more-close" aria-label="Close navigation">✕</button></div>
    <nav aria-label="More destinations">${navigation(true)}</nav>
    <div class="more-footer"><a href="/about" target="_blank" rel="noopener">Source & licences</a><button type="button" class="secondary" id="mobile-logout">Sign out</button></div>
   </dialog>`;
 }
 function bindNavigation(logout){
  const more=$('#workspace-more-menu'),trigger=$('#workspace-more');
  bind('#workspace-more',()=>{
   more.showModal();
   trigger.setAttribute('aria-expanded','true');
  });
  more.addEventListener('close',()=>{
   trigger.setAttribute('aria-expanded','false');
   if(trigger.isConnected)trigger.focus({preventScroll:true});
  });
  bind('#workspace-more-close',()=>more.close());
  bind('#mobile-logout',logout);
  document.querySelectorAll('[data-page],[data-more-page]').forEach(button=>{
   button.onclick=()=>navigate(button.dataset.page||button.dataset.morePage);
  });
 }
 function metrics(items){
  return `<div class="page-metrics">${items.map(([label,value,note,glyph='reports'])=>`<section class="page-metric"><h2><span class="metric-icon">${icon(glyph)}</span>${esc(label)}</h2><strong>${esc(value)}</strong>${note?`<small>${esc(note)}</small>`:''}</section>`).join('')}</div>`;
 }
 function searchBar(id,label,count=''){
  return `<div class="record-toolbar"><div class="record-search"><label for="${id}">${esc(label)}</label><input type="search" id="${id}" placeholder="${esc(label)}"></div>${count?`<span class="record-count" aria-live="polite">${esc(count)}</span>`:''}</div>`;
 }
 function filterTable(id,selector,onFiltered=null){
  const input=document.getElementById(id);if(!input)return;
  const count=input.closest('.record-toolbar').querySelector('.record-count'),original=count?.textContent;
  input.oninput=()=>{const query=input.value.trim().toLocaleLowerCase(),rows=[...document.querySelectorAll(selector)];rows.forEach(row=>{row.hidden=!!query&&!row.textContent.toLocaleLowerCase().includes(query);});if(count)count.textContent=query?rows.filter(row=>!row.hidden).length+' of '+rows.length+' records':original;if(onFiltered)onFiltered(rows);};
 }
 let recordObserver=null;
 function mountRecords(){
  recordObserver?.disconnect();
  const root=$('#content');if(!root)return;
  const decorate=()=>root.querySelectorAll('table').forEach(table=>{
   if(table.closest('.document-viewer,.invoice-live-preview')||!table.tHead)return;
   const labels=[...table.tHead.rows[0].cells].map(cell=>cell.dataset.label||cell.textContent.replace(/[↑↓↕]/g,'').trim());
   table.dataset.recordCards='';table.setAttribute('role','table');table.tHead.setAttribute('role','rowgroup');
   [...table.tHead.rows].forEach(row=>{row.setAttribute('role','row');[...row.cells].forEach(cell=>cell.setAttribute('role','columnheader'));});
   [...table.tBodies].forEach(body=>{body.setAttribute('role','rowgroup');[...body.rows].forEach(row=>{row.setAttribute('role','row');[...row.cells].forEach((cell,i)=>{cell.dataset.label=labels[i]||'';cell.setAttribute('role','cell');});});});
  });
  recordObserver=new MutationObserver(decorate);recordObserver.observe(root,{childList:true,subtree:true});decorate();
 }
 return {icon,navigation,moreMenu,bindNavigation,metrics,searchBar,filterTable,mountRecords};
})();
