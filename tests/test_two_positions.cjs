// Synthetic example: staggered purchases share cash, rather than compounding full investments.
const test=require('node:test'), assert=require('node:assert/strict');
const {closedEquity,fullHistoryRows}=require('../docs/assets/method.js');
const candles=[{date:'2026-01-05',close:100},{date:'2026-01-06',close:100},{date:'2026-01-07',close:110},{date:'2026-01-08',close:120}];
const trades=[
 {entry_date:'2026-01-05',exit_date:'2026-01-07',entry_price:100,return_pct:(110*.9975/(100*1.0025)-1)*100},
 {entry_date:'2026-01-06',exit_date:'2026-01-08',entry_price:100,return_pct:(120*.9975/(100*1.0025)-1)*100}
];
test('two overlapping lots use half the NAV and remaining cash',()=>{
 const firstBudget=.5, quantity=firstBudget/(100*1.0025);
 const secondBudget=(.5+quantity*100)/2;
 const expected=1-firstBudget-secondBudget+firstBudget*(1+trades[0].return_pct/100)+secondBudget*(1+trades[1].return_pct/100);
 const curve=closedEquity(candles,trades,[],candles.map(c=>c.date),2);
 assert(Math.abs(curve.at(-1)-expected)<1e-12);
 const rows=fullHistoryRows({candles},{standard_two_positions:{closed_trades:trades}},null);
 assert(Math.abs(rows.find(r=>r.id==='standard_two_positions').return_pct-(expected-1)*100)<1e-9);
});
