// Exercise the application's notification lifecycle without real-time sleeps.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../../server/static/app.js'),'utf8');
const start=source.indexOf('let toastTimer;'),end=source.indexOf('async function api(',start);
assert(start>=0&&end>start,'Notification implementation not found');
const element={textContent:'',style:{}},timers=new Map();let now=0,next=0;
const context={$:selector=>{assert.equal(selector,'#toast');return element;},setTimeout:(fn,delay)=>{const id=++next;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id)};
vm.runInNewContext(source.slice(start,end),context);
function advance(milliseconds){const target=now+milliseconds;while(true){const due=[...timers].filter(([,t])=>t.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}now=target;}
context.toast('First save');advance(5000);
context.toast('Second save');advance(500);
assert.equal(element.textContent,'Second save');assert.equal(element.style.display,'block','An earlier notification must not hide a newer one');
advance(4999);assert.equal(element.style.display,'block');
advance(1);assert.equal(element.style.display,'none');
context.toast('Third save');assert.equal(element.style.display,'block');advance(5500);assert.equal(element.style.display,'none');
console.log('PASS: each notification receives its full display duration');
