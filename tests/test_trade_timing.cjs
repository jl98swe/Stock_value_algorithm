// Synthetic examples: exchange holiday, weekend, pending data, and sale at next open.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {tradeTimingMetrics, entryUpsideMetrics, upsideWithDays} = require('../docs/assets/method.js');
const candles = [['2026-11-04',100],['2026-11-05',120],['2026-11-06',110],['2026-11-09',90],['2026-11-10',95],['2026-11-12',105],['2026-11-13',108]].map(([date,close])=>({date,close}));
const trade = {entry_date:'2026-11-04',entry_price:100,exit_signal_date:'2026-11-05',exit_date:'2026-11-06',exit_reason:'score'};
test('holding time counts observed sessions from zero, including sale day',()=>{
 assert.equal(tradeTimingMetrics(candles,trade).holding_trading_days,2);
 assert.equal(tradeTimingMetrics(candles,{...trade,exit_date:null,valuation_date:'2026-11-12'}).holding_trading_days,5);
 assert.equal(tradeTimingMetrics(candles,{...trade,exit_date:trade.entry_date}).holding_trading_days,0);
 const peak=entryUpsideMetrics(candles,trade);
 assert.equal(upsideWithDays(peak.entry_upside_pct,peak.entry_upside_days,peak.entry_upside_peak_days),'+20 % · 1/1 dagar');
});
test('five sessions start after signal close, not sale price or calendar days',()=>{
 const m=tradeTimingMetrics([...candles].reverse(),{...trade,exit_price:80});
 assert(Math.abs(m.post_sell_5d_pct + 10)<1e-10);
 assert.equal(tradeTimingMetrics(candles.slice(0,-1),trade).post_sell_5d_pct,null);
 assert.equal(tradeTimingMetrics(candles.map((c,i)=>({...c,preliminary:i===6})),trade).post_sell_5d_pct,null);
 assert.equal(tradeTimingMetrics(candles,trade,'2026-11-12').post_sell_5d_pct,null);
});
test('open lots, reference exits, absent signals and invalid prices stay blank',()=>{
 for (const t of [{...trade,exit_date:null},{...trade,exit_reason:'period_end'},{...trade,exit_signal_date:null}]) assert.equal(tradeTimingMetrics(candles,t).post_sell_5d_pct,null);
 for (const close of [null,0,-1,NaN]) assert.equal(tradeTimingMetrics(candles.map((c,i)=>i===6 ? {...c,close}:c),trade).post_sell_5d_pct,null);
 assert.equal(tradeTimingMetrics(candles.filter(c=>c.date!==trade.exit_signal_date),trade).post_sell_5d_pct,null);
});
test('Python aggregate metrics match browser for completed and partial windows',()=>{
 const {execFileSync} = require('node:child_process');
 const trades=[trade,{...trade,exit_date:null,valuation_date:'2026-11-12'},{...trade,exit_reason:'period_end'},{...trade,exit_signal_date:null}];
 const script='import json,sys; from src.entry_drawdown import trade_timing_metrics; p=json.load(sys.stdin); print(json.dumps([trade_timing_metrics(p["candles"],t,p["end"]) for t in p["trades"]]))';
 const py=JSON.parse(execFileSync('python',['-c',script],{input:JSON.stringify({candles,trades,end:'2026-11-13'})}));
 assert.deepEqual(py,trades.map(t=>tradeTimingMetrics(candles,t,'2026-11-13')));
});

test('opening executions retain sale-session duration before its close is available',()=>{
 const t={...trade,holding_trading_days:2};
 assert.equal(tradeTimingMetrics(candles.slice(0,2),t).holding_trading_days,2);
 assert.equal(entryUpsideMetrics(candles.slice(0,2),t).entry_upside_days,1);
});
