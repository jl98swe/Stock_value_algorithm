const assert = require('node:assert/strict');
const {profitFactor, profitFactorText, fullHistoryRows} = require('../docs/assets/method.js');
// Synthetic examples: monetary profits reflect reinvested capital, not summed percentages.
const candles = [1,2,3,4,5,6].map(day => ({date:`2026-01-0${day}`,close:100}));
const trade = (first,last,result) => ({entry_date:candles[first].date,exit_date:candles[last].date,entry_price:100,return_pct:result});
const trades = [trade(0,1,20),trade(2,3,-10)];
assert(Math.abs(profitFactor(candles,trades) - 20/12) < 1e-12);
assert.equal(profitFactor(candles,[]),null);
assert.equal(profitFactor(candles,[trade(0,1,0)]),null);
assert.equal(profitFactor(candles,[trade(0,1,20)]),Infinity);
assert.equal(profitFactor(candles,[trade(0,1,-10)]),0);
assert.equal(profitFactor(candles,[trade(0,1,null)]),null);
assert.equal(profitFactorText(Infinity),'∞');
assert.equal(profitFactorText(null),'–');
assert.equal(profitFactorText(1.234),'1,23');
// Overlapping positions split current capital; the first entry fee reduces the second budget.
const secondBudget = (.5 + .5/1.0025)/2;
assert(Math.abs(profitFactor(candles,[trade(0,3,20),trade(0,4,-10)],[],2)-.1/(secondBudget*.1))<1e-12);
// Same-day stop loss must count as a realized loss.
assert(Math.abs(profitFactor(candles,[trade(0,0,-10),trade(1,2,20)])-1.8)<1e-12);
// Cash dividends do not get counted twice; final returns already include them.
assert(Math.abs(profitFactor(candles,trades,[{date:candles[1].date,amount:5}])-20/12)<1e-12);
const rows=fullHistoryRows({candles},{standard:{closed_trades:trades,open_lots:[{current_return_pct:999}]}},null);
assert(Math.abs(rows.find(r=>r.id==='standard').profit_factor-20/12)<1e-12);
const fs=require('node:fs');
const app=fs.readFileSync('docs/assets/app.js','utf8');
const {summaryHeader} = require('../docs/assets/method.js');
assert(summaryHeader().indexOf('Avkastning') < summaryHeader().indexOf('Profit<br>factor'));
assert.equal((summaryHeader().match(/<th>/g)||[]).length,8);
assert(!/Genomsnitt per affär|UPPGÅNG|data-drawdown-help/.test(summaryHeader()));
assert(summaryHeader().includes('Öppna<br>positioner'));
assert(app.includes('window.backtestMetrics.summaryHeader()'));
assert(fs.readFileSync('docs/assets/method.js','utf8').includes('`<tr>${summaryHeader()}</tr>`'));
assert(fs.readFileSync('docs/assets/style.css','utf8').includes('.info-tip { display: inline-grid;'));
assert(fs.readFileSync('docs/index.html','utf8').includes('id="comparison-period"'));
assert(summaryHeader().includes('data-capital-drawdown-help'));
assert(!/dagar/.test(summaryHeader().match(/<th>Max<br>drawdown .*?<\/th>/)[0]));
assert(app.includes('<td>${pct(row.return_pct)}</td><td>${window.backtestMetrics.profitFactorText(row.profit_factor)}</td>'));
console.log('Profit factor checks passed.');

