// npm install --no-save playwright; node tests/test_chart_ui.cjs
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const docs = path.resolve(__dirname, '../docs');
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}), args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1500, height: 1200 } });
    const errors = [], requests = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('https://stock-ui.test/**', async (route) => {
      const url = new URL(route.request().url()); requests.push(url.pathname);
      // Reproduce data arriving after the old 60 ms enhancement timer.
      if (url.pathname.startsWith('/data/dashboard/') && url.pathname.endsWith('.ST.json')) await new Promise((r) => setTimeout(r, 800));
      const file = path.join(docs, decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
      await route.fulfill({ body: await fs.readFile(file), contentType: ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' })[path.extname(file)] });
    });
    if (process.env.ECHARTS_TEST_FILE) await page.route('https://cdnjs.cloudflare.com/**', (route) => route.fulfill({ path: process.env.ECHARTS_TEST_FILE, contentType: 'text/javascript' }));
    const snapshot = () => page.evaluate(() => {
      const option = echarts.getInstanceByDom(document.getElementById('market-chart')).getOption();
      return { maCount: option.series.filter((s) => s.name === 'MA200').length,
        points: option.series.find((s) => s.name === 'Pris').markPoint.data,
        events: option.series.find((s) => s.name === 'Händelser').data };
    });
    await page.goto('https://stock-ui.test/?ticker=ANOD-B.ST');
    await page.waitForFunction(() => echarts.getInstanceByDom(document.getElementById('market-chart'))?.getOption()?.series?.some((s) => s.name === 'MA200'));
    const initial = await snapshot();
    assert.equal(initial.maCount, 1);
    assert(initial.events.some((p) => p.label?.formatter === 'E' && p.symbol === 'circle'));
    assert(initial.points.every((p) => p.signalTooltip));
    const eventPixels = await page.evaluate(() => {
      const chart = echarts.getInstanceByDom(document.getElementById('market-chart'));
      const series = chart.getOption().series.find((s) => s.name === 'Händelser');
      return series.data.map((p) => ({
        y: chart.convertToPixel({ xAxisIndex: 2, yAxisIndex: 2 }, p.value)[1], height: chart.getHeight()
      }));
    });
    for (const pixel of eventPixels) {
      assert(pixel.y - 9 > 24 + pixel.height * 0.47);
      assert(pixel.y + 9 < pixel.height * 0.70);
    }
    assert.equal(await page.locator('#stock-name').textContent(), 'Addnode');
    assert(!requests.includes('/data/dashboard.json'));
    await page.locator('[data-marker="dividend"]').uncheck();
    await page.locator('[data-marker="dividend"]').check();
    assert.deepEqual(await snapshot(), initial, 'First render must equal toggle round trip');
    await page.locator('[data-range="ytd"]').click();
    const signals = (await snapshot()).points.filter((p) => p.signalTooltip);
    assert(signals.some((p) => p.name === 'Köp'));
    assert(signals.some((p) => p.name === 'Sälj'));
    const data = JSON.parse(await fs.readFile(path.join(docs, 'data/dashboard/ANOD-B.ST.json')));
    for (const point of signals) {
      const candle = data.candles.find((c) => c.date === point.coord[0]), buy = point.name === 'Köp';
      assert.equal(point.coord[1], buy ? candle.low : candle.high);
      assert.equal(point.symbolOffset[1], buy ? 16 : -16);
      const pixel = await page.evaluate((point) => {
        const chart = echarts.getInstanceByDom(document.getElementById('market-chart'));
        const wick = chart.convertToPixel({ seriesIndex: 0 }, point.coord);
        return { wickY: wick[1], markerY: wick[1] + point.symbolOffset[1], height: chart.getHeight() };
      }, point);
      assert(buy ? pixel.markerY - 9 > pixel.wickY : pixel.markerY + 9 < pixel.wickY);
      assert(pixel.markerY > 9 && pixel.markerY < pixel.height * 0.65);
    }
    const tooltip = await page.evaluate(() => {
      const option = echarts.getInstanceByDom(document.getElementById('market-chart')).getOption();
      return option.tooltip[0].formatter([{ axisValue: option.xAxis[0].data[0] }]);
    });
    assert.match(tooltip, /<br>O .* · H .* · L .* · C /);
    await page.locator('[data-marker="report"]').uncheck();
    await page.locator('[data-marker="signals"]').uncheck();
    await page.locator('[data-range="6m"]').click();
    const isHidden = (state) => !state.points.some((p) => p.signalTooltip) && !state.events.some((p) => p.label?.formatter === 'E');
    assert(isHidden(await snapshot()));
    await page.locator('#stock-search').fill('embracer');
    assert.equal(await page.locator('.stock-button').count(), 1);
    assert.equal(await page.locator('.stock-button').getAttribute('data-ticker'), 'EMBRAC-B.ST');
    await page.locator('.stock-button').click();
    await page.waitForFunction(() => document.getElementById('stock-name').textContent === 'Embracer');
    assert(isHidden(await snapshot()));
    for (const marker of ['report', 'dividend', 'news', 'signals']) await page.locator(`[data-marker="${marker}"]`).check();
    const restored = await snapshot();
    assert(restored.events.some((p) => p.label?.formatter === 'E'));
    assert(!restored.points.some((p) => p.symbol === 'pin'));
    assert.equal(restored.maCount, 1);
    await page.locator('#stock-search').fill('anod');
    await page.locator('.stock-button').click();
    await page.waitForFunction(() => document.getElementById('stock-name').textContent === 'Addnode');
    await page.locator('[data-range="ytd"]').click();
    if (process.env.CHART_TEST_SCREENSHOT) await page.locator('#market-chart').screenshot({ path: process.env.CHART_TEST_SCREENSHOT });
    assert.deepEqual(errors, []);
    console.log('Chart UI passed: delayed initial load, toggle round trip, wick offsets, OHLC, range changes, company search and delayed stock switches.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
