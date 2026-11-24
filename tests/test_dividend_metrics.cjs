// Synthetic examples: ex-date price falls, changing peaks, and cash outside ownership.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const m = require('../docs/assets/method.js');
const candles = [100,99,94,103,96,96,95].map((close,i)=>({date:`2026-11-${String(2+i).padStart(2,'0')}`,close}));
const dividends = [{date:'2026-11-02',amount:50},{date:'2026-11-04',amount:6},{date:'2026-11-06',amount:10},{date:'2026-11-07',amount:1},{date:'2026-11-08',amount:100}];
const trade = {entry_date:'2026-11-02',entry_price:100,exit_date:'2026-11-07',exit_signal_date:'2026-11-02'};
const approx = (actual,expected)=>assert(Math.abs(actual-expected)<1e-9,`${actual} != ${expected}`);
test('cash dividends move the low and peak; purchase and exit closes retain their boundaries',()=>{
 const loss=m.entryDrawdownMetrics(candles,trade,null,dividends);
 approx(loss.entry_drawdown_pct,-1); assert.equal(loss.entry_drawdown_days,1);
 const gain=m.entryUpsideMetrics(candles,trade,null,dividends);
 approx(gain.entry_upside_pct,12);assert.equal(gain.entry_upside_peak_days,4);assert.equal(gain.entry_upside_days,1);
 approx(m.entryUpsideMetrics(candles,{...trade,exit_date:null,valuation_date:'2026-11-07'},null,dividends).entry_upside_pct,13);
 approx(m.tradeTimingMetrics(candles,trade,null,dividends).post_sell_5d_pct,13);
});
test('Python exports and browser agree for dividends, missing prices, open lots and references',()=>{
 const trades=[trade,{...trade,exit_reason:'period_end'},{...trade,exit_date:null,valuation_date:'2026-11-06'},{...trade,entry_price:0}];
 const sample={candles:[...candles,{date:'2026-11-09',close:999,preliminary:true}],dividends,trades,end:'2026-11-09'};
 const script='import json,sys; from src.entry_drawdown import entry_drawdown_metrics,entry_upside_metrics,trade_timing_metrics; p=json.load(sys.stdin); print(json.dumps([[f(p["candles"],t,p["end"],p["dividends"]) for f in (entry_drawdown_metrics,entry_upside_metrics,trade_timing_metrics)] for t in p["trades"]]))';
 const py=JSON.parse(execFileSync('python',['-c',script],{input:JSON.stringify(sample)}));
 assert.deepEqual(py,trades.map(t=>[m.entryDrawdownMetrics,m.entryUpsideMetrics,m.tradeTimingMetrics].map(f=>f(sample.candles,t,sample.end,dividends))));
});
test('summary uses the same dividends and index is not counted twice',()=>{
 const variants={standard:{closed_trades:[trade]},_dividends:dividends};
 const rows=m.fullHistoryRows({candles},variants,{candles});
 approx(rows.find(r=>r.id==='standard').entry_upside_pct,12);
 approx(rows.find(r=>r.id==='omxsgi').entry_upside_pct,3);
});
