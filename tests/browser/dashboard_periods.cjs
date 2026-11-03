const assert=require('node:assert/strict'),p=require('../../server/static/dashboard-periods.js');
assert.deepEqual(p.months(2025,'financial').map(m=>m.key),Array.from({length:12},(_,i)=>`${i<6?2025:2026}-${String((i+6)%12+1).padStart(2,'0')}`));
assert.equal(p.cutoff(2023,'calendar','ytd','2024-02-29'),'2023-02-28');
assert.equal(p.cutoff(2023,'financial','ytd','2026-02-28'),'2024-02-28');
assert.equal(p.cutoff(2025,'financial','full','2026-11-03'),'2026-06-30');
const r=[{date:'2025-07-01',n:100},{date:'2025-11-03',n:200},{date:'2025-11-04',n:300},{date:'2026-01-01',n:400}];
const v=p.amounts(r,2025,'financial','ytd','2026-11-03',r=>r.n);assert.equal(v[0],100);assert.equal(v[4],200);assert.equal(v[5],null);assert.equal(v[6],null);
console.log('PASS matched calendar/FY year-to-date and leap-day boundaries');
