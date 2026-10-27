// Exercise HTTP failures and polling without a live AI service or real-time waits.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../../server/static/app.js'),'utf8');
const code=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction bind('));
let requests=[],responses=[];
const context={S:{csrf:'synthetic-token'},FormData,AbortController,TypeError,Date,encodeURIComponent,
 setTimeout:(fn,ms)=>{if(ms===1500)queueMicrotask(fn);return 1;},clearTimeout:()=>{},
 fetch:async(url,init)=>{requests.push({url,init});const next=responses.shift();assert.ok(next,'Unexpected extra request');if(next instanceof Error)throw next;return {status:next.status,ok:next.status>=200&&next.status<300,text:async()=>{if(next.textError)throw next.textError;return next.raw??JSON.stringify(next.data);}};}};
vm.runInNewContext(code,context);
const reply=(status,data)=>({status,data}),html=status=>({status,raw:'<!DOCTYPE html><p>Private proxy details</p>'});
async function run(){
 responses=[html(524)];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===524&&e.transient&&/timed out/.test(e.message)&&!e.message.includes('Private proxy'));
 responses=[html(502)];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===502&&/HTTP 502/.test(e.message));
 responses=[html(200)];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===200&&!e.transient&&/unexpected response/.test(e.message));
 responses=[reply(403,{error:'Please sign in.'})];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===403&&e.message==='Please sign in.');
 responses=[new TypeError('Failed to fetch')];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===0&&e.transient);
 const aborted=Error('Body interrupted');aborted.name='AbortError';responses=[{status:200,textError:aborted}];await assert.rejects(context.api('receipts/example/extract',{}),e=>e.status===0&&e.transient);
 requests=[];responses=[reply(202,{job_id:'job1',status:'reading'}),html(502),reply(200,{job_id:'job1',status:'reading'}),reply(200,{job_id:'job1',status:'complete',result:{gross:3000,withheld:650}})];
 const result=await context.readDocument('example');assert.equal(result.gross,3000);assert.equal(result.withheld,650);
 assert.equal(requests.filter(r=>r.init.method==='POST').length,1,'Transient status errors must never start another AI request');
 assert.equal(requests.filter(r=>r.init.method==='GET').length,3);
 assert.equal(JSON.parse(requests[0].init.body).background,true);
 responses=[reply(202,{job_id:'job2',status:'failed',error:'Provider unavailable.',error_status:502})];await assert.rejects(context.readDocument('example'),e=>e.message==='Provider unavailable.'&&e.status===502);
 requests=[];responses=[reply(202,{job_id:'job3',status:'reading'}),html(502),html(502),html(502),html(502)];await assert.rejects(context.readDocument('example'),e=>e.status===502);assert.equal(requests.length,5,'Polling retries must be bounded');
 responses=[reply(200,{gross:3000})];assert.equal((await context.readDocument('example')).gross,3000,'Keep compatibility with a synchronous server during updates');
 console.log('PASS: HTML/JSON/network errors, bounded status retries, preserved HTTP status and one AI request per read.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
