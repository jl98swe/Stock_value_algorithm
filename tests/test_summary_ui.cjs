// Synthetic data exercises production Method rendering, filtering and help on both viewport sizes.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const {summaryHeader} = require('../docs/assets/method.js');
const ids=['standard','standard_stop_loss_10','standard_two_positions','ma200','report_avoidance','buy_and_hold','omxsgi'];
const candles=[{date:'2025-01-02',close:100},{date:'2025-06-02',close:120},{date:'2026-01-02',close:108}];
const trades=[{entry_date:candles[0].date,exit_date:candles[1].date,entry_price:100,return_pct:20},{entry_date:candles[1].date,exit_date:candles[2].date,entry_price:120,return_pct:-10}];
const variants=Object.fromEntries(ids.slice(0,5).map(id=>[id,{closed_trades:trades,open_lots:[]}]));
const summary={return_pct:8,max_drawdown_pct:-10,sharpe_ratio:.5,trade_count:2,win_rate_pct:50,open_count:0,gross_profit:.2,gross_loss:.12};
const aggregate={...variants,meta:{start_date:candles[0].date,end_date:candles[2].date,stock_count:1,excluded_stocks:[]},periods:Object.fromEntries(['all','1','3','5'].map(p=>[p,{start_date:candles[0].date,strategies:Object.fromEntries(ids.map(id=>[id,summary])),reference_trades:{}}]))};
test('summary columns, ratios and circular help work on mobile and desktop',async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,headless:true,args:['--no-sandbox']});
 try {
  for(const width of [1440,390]) {
   const page=await browser.newPage({viewport:{width,height:1000}}), errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('https://summary.test/**',async route=>{
    const name=decodeURIComponent(new URL(route.request().url()).pathname).slice(1);
    const fixtures={'data/stocks.json':{stocks:[{ticker:'EXAMPLE.ST',name:'Exempel'}]},'data/benchmarks/omxsgi.json':{candles},'data/dashboard/EXAMPLE.ST.json':{candles},'data/backtests/EXAMPLE.ST.json':variants,'data/backtests/all.json':aggregate};
    if(name in fixtures) return route.fulfill({json:fixtures[name]});
    try {await route.fulfill({body:await fs.readFile(path.join(__dirname,'../docs',name)),contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css'})[path.extname(name)]});}
    catch {await route.fulfill({status:404,body:'Missing fixture'});}
   });
   await page.goto('https://summary.test/method.html?ticker=all');
   await page.waitForSelector('#backtest-summary tr');
   assert.equal(await page.locator('#backtest-summary-head th').count(),8);
   assert.equal(await page.locator('#backtest-summary tr').count(),7);
   assert.equal(await page.locator('#backtest-summary tr:first-child td').count(),8);
   assert.equal(await page.locator('#backtest-summary tr:first-child td').nth(2).innerText(),'1,67');
   for(const trigger of await page.locator('#backtest-summary-head .info-tip').all()) {
    assert.equal(await trigger.evaluate(el=>getComputedStyle(el).borderRadius),'50%');
    assert.equal(await trigger.evaluate(el=>getComputedStyle(el).borderTopStyle),'solid');
   }
   const help=page.locator('button[data-capital-drawdown-help]');
   await help.click();
   assert.match(await page.locator('.help-popover:popover-open').innerText(),/tidigare topp/);
   assert(!/dagar/.test(await page.locator('.help-popover:popover-open').innerText()));
   await page.keyboard.press('Escape');
   await page.locator('#method-stock').selectOption('EXAMPLE.ST');
   await page.locator('#method-results:not([hidden])').waitFor();
   await page.waitForFunction(()=>document.querySelector('#backtest-summary tr td:nth-child(2)').textContent.includes('8'));
   assert.equal(await page.locator('#backtest-summary tr:first-child td').nth(2).innerText(),'1,67');
   const actual=await page.locator('#backtest-summary-head th').allTextContents();
   assert.deepEqual(actual,summaryHeader().match(/<th>.*?<\/th>/g).map(s=>s.replace(/<[^>]*>/g,'')));
   await page.locator('#method-period').selectOption('1');
   assert.equal(await page.locator('#backtest-summary tr:first-child td').count(),8);
   assert.deepEqual(errors,[]); await page.close();
  }
 } finally {await browser.close();}
});
