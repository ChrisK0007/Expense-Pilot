// Prevent late background cookies from replacing the fresh sign-in session.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../../server/static/app.js'),'utf8');
const code=source.slice(source.indexOf('const apiRequests='),source.indexOf('\nasync function readDocument('));
const calls=[],pending=[];
const context={S:{csrf:'test-token'},FormData,AbortController,TypeError,setTimeout,clearTimeout,
 fetch:(url,init)=>{calls.push({url,init});return new Promise((resolve,reject)=>pending.push({resolve,reject}));}};
vm.runInNewContext(code,context);
const reply=()=>({ok:true,status:200,text:async()=>'{"ok":true}'});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function run(){
 const background=context.api('data/auto-backup'),logout=context.api('logout',{});
 assert.deepEqual(calls.map(c=>c.url),['/api/data/auto-backup']);
 await assert.rejects(context.api('billing/settings'),/Signing out/);
 pending.shift().resolve(reply());await background;await tick();
 assert.deepEqual(calls.map(c=>c.url),['/api/data/auto-backup','/api/logout']);
 await assert.rejects(context.api('security/sessions'),/Signing out/);
 pending.shift().resolve(reply());await logout;
 const session=context.api('session');pending.shift().resolve(reply());await session;
 // A failed background read must not strand sign-out, and a failed sign-out
 // must leave the existing page able to retry rather than block all requests.
 const failedRead=context.api('security').catch(()=>{}),failedLogout=context.api('logout',{});
 pending.shift().reject(new TypeError('Disconnected'));await failedRead;await tick();
 pending.shift().reject(new TypeError('Disconnected'));
 await assert.rejects(failedLogout,/Connection interrupted/);
 const retry=context.api('logout',{});await tick();pending.shift().resolve(reply());await retry;
 assert.equal(calls.filter(c=>c.url==='/api/logout').length,3);
 console.log('PASS: sign-out drains in-flight responses, blocks chained reads and recovers after request failures.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
