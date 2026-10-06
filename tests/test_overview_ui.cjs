const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const docs=path.resolve(__dirname,'../docs');
(async()=>{
 const data=JSON.parse(await fs.readFile(path.join(docs,'data/strategy_overviews.json')));
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,args:['--no-sandbox']});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let override=null, forecastOverride=null;
  await page.route('https://overview-ui.test/**',async route=>{
   const url=new URL(route.request().url());
   if(override && url.pathname==='/data/strategy_overviews.json') return route.fulfill({json:override});
   if(forecastOverride && url.pathname==='/data/signal_prices.json') return route.fulfill({json:forecastOverride});
   const file=path.join(docs,decodeURIComponent(url.pathname));
   try {await route.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css'})[path.extname(file)]});}
   catch {await route.fulfill({status:404,body:'Missing fixture'});}
  });
  if(process.env.ECHARTS_TEST_FILE) await page.route('https://cdnjs.cloudflare.com/**',route=>route.fulfill({path:process.env.ECHARTS_TEST_FILE,contentType:'text/javascript'}));
  await page.goto('https://overview-ui.test/index.html?ticker=ABB.ST');
  await page.waitForFunction(()=>document.querySelector('#stock-name').textContent && document.querySelector('#trades-table tbody'));
  assert.equal(await page.locator('#home-strategy').inputValue(),'standard');
  assert((await page.locator('#home-strategy').boundingBox()).y < (await page.locator('#stock-name').boundingBox()).y);
  for(const key of ['standard','ma200','report_avoidance']) {
    await page.locator('#home-strategy').selectOption(key);
    const live=data.strategies[key].stocks['ABB.ST'];
    assert.equal(await page.locator('#metric-position').textContent(),live.position.lots ? '1 aktiv position' : 'Ingen aktiv position');
    assert.equal(await page.locator('#metric-action').textContent(),live.next_action.label || 'Ingen signal');
    assert.equal(new URL(page.url()).searchParams.get('strategy'),key);
    const tests=JSON.parse(await fs.readFile(path.join(docs,'data/backtests/ABB.ST.json')))[key];
    const actual=await page.evaluate(()=>echarts.getInstanceByDom(document.querySelector('#market-chart')).getOption().series[0].markPoint.data.map(p=>p.coord[0]));
    const dates=await page.evaluate(()=>echarts.getInstanceByDom(document.querySelector('#market-chart')).getOption().xAxis[0].data);
    const expected=tests.closed_trades.flatMap(t=>[t.entry_date,t.exit_date]).concat(tests.open_lots.map(t=>t.entry_date)).filter(d=>d>=dates[0] && d<=dates.at(-1));
    assert.deepEqual(actual.sort(),expected.sort());
    for(const url of await page.locator('#trades-table [data-method-link]').evaluateAll(rows=>rows.map(r=>r.dataset.methodLink))) assert.equal(new URL(url,'https://overview-ui.test').searchParams.get('strategy'),key);
  }
  await page.locator('.page-nav a').filter({hasText:'Metod',exact:true}).click();
  await page.waitForSelector('#method-results:not([hidden])');
  assert.equal(await page.locator('#method-strategy').inputValue(),'report_avoidance');
  await page.locator('#method-strategy').selectOption('ma200');
  await page.locator('.page-nav a').filter({hasText:'Startsida',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#trades-table tbody'));
  assert.equal(await page.locator('#home-strategy').inputValue(),'ma200');
  await page.locator('.stock-button[data-ticker="AAK.ST"]').click();
  await page.waitForFunction(()=>document.querySelector('#stock-ticker')?.textContent==='AAK.ST');
  await page.locator('.page-nav a').filter({hasText:'Metod',exact:true}).click();
  await page.waitForSelector('#method-results:not([hidden])');
  assert.equal(await page.locator('#method-stock').inputValue(),'AAK.ST');
  await page.locator('#method-stock').selectOption('ABB.ST');
  await page.waitForSelector('#method-results:not([hidden])');
  await page.locator('.page-nav a').filter({hasText:'Granska nyheter och data',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#review-stock')?.options.length>0);
  assert.equal(await page.locator('#review-stock').inputValue(),'ABB.ST');
  assert.equal(await page.locator('#repository-link').count(),0);
  assert.equal(await page.locator('#review-action-link').count(),1);
  await page.locator('#review-stock').selectOption('AAK.ST');
  await page.waitForFunction(()=>new URL(location.href).searchParams.get('ticker')==='AAK.ST');
  for(const label of ['Rapporter','Kommande signaler','Aktiva positioner','Startsida']) {
    const link=page.locator('.page-nav a').filter({hasText:label,exact:true});
    assert.equal(new URL(await link.getAttribute('href'),'https://overview-ui.test').searchParams.get('ticker'),'AAK.ST');
    await link.click();
    if(label==='Rapporter') await page.waitForSelector('#reports-content:not([hidden])');
    else if(label==='Startsida') await page.waitForFunction(()=>document.querySelector('#stock-ticker')?.textContent==='AAK.ST');
    else await page.waitForSelector('#overview-content:not([hidden])');
  }
  await page.goto('https://overview-ui.test/index.html');
  await page.waitForFunction(()=>document.querySelector('#stock-ticker')?.textContent==='AAK.ST');
  await page.goto('https://overview-ui.test/index.html?ticker=ABB.ST');
  await page.waitForFunction(()=>document.querySelector('#stock-ticker')?.textContent==='ABB.ST');
  await page.locator('.page-nav a').filter({hasText:'Metod',exact:true}).click();
  await page.waitForSelector('#method-results:not([hidden])');
  await page.locator('#method-stock').selectOption('all');
  await page.waitForSelector('#method-results:not([hidden])');
  await page.locator('.page-nav a').filter({hasText:'Startsida',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#stock-ticker')?.textContent==='ABB.ST');
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#home-strategy').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('https://overview-ui.test/positions.html?strategy=standard');
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#overview-strategy').inputValue(),'standard');
  assert.deepEqual(await page.locator('#overview-strategy option').evaluateAll(options=>options.map(o=>o.textContent)),['Standard','MA200','Rapportundvikande']);
  assert((await page.locator('#overview-strategy').boundingBox()).y < (await page.locator('h1').boundingBox()).y);
  for(const key of ['standard','ma200','report_avoidance']) {
   await page.locator('#overview-strategy').selectOption(key);
   const expected=Object.values(data.strategies[key].stocks).filter(s=>s.position.lots>0).length;
   assert.equal(await page.locator('#summary-count').textContent(),String(expected));
   assert.equal(new URL(page.url()).searchParams.get('strategy'),key);
  }
  await page.locator('#overview-strategy').selectOption('ma200');
  await page.locator('.page-nav a').filter({hasText:'Kommande signaler'}).click();
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#overview-strategy').inputValue(),'ma200');
  const dates=data.meta.trading_dates,cutoff=dates[0],end=dates.at(-1);
  for(const key of ['standard','ma200','report_avoidance']) {
   await page.locator('#overview-strategy').selectOption(key);
   const expected=Object.values(data.strategies[key].stocks).flatMap(s=>s.signals).filter(s=>s.status==='executed' && s.execution_date>=cutoff && s.execution_date<=end).length;
   assert.equal(await page.locator('#recent-count').textContent(),String(expected));
  }
  await page.goto('https://overview-ui.test/positions.html');
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#overview-strategy').inputValue(),'report_avoidance'); // saved choice
  await page.locator('#overview-search').fill('does-not-exist');
  assert.equal(await page.locator('#summary-count').textContent(),'0');
  await page.locator('#overview-search').fill('');
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#overview-strategy').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  override=structuredClone(data);
  override.strategies.report_avoidance.stocks={'TEST.ST':{latest:{score:50,close:100,fundamental_lock:true},position:{lots:1,avg_entry:90,unrealized_pct:10,sell_armed:false},next_action:{type:'SELL',exit_reason:'report',execute_on:'2026-10-06',label:'Sälj inför rapport'},strategy_filter:{buy_allowed:false},signals:[]}};
  await page.goto('https://overview-ui.test/signals.html?strategy=report_avoidance');
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#upcoming-count').textContent(),'1');
  assert((await page.locator('#upcoming-signals-body').textContent()).includes('Sälj inför rapport'));
  assert((await page.locator('#upcoming-signals-body').textContent()).includes('rapportsälj tillåten'));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  override.strategies.report_avoidance.stocks['TEST.ST'].next_action={type:'NONE'};
  override.strategies.report_avoidance.stocks['TEST.ST'].strategy_filter={buy_allowed:false,trading_days_to_report:5,next_report_date:'2026-10-13',report_exit_date:'2026-10-12'};
  await page.reload();
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#upcoming-count').textContent(),'1');
  assert((await page.locator('#upcoming-signals-body').textContent()).includes('5 börsdagar till rapport'));
  assert((await page.locator('#upcoming-signals-body').textContent()).includes('12 okt'));
  override.strategies.report_avoidance.stocks['TEST.ST'].strategy_filter.trading_days_to_report=6;
  await page.reload();
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#upcoming-count').textContent(),'0');
  override.strategies.standard.stocks={'TEST.ST':{latest:{date:'2026-10-06',score:8,close:100},position:{lots:0},next_action:{type:'NONE'},strategy_filter:{buy_allowed:true},signals:[]}};
  forecastOverride={stocks:{'TEST.ST':{as_of:'2026-10-06',session:'2026-10-07',buy:{price:95.5,direction:'below',multiple_crossings:true}}}};
  await page.goto('https://overview-ui.test/signals.html?strategy=standard');
  await page.waitForSelector('#overview-content:not([hidden])');
  assert.equal(await page.locator('#upcoming-count').textContent(),'1');
  assert((await page.locator('#upcoming-signals-body').textContent()).includes('Under ≈ 95,5 kr'));
  const info=page.locator('button[aria-label="Information om stängningsgränsen"]');
  assert((await info.getAttribute('data-tooltip')).includes('oförändrad EPS'));
  await info.focus();
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('button[aria-label="Information om stängningsgränsen"]'),'::after').opacity==='1');
  forecastOverride.stocks['TEST.ST'].as_of='2026-10-04';
  await page.reload();
  await page.waitForSelector('#overview-content:not([hidden])');
  assert(!(await page.locator('#upcoming-signals-body').textContent()).includes('95,5 kr'));
  assert.deepEqual(errors,[]);
  console.log('Overview UI passed: independent counts, three strategies at top, navigation, persistence, recent executions, report exits, search and mobile.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
