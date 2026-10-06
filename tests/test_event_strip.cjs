const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'docs/assets/chart-enhancements.js'), 'utf8');

// Synthetic test fixtures: verify the actual enhancement event handler.
function setup() {
  const document = new EventTarget();
  const controls = Object.fromEntries(['report', 'dividend', 'news', 'signals'].map((key) => [key, { checked: true }]));
  const chart = {
    option: { series: [{ name: 'Pris', markPoint: { data: [] } }, { name: 'Score' }] },
    getOption() { return this.option; },
    setOption(option) { this.option = { ...this.option, ...option }; }
  };
  document.getElementById = (id) => id === 'market-chart' ? {} : null;
  document.querySelector = (selector) => {
    if (selector === '[data-range].active') return { dataset: { range: 'all' } };
    return controls[selector.match(/\[data-marker="(.*)"\]/)?.[1]] || null;
  };
  const echarts = { getInstanceByDom: () => chart };
  vm.runInNewContext(source, { document, window: { location: { search: '?ticker=TEST.ST' }, echarts }, echarts, URLSearchParams, Intl });
  const stock = { candles: [
    { date: '2026-01-05', open: 100, high: 110, low: 90, close: 105, ma200: 95 },
    { date: '2026-01-06', open: 105, high: 115, low: 101, close: 111, ma200: 96 }
  ], signals: [{ side: 'BUY', status: 'executed', execution_date: '2026-01-05', execution_price: 100 }] };
  const events = [
    { event_type: 'report', source: 'YAHOO', eps_ttm: 0.69 },
    { event_type: 'report', source: 'TRADINGVIEW', eps_ttm: 0.69012345 },
    { event_type: 'dividend', title: 'Utdelning' },
    { event_type: 'news', title: 'Nyhet ett' },
    { event_type: 'news', title: 'Nyhet två', locking: true }
  ].map((event) => ({ ticker: 'TEST.ST', event_date: '2026-01-05', ...event }));
  const render = () => {
    const event = new Event('market-chart-rendered');
    event.detail = { ticker: 'TEST.ST', stock, eventsPayload: { events } };
    document.dispatchEvent(event);
    return chart.getOption().series;
  };
  return { render, controls, stock };
}

test('events live in a separate coordinate system; only trade markers remain on price', () => {
  const ui = setup(), series = ui.render();
  const price = series.find((s) => s.name === 'Pris');
  assert.equal(price.markPoint.data.length, 1);
  assert(price.markPoint.data[0].signalTooltip);
  assert.equal(price.markPoint.data[0].coord[1], 90);
  const events = series.find((s) => s.name === 'Händelser');
  assert.equal(events.xAxisIndex, 2); assert.equal(events.yAxisIndex, 2);
  assert.equal(events.data.length, 3);
  assert.deepEqual(Array.from(events.data, (p) => p.value[1]), [3, 2, 1]);
  assert(events.data.every((p) => p.value[0] === '2026-01-05' && !p.coord));
  assert.match(events.data[0].eventTooltip, /TRADINGVIEW/);
  assert.match(events.data[0].eventTooltip, /0,69012345/);
  assert.match(events.data[2].eventTooltip, /Nyhet ett/);
  assert.match(events.data[2].eventTooltip, /Nyhet två/);
  assert.equal(events.data[2].itemStyle.borderWidth, 2.5);
});

test('toggles and repeated renders keep one event strip without changing price data', () => {
  const ui = setup();
  ui.render(); ui.controls.report.checked = false; ui.controls.signals.checked = false;
  let series = ui.render();
  assert.equal(series.filter((s) => s.name === 'Händelser').length, 1);
  assert.equal(series.filter((s) => s.name === 'MA200').length, 1);
  assert.equal(series.find((s) => s.name === 'Pris').markPoint.data.length, 0);
  assert(!series.find((s) => s.name === 'Händelser').data.some((p) => p.value[1] === 3));
  ui.controls.report.checked = true; ui.controls.signals.checked = true;
  series = ui.render();
  assert.equal(series.find((s) => s.name === 'Händelser').data.length, 3);
  assert.equal(ui.stock.candles[0].low, 90);
});

test('reserved band stays between price and score on mobile and desktop; zoom uses all three axes', () => {
  const app = fs.readFileSync(path.join(root, 'docs/assets/app.js'), 'utf8');
  assert(app.includes('xAxisIndex: [0, 1, 2]'));
  assert.equal((app.match(/left: 18, right: 58/g) || []).length, 3);
  assert(app.includes("top: '55%', height: 60, containLabel: false"));
  for (const height of [470, 500, 540, 640]) {
    const priceBottom = 24 + height * 0.47, bandTop = height * 0.55;
    assert(bandTop > priceBottom);
    assert(bandTop + 60 < height * 0.70);
    assert(60 / 3 > 18); // separate 18px icons with a gap between rows
  }
});
