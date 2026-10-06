const assert = require('node:assert/strict');
const {selectTrades, compound, periodStart, closedDrawdown, equityMetrics, holdCurve, closedEquity} = require('../docs/assets/method.js');
// Synthetic trades, including entry outside the window and an open position.
const variant = {
  closed_trades: [
    {entry_date:'2024-10-05',exit_date:'2025-11-01',return_pct:20},
    {entry_date:'2025-10-06',exit_date:'2026-02-01',return_pct:10},
    {entry_date:'2026-03-01',exit_date:'2026-10-05',return_pct:-10},
    {entry_date:'2026-04-01',exit_date:'2026-10-06',return_pct:30}
  ],
  open_lots: [{entry_date:'2025-01-01'}, {entry_date:'2026-05-01',current_return_pct:50}]
};
const selected=selectTrades(variant,'2025-10-05','2026-10-05');
assert.equal(selected.closed.length,2); assert.equal(selected.open.length,1);
assert(Math.abs(compound(selected.closed) + 1) < 1e-10);
assert.equal(compound([]),null);
assert.equal(periodStart('2026-10-05','1','2019-09-02'),'2025-10-05');
assert.equal(periodStart('2026-10-05','3','2019-09-02'),'2023-10-05');
assert.equal(periodStart('2026-10-05','5','2019-09-02'),'2021-10-05');
assert.equal(periodStart('2024-02-29','1','2019-09-02'),'2023-02-28');
assert.equal(periodStart('2026-10-05','all','2019-09-02'),'2019-09-02');
console.log('Method period checks passed.');

assert.equal(closedDrawdown([],[],[]),null);
const fall=closedDrawdown([{date:'2026-01-01',close:100},{date:'2026-01-02',close:80},{date:'2026-01-03',close:120}], [{entry_date:'2026-01-01',exit_date:'2026-01-03',entry_price:100,return_pct:19.4}],[]);
assert(fall < -20 && fall > -21);

const changes=[.01,-.02,.03,0,.015];
let equity=1;
const metrics=equityMetrics(changes.map(r=>equity*=1+r));
const mean=changes.reduce((a,b)=>a+b,0)/changes.length;
const std=Math.sqrt(changes.reduce((sum,r)=>sum+(r-mean)**2,0)/(changes.length-1));
assert(Math.abs(metrics.sharpe_ratio - mean/std*Math.sqrt(252))<1e-9);
assert(Math.abs(metrics.max_drawdown_pct+2)<1e-9);
assert.equal(equityMetrics([1,1,1]).sharpe_ratio,null);
assert.equal(equityMetrics([]).sharpe_ratio,null);
const dates=['2026-01-02','2026-01-05','2026-01-06'];
const candles=dates.map((date,i)=>({date,close:[100,90,120][i]}));
const held=holdCurve(candles,[{date:dates[0],amount:999},{date:dates[1],amount:5},{date:dates[2],amount:2}],dates);
assert(Math.abs(held.trade.return_pct - (126.7/100.25-1)*100)<1e-9);
const index=holdCurve(candles,[],dates,0);
assert(Math.abs(index.trade.return_pct-20)<1e-9);
assert(Math.abs(equityMetrics(index.equity).max_drawdown_pct+10)<1e-9);
assert.deepEqual(closedEquity(candles,[],[],dates),[1,1,1]);
assert.equal(equityMetrics(closedEquity(candles,[],[],dates)).sharpe_ratio,null);
