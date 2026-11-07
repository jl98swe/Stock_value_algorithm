const {test} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const docs = path.resolve(__dirname, '../docs');
test('upside column and circular help work on desktop and mobile',async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try {
  for (const width of [1440,390]) {
   const page=await browser.newPage({viewport:{width,height:1000}});
   const errors=[]; page.on('pageerror',e=>errors.push(e.message));
   await page.route('https://upside.test/**',async route=>{
    const file=path.join(docs,decodeURIComponent(new URL(route.request().url()).pathname));
    try {await route.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css'})[path.extname(file)]});}
    catch {await route.fulfill({status:404,body:'Missing fixture'});}
   });
   await page.route('https://cdnjs.cloudflare.com/**',route=>process.env.ECHARTS_TEST_FILE ? route.fulfill({path:process.env.ECHARTS_TEST_FILE,contentType:'text/javascript'}) : route.abort());
   for(const url of ['method.html?ticker=all','method.html?ticker=AAK.ST','index.html?ticker=AAK.ST']) {
    await page.goto(`https://upside.test/${url}`);
    const triggers=page.locator('button[data-upside-help]');
    await triggers.first().waitFor(); assert.equal(await triggers.count(),2);
    const trigger=triggers.last(); await trigger.scrollIntoViewIfNeeded();
    const heading=trigger.locator('..'); assert.match(await heading.innerText(),/MAX\s+UPPGÅNG/);
    const rect=await trigger.boundingBox(); assert(rect.width<=18 && rect.height<=18);
    assert.equal(await trigger.evaluate(el=>getComputedStyle(el).borderRadius),'50%');
    assert.equal(await page.locator('.help-popover:visible').count(),0);
    await trigger.click();
    const popup=page.locator('.help-popover:popover-open'); await popup.waitFor();
    assert.match(await popup.innerText(),/handelsdagar.*försäljningen/);
    const box=await popup.boundingBox(); assert(box.x>=0 && box.x+box.width<=width);
    await page.keyboard.press('Escape'); assert.equal(await page.locator('.help-popover:visible').count(),0);
    const cells=page.locator(url.startsWith('method') ? '#method-trades tr:first-child td' : '#trades-table tbody tr:first-child td');
    if(!url.includes('ticker=all')) assert.match(await cells.last().innerText(),/%/);
   }
   assert.deepEqual(errors,[]); await page.close();
  }
 } finally {await browser.close();}
});
