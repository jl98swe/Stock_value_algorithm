// Synthetic sessions: weekend, tied peaks, opening sale and period-end close.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {entryUpsideMetrics, bestEntryUpsideMetrics, upsideWithDays} = require('../docs/assets/method.js');
const sessions = [['2026-10-23',100],['2026-10-26',125],['2026-10-27',125],['2026-10-28',110],['2026-10-29',150]].map(([date,close])=>({date,close}));
const trade = {entry_date:'2026-10-23',entry_price:100,exit_date:'2026-10-29'};
test('last tied high to opening sale counts trading sessions including sale day',()=>{
  const m=entryUpsideMetrics([...sessions].reverse(),trade);
  assert.equal(m.entry_upside_pct,25); assert.equal(m.entry_upside_days,2);
});
test('period-end close may be a peak on sale day',()=>{
  assert.deepEqual(entryUpsideMetrics(sessions,{...trade,exit_reason:'period_end'}),{entry_upside_pct:50,entry_upside_days:0});
});
test('open lots omit days; preliminary and later closes never enter the peak',()=>{
  assert.deepEqual(entryUpsideMetrics(sessions.map((c,i)=>({...c,preliminary:i===4})),{...trade,exit_date:null},'2026-10-29'),{entry_upside_pct:25,entry_upside_days:null});
  assert.deepEqual(entryUpsideMetrics(sessions,{...trade,exit_date:null},'2026-10-23'),{entry_upside_pct:0,entry_upside_days:null});
});
test('missing closes are missing; highest close can be below entry',()=>{
  assert.deepEqual(entryUpsideMetrics([],trade),{entry_upside_pct:null,entry_upside_days:null});
  assert(entryUpsideMetrics(sessions,{...trade,entry_price:200}).entry_upside_pct<0);
  assert.equal(bestEntryUpsideMetrics(sessions,[]).entry_upside_pct,null);
  assert.deepEqual(bestEntryUpsideMetrics(sessions,[trade,{...trade,entry_price:200}]),{entry_upside_pct:25,entry_upside_days:2});
  assert.match(upsideWithDays(25,2),/\+25 % · 2 dagar/);
  assert.equal(upsideWithDays(null,null),'–');
});
test('exported metrics match browser calculations and preserve trading data',()=>{
  const {execFileSync}=require('node:child_process');
  const script='import json,sys; from src.entry_drawdown import entry_upside_metrics; p=json.load(sys.stdin); print(json.dumps([entry_upside_metrics(p["candles"], t, p["end"]) for t in p["trades"]]))';
  const trades=[trade,{...trade,exit_reason:'period_end'},{...trade,exit_date:null},{...trade,entry_price:200},{...trade,entry_price:0}];
  const py=JSON.parse(execFileSync('python',['-c',script],{cwd:require('node:path').resolve(__dirname,'..'),input:JSON.stringify({candles:sessions,trades,end:'2026-10-29'})}));
  assert.deepEqual(py,trades.map(t=>entryUpsideMetrics(sessions,t,'2026-10-29')));
});
