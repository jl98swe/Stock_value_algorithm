// Synthetic quote example: test the exact session/basis/expiry contract in a real chart.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const docs = path.resolve(__dirname, '../docs');

test('desktop and mobile show a cached score, expire it, and replace it with the published close', async () => {
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  try {
    for (const mobile of [false,true]) {
      const context = await browser.newContext({viewport:mobile ? {width:390,height:844} : {width:1440,height:1000},hasTouch:mobile,isMobile:mobile});
      const page = await context.newPage();
      const errors=[]; page.on('pageerror',e=>errors.push(e.message));
      let published=false;
      const stock = JSON.parse(await fs.readFile(path.join(docs,'data/dashboard/THULE.ST.json'),'utf8'));
      const old = structuredClone(stock);
      old.candles=old.candles.filter(r=>r.date<='2026-11-03');
      old.scores=old.scores.filter(r=>r.date<='2026-11-03');
      old.latest={...old.latest,date:'2026-11-03',close:204.6,score:64.9129};
      old.opening_candle={date:'2026-11-04',open:204.6,close:204.6,high:204.6,low:204.6,preliminary:true,completeOHLC:false};
      const final=structuredClone(old);
      final.candles.push({date:'2026-11-04',open:204.6,high:211,low:203.4,close:210.2,ma200:213.08});
      final.scores.push({date:'2026-11-04',value:80.9451});
      final.latest={...final.latest,date:'2026-11-04',close:210.2,score:80.9451};
      delete final.opening_candle;
      const cache={schema_version:1,session_date:'2026-11-04',generated_at:'2026-11-04T22:23:00+01:00',expires_at:'2026-11-05T00:00:00+01:00',
        closing_match_start:'2026-11-04T17:29:30+01:00',session_close:'2026-11-04T17:30:00+01:00',
        stocks:{'THULE.ST':{latest:{price:210.2,currency:'SEK',source:'Synthetic',as_of:'2026-11-04T17:23:40+01:00'},
          opening:{price:204.6},day_high:211,day_low:203.4,
          valuation:{score:80.9451,price:210.2,currency:'SEK',as_of:'2026-11-04T17:23:40+01:00',basis_date:'2026-11-03',session:'2026-11-04',preliminary:true}}}};
      await page.clock.install({time:new Date('2026-11-04T22:30:00+01:00')});
      await page.route('https://raw.githubusercontent.com/**',r=>r.fulfill({json:cache}));
      await page.route('https://cdnjs.cloudflare.com/**',r=>r.fulfill({path:process.env.ECHARTS_TEST_FILE,contentType:'text/javascript'}));
      await page.route('https://closing-ui.test/**',async r=>{
        const url=new URL(r.request().url());
        if(url.pathname.endsWith('/THULE.ST.json'))return r.fulfill({json:published?final:old});
        const file=path.join(docs,url.pathname==='/'?'index.html':decodeURIComponent(url.pathname));
        await r.fulfill({body:await fs.readFile(file),contentType:({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[path.extname(file)]});
      });
      const option=()=>page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('market-chart')).getOption());
      const ready=()=>page.waitForFunction(()=>document.getElementById('stock-name').textContent.includes('Thule')&&window.echarts?.getInstanceByDom(document.getElementById('market-chart'))?.getOption()?.series?.some(s=>s.name==='MA200'));
      await page.goto('https://closing-ui.test/?ticker=THULE.ST');await ready();
      await page.waitForFunction(()=>document.getElementById('metric-score').textContent==='80,95');
      let o=await option();
      assert.equal(o.series.find(s=>s.name==='Preliminär poäng').data.at(-1),80.9451);
      assert.equal(o.series.find(s=>s.name==='Värderingspoäng').data.at(-1),null);
      assert.deepEqual(o.series.find(s=>s.name==='Pris').data.at(-1).value,[204.6,210.2,203.4,211]);
      await page.locator('[data-range="1m"]').click();
      await page.locator('#market-chart').click({position:{x:mobile?180:600,y:300}});
      assert((await option()).series.some(s=>s.name==='Preliminär poäng'));
      await page.clock.setFixedTime(new Date('2026-11-05T09:00:00+01:00'));
      await page.reload();await ready();
      assert.equal(await page.locator('#metric-score').textContent(),'64,91');
      assert.match(await page.locator('#chart-preliminary-description').textContent(),/öppningskursen/);
      published=true;await page.reload();await ready();
      o=await option();
      assert.equal(o.series.find(s=>s.name==='Värderingspoäng').data.at(-1),80.9451);
      assert.equal(o.xAxis[0].data.filter(d=>d==='2026-11-04').length,1);
      assert.equal(await page.locator('#chart-preliminary-note').isVisible(),false);
      assert.deepEqual(errors,[]);
      await context.close();
    }
  } finally {await browser.close();}
});
