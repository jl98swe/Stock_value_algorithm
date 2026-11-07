// Synthetic examples: entry-relative loss, not a fall from a later peak.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {entryDrawdown, worstEntryDrawdown, drawdownPercent} = require('../docs/assets/method.js');
const candles = [100,120,95,50].map((close,i)=>({date:`2026-10-${20+i}`,close}));
const trade = {entry_date:'2026-10-20',entry_price:100,exit_date:'2026-10-23'};
test('uses held closes, excluding exit-day close after an opening sale',()=>{
  assert(Math.abs(entryDrawdown(candles,trade)+5)<1e-10);
  assert.equal(entryDrawdown(candles,{...trade,exit_reason:'period_end'}),-50);
});
test('never below entry is zero, even after a fall from a peak',()=>{
  assert.equal(entryDrawdown(candles.slice(0,2),trade),0);
  assert.equal(drawdownPercent(0),'0 %');
  assert.match(drawdownPercent(-5),/−5/);
});
test('open positions exclude preliminary prices and summary takes worst closed lot',()=>{
  const open={entry_date:'2026-10-20',entry_price:100};
  assert(Math.abs(entryDrawdown([...candles.slice(0,3),{...candles[3],preliminary:true}],open,'2026-10-23')+5)<1e-10);
  assert(Math.abs(worstEntryDrawdown(candles,[trade,{...trade,entry_price:80}])+5)<1e-10);
  assert.equal(worstEntryDrawdown(candles,[]),null);
});

test('both pages load the information popover and rightmost two-line heading',()=>{
  const fs=require('node:fs'), path=require('node:path');
  for(const name of ['index','method']) {
    const html=fs.readFileSync(path.join(__dirname,`../docs/${name}.html`),'utf8');
    assert(html.includes('help-popovers.js'));
    if (name === 'method') assert(html.includes('beräknad på stängningskurser'));
  }
  const app=fs.readFileSync(path.join(__dirname,'../docs/assets/app.js'),'utf8');
  assert.match(app, /<th>MAX<br>DRAWDOWN <span class="info-tip"/);
  assert(app.includes('window.initializeHelpPopovers?.()'));
  for (const name of ['index', 'method']) {
    const html = fs.readFileSync(path.join(__dirname, `../docs/${name}.html`), 'utf8');
    assert(html.includes('help-popovers.js?v='));
  }
  assert(app.includes('<th>TID I<br>POSITION</th>'));
});

// Synthetic sessions span a weekend; repeated lows retain the first occurrence.
test('days to lowest close count sessions from zero and preserve first tied low',()=>{
  const {entryDrawdownMetrics, worstEntryDrawdownMetrics, drawdownWithDays} = require('../docs/assets/method.js');
  const sessions = [['2026-10-23',99],['2026-10-26',95],['2026-10-27',95],['2026-10-28',90]].map(([date,close])=>({date,close}));
  const t = {entry_date:'2026-10-23',entry_price:100,exit_date:'2026-10-28'};
  assert.equal(entryDrawdownMetrics(sessions,t).entry_drawdown_days,1);
  assert.equal(entryDrawdownMetrics(sessions,{...t,exit_reason:'period_end'}).entry_drawdown_days,3);
  assert.equal(entryDrawdownMetrics(sessions.slice(0,1),t).entry_drawdown_days,0);
  assert.equal(entryDrawdownMetrics([...sessions].reverse(),t).entry_drawdown_days,1);
  assert.equal(entryDrawdownMetrics(sessions,{...t,exit_date:null},'2026-10-27').entry_drawdown_days,1);
  assert.equal(entryDrawdownMetrics([{...sessions[3],preliminary:true}],t).entry_drawdown_days,null);
  assert.equal(worstEntryDrawdownMetrics(sessions,[t,{...t,entry_price:110}]).entry_drawdown_days,1);
  assert.match(drawdownWithDays(-5,0),/0 dagar/);
});
