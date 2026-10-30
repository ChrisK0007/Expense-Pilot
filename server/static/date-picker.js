'use strict';
// Keep the AU text field as the source of truth, with a calendar alongside it.
(()=>{
 let input=null,popup=null,month='',restoreFocus=false;
 const iso=d=>d.toISOString().slice(0,10),day=value=>new Date(value+'T12:00:00Z');
 function close(){if(input){input.removeAttribute('aria-controls');input.setAttribute('aria-expanded','false');}popup?.remove();popup=null;input=null;}
 function position(){if(!popup||!input?.isConnected)return close();const r=input.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight||r.right<0||r.left>innerWidth)return close();popup.style.left=Math.max(8,Math.min(innerWidth-popup.offsetWidth-8,r.left))+'px';popup.style.top=Math.max(8,r.bottom+popup.offsetHeight+8>innerHeight?r.top-popup.offsetHeight-6:r.bottom+6)+'px';}
 function choose(value){const target=input;target.value=dateAU(value);normaliseDateInput(target);target.dispatchEvent(new Event('input',{bubbles:true}));target.dispatchEvent(new Event('change',{bubbles:true}));close();restoreFocus=true;target.focus({preventScroll:true});restoreFocus=false;}
 function draw(focusDate=''){
  let selected='';try{selected=dateISO(input.value);}catch(_){}
  const first=day(month+'-01'),year=first.getUTCFullYear(),m=first.getUTCMonth(),count=new Date(Date.UTC(year,m+1,0,12)).getUTCDate(),offset=(first.getUTCDay()+6)%7;
  const allowed=value=>(!input.dataset.min||value>=input.dataset.min)&&(!input.dataset.max||value<=input.dataset.max);
  const preferred=focusDate||selected||today(),tabDate=preferred.startsWith(month)&&allowed(preferred)?preferred:Array.from({length:count},(_,i)=>month+'-'+String(i+1).padStart(2,'0')).find(allowed);
  const names=Array.from({length:12},(_,i)=>new Date(Date.UTC(2026,i,1)).toLocaleString('en-AU',{month:'long',timeZone:'UTC'}));
  popup.innerHTML=`<div class="calendar-heading"><button type="button" class="ghost" data-month-step="-1" aria-label="Previous month">‹</button><select aria-label="Calendar month">${names.map((n,i)=>`<option value="${i}" ${i===m?'selected':''}>${n}</option>`).join('')}</select><input type="number" aria-label="Calendar year" min="1" max="9999" value="${year}"><button type="button" class="ghost" data-month-step="1" aria-label="Next month">›</button></div><div class="calendar-grid">${['Mo','Tu','We','Th','Fr','Sa','Su'].map(n=>`<span class="calendar-weekday">${n}</span>`).join('')}${'<span></span>'.repeat(offset)}${Array.from({length:count},(_,i)=>{const value=month+'-'+String(i+1).padStart(2,'0');return `<button type="button" class="calendar-day ${value===selected?'selected':''}" data-calendar-date="${value}" aria-label="Choose ${dateAU(value)}" ${value===today()?'aria-current="date"':''} ${allowed(value)?'':'disabled'} tabindex="${value===tabDate?0:-1}">${i+1}</button>`;}).join('')}</div><div class="calendar-footer"><button type="button" class="ghost" data-today ${allowed(today())?'':'disabled'}>Today</button><button type="button" class="ghost" data-close>Close</button></div>`;
  popup.querySelectorAll('[data-calendar-date]').forEach(b=>{b.onclick=()=>choose(b.dataset.calendarDate);b.onkeydown=e=>{const shift={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[e.key];if(shift){e.preventDefault();const next=day(b.dataset.calendarDate);next.setUTCDate(next.getUTCDate()+shift);const value=iso(next);if(allowed(value)&&value.slice(0,4)!=='0000'){month=value.slice(0,7);draw(value);}}};});
  popup.querySelectorAll('[data-month-step]').forEach(b=>b.onclick=()=>{const next=day(month+'-01');next.setUTCMonth(next.getUTCMonth()+Number(b.dataset.monthStep));if(next.getUTCFullYear()>0&&next.getUTCFullYear()<=9999){month=iso(next).slice(0,7);draw();}});
  const monthSelect=popup.querySelector('select'),yearInput=popup.querySelector('input');
  const changeMonth=()=>{const y=Number(yearInput.value);if(Number.isInteger(y)&&y>=1&&y<=9999){month=String(y).padStart(4,'0')+'-'+String(Number(monthSelect.value)+1).padStart(2,'0');draw();}};
  monthSelect.onchange=changeMonth;yearInput.onchange=changeMonth;
  popup.querySelector('[data-today]').onclick=()=>choose(today());popup.querySelector('[data-close]').onclick=()=>{const target=input;close();restoreFocus=true;target.focus();restoreFocus=false;};
  position();if(focusDate)popup.querySelector(`[data-calendar-date="${focusDate}"]`)?.focus();
 }
 function open(target){
  if(restoreFocus||target.disabled||target.readOnly)return;
  if(input===target&&popup)return;
  close();input=target;let value=today();try{value=dateISO(target.value)||value;}catch(_){}
  month=value.slice(0,7);popup=document.createElement('div');popup.className='date-calendar';popup.id='date-calendar';popup.setAttribute('role','dialog');popup.setAttribute('aria-label','Choose date');popup.setAttribute('popover','manual');target.parentElement.append(popup);target.setAttribute('aria-controls',popup.id);target.setAttribute('aria-expanded','true');popup.showPopover?.();draw();
 }
 document.addEventListener('focusin',e=>{if(e.target.matches('[data-date=au]'))open(e.target);else if(popup&&!popup.contains(e.target))close();});
 document.addEventListener('click',e=>{if(e.target.matches('[data-date=au]'))open(e.target);});
 document.addEventListener('pointerdown',e=>{if(popup&&e.target!==input&&!popup.contains(e.target))close();},true);
 document.addEventListener('input',e=>{if(e.target===input)close();});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&popup){e.preventDefault();e.stopPropagation();close();}else if(e.altKey&&e.key==='ArrowDown'&&e.target.matches('[data-date=au]')){e.preventDefault();open(e.target);popup?.querySelector('.calendar-day[tabindex="0"]')?.focus();}},true);
 document.addEventListener('close',close,true);window.addEventListener('resize',position);window.addEventListener('scroll',e=>{if(popup&&!popup.contains(e.target))position();},true);
 new MutationObserver(()=>{if(input&&!input.isConnected)close();}).observe(document.documentElement,{childList:true,subtree:true});
})();
