const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const docs = path.resolve(__dirname, '../docs');
(async () => {
 const browser = await chromium.launch({headless:true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH} : {}),
  args:['--no-sandbox']});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://method-ui.test/**', async route => {
   const url=new URL(route.request().url()), file=path.join(docs,decodeURIComponent(url.pathname));
   try {await route.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css'})[path.extname(file)]});}
   catch {await route.fulfill({status:404,body:'Missing test file'});}
  });
  if(process.env.ECHARTS_TEST_FILE) await page.route('https://cdnjs.cloudflare.com/**', route => route.fulfill({path:process.env.ECHARTS_TEST_FILE,contentType:'text/javascript'}));
  await page.goto('https://method-ui.test/method.html?ticker=AAK.ST&strategy=ma200&period=1');
  await page.waitForSelector('#method-results:not([hidden])');
  assert.equal(await page.locator('#method-strategy').inputValue(),'ma200');
  assert.equal(await page.locator('#method-period').inputValue(),'1');
  assert.equal(await page.locator('#backtest-summary tr').count(),3);
  assert(await page.locator('[data-method="ma200"]').isVisible());
  const data=JSON.parse(await fs.readFile(path.join(docs,'data/backtests/AAK.ST.json')));
  const stock=JSON.parse(await fs.readFile(path.join(docs,'data/dashboard/AAK.ST.json')));
  const cutoff=stock.candles.at(-1).date.replace(/^2026/,'2025');
  const expected=data.ma200.closed_trades.filter(t=>t.entry_date>=cutoff && t.exit_date<=stock.candles.at(-1).date).length + data.ma200.open_lots.filter(t=>t.entry_date>=cutoff).length;
  if(expected) assert.equal(await page.locator('#method-trades tr').count(),expected);
  await page.locator('[data-strategy="report_avoidance"]').click();
  assert(await page.locator('[data-method="report_avoidance"]').isVisible());
  await page.locator('#method-period').selectOption('all');
  assert((await page.locator('#period-caption').textContent()).startsWith('2019-09-02'));
  await page.setViewportSize({width:390,height:844});
  assert(await page.locator('#method-period').isVisible());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
  await page.locator('#method-stock').selectOption('ABB.ST');
  await page.waitForSelector('#method-results:not([hidden])');
  assert.equal(new URL(page.url()).searchParams.get('ticker'),'ABB.ST');
  if(process.env.ECHARTS_TEST_FILE) {
   await page.goto('https://method-ui.test/index.html?ticker=AAK.ST');
   await page.waitForSelector('#trades-table [data-method-link]');
   await page.locator('#trades-table [data-method-link]').first().focus();
   await page.keyboard.press('Enter');
   await page.waitForURL('**/method.html?ticker=AAK.ST&strategy=standard');
   await page.waitForSelector('#method-results:not([hidden])');
   assert.equal(await page.locator('#method-strategy').inputValue(),'standard');
  }
  assert.deepEqual(errors,[]);
  console.log('Method UI passed: deep links, three strategies, periods, stock switch and mobile layout.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
