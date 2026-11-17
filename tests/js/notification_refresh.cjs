const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function check(detached){
 let resolveFirst,calls=0;
 const first=new Promise(resolve=>{resolveFirst=resolve;}),attributes={},count={};
 const trigger={isConnected:true,setAttribute:(key,value)=>{attributes[key]=value;}};
 const list={},panel={querySelector:()=>list,matches:()=>false,addEventListener:()=>{}};
 const root={querySelector:selector=>selector==='.notification-trigger'?trigger:selector==='[popover]'?panel:count};
 const context={Date,Number,Promise,$:()=>root,owner:()=>true,today:()=> '2026-11-17',api:async path=>{
  if(path.startsWith('workflows/attention/')){calls++;return calls===1?first:{items:[{kind:'expense'}]};}
  if(path==='workspace-notifications')return {items:[]};
  if(path==='workspace-preferences')return {notifications:{receipts:{bell:true}}};
  throw Error('Unexpected request: '+path);
 }};
 vm.createContext(context);vm.runInContext(fs.readFileSync('server/static/notifications.js','utf8')+'\nglobalThis.notifications=Notifications;',context);
 const pending=context.notifications.mount();
 context.notifications.invalidate();if(detached)trigger.isConnected=false;
 resolveFirst({items:[]});await pending;
 assert.equal(calls,detached?1:2);
 if(!detached){assert.equal(count.textContent,1);assert.equal(count.hidden,false);assert.equal(attributes['aria-label'],'Notifications, 1 items needing attention');}
}
(async()=>{await check(false);await check(true);console.log('PASS: invalidated notification loads refresh connected bells and ignore detached views.');})().catch(error=>{console.error(error);process.exitCode=1;});
