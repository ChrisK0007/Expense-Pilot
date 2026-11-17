const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('server/static/app.js','utf8');
const dateSource=app.slice(app.indexOf('function dateAU('),app.indexOf('function normaliseDateInput('));
const clock=fs.readFileSync('server/static/workspace-time.js','utf8');
for(const zone of ['Australia/Brisbane','Australia/Sydney','America/Los_Angeles']){
 const context=vm.createContext({S:{timezone:zone},Intl,Date});
 vm.runInContext(dateSource+'\n'+clock+'\nglobalThis.clock=WorkspaceTime;',context);
 assert.equal(vm.runInContext("dateISO('04/05/2024')",context),'2024-05-04');
 assert.equal(vm.runInContext("dateISO('29/02/2024')",context),'2024-02-29');
 assert.equal(vm.runInContext("dateAU('2024-02-29')",context),'29/02/2024');
 for(const invalid of ['29/02/2025','31/04/2024','13/32/2024'])assert.throws(()=>vm.runInContext('dateISO('+JSON.stringify(invalid)+')',context));
 const stamp=context.clock.stamp('2026-01-01T13:30:00Z');
 assert.match(stamp,zone==='Australia/Sydney'?/02\/01\/2026/:/01\/01\/2026/);
 assert.equal(context.clock.local('2026-01-01T13:30:00Z'),zone==='Australia/Brisbane'?'2026-01-01T23:30':zone==='Australia/Sydney'?'2026-01-02T00:30':'2026-01-01T05:30');
}
console.log('PASS: AU date parsing, leap/invalid dates and workspace timestamp formatting.');
