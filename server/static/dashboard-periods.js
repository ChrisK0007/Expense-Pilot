'use strict';
// Compare the same elapsed calendar position in each selected year, including leap years.
const DashboardPeriods=(()=>{
 const iso=d=>d.toISOString().slice(0,10);
 function months(year,basis='calendar'){const first=basis==='financial'?6:0;return Array.from({length:12},(_,i)=>{const date=new Date(Date.UTC(year,first+i,1));return {key:iso(date).slice(0,7),label:date.toLocaleString('en-AU',{month:'short',timeZone:'UTC'}),year:date.getUTCFullYear()};});}
 function cutoff(year,basis,period,now){const start=basis==='financial'?6:0;if(period!=='ytd')return iso(new Date(Date.UTC(year,start+12,0)));const month=Number(now.slice(5,7))-1,day=Number(now.slice(8,10)),targetYear=year+(basis==='financial'&&month<6?1:0);return iso(new Date(Date.UTC(targetYear,month,Math.min(day,new Date(Date.UTC(targetYear,month+1,0)).getUTCDate()))));}
 function amounts(records,year,basis,period,now,value){const end=cutoff(year,basis,period,now);return months(year,basis).map(m=>m.key>end.slice(0,7)?null:records.filter(r=>r.date.startsWith(m.key)&&r.date<=end).reduce((total,r)=>total+value(r),0));}
 const label=(year,basis)=>basis==='financial'?`FY ${year}–${String(year+1).slice(-2)}`:String(year);
 return {months,cutoff,amounts,label};
})();
if(typeof module!=='undefined')module.exports=DashboardPeriods;
