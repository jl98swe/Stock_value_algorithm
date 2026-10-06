const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const echarts = require(process.env.ECHARTS_TEST_MODULE || 'echarts');
const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'docs/assets/app.js'), 'utf8');
const enhancements = fs.readFileSync(path.join(root, 'docs/assets/chart-enhancements.js'), 'utf8');

// Synthetic fixtures: reports extend beyond the overlapping dividend date.
function setup() {
  const dates = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08'];
  const axisSource = app.match(/xAxis: \[([\s\S]*?)\n      \],\n      yAxis:/)[1];
  const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width: 1000, height: 500 });
  chart.setOption({
    animation: false,
    grid: [{ left: 18, right: 58, top: 24, height: 265 },
      { left: 18, right: 58, top: 350, height: 105 },
      { left: 18, right: 58, top: 305, height: 24 }],
    xAxis: new Function('dates', `return [${axisSource}];`)(dates),
    yAxis: [{}, { gridIndex: 1 }, { gridIndex: 2, min: 0, max: 2 }],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1, 2], start: 0, end: 100 }],
    series: [{ name: 'Pris', type: 'candlestick', data: dates.map(() => [100, 105, 90, 110]) },
      { name: 'Score', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: dates.map(() => 50) }]
  });
  const document = new EventTarget();
  const controls = Object.fromEntries(['report', 'dividend', 'news', 'signals'].map((key) => {
    const control = new EventTarget(); control.checked = true; return [key, control];
  }));
  document.getElementById = (id) => id === 'market-chart' ? {} : null;
  document.querySelector = (selector) => selector === '[data-range].active'
    ? { dataset: { range: 'all' } } : controls[selector.match(/\[data-marker="(.*)"\]/)?.[1]] || null;
  document.querySelectorAll = () => Object.values(controls);
  const wrapper = { getInstanceByDom: () => chart };
  new Function('document', 'window', 'echarts', enhancements)(document,
    { location: { search: '?ticker=TEST.ST' }, echarts: wrapper, addEventListener() {} }, wrapper);
  document.dispatchEvent(new Event('DOMContentLoaded'));
  const stock = { candles: dates.map((date) => ({ date, open: 100, close: 105, low: 90, high: 110, ma200: 95 })), signals: [] };
  const events = [
    { event_type: 'report', event_date: dates[0], eps_ttm: 1 },
    { event_type: 'report', event_date: dates[1], eps_ttm: 1 },
    { event_type: 'dividend', event_date: dates[1], title: 'Utdelning' },
    { event_type: 'news', event_date: dates[2], title: 'Nyhet' }
  ].map((event) => ({ ticker: 'TEST.ST', ...event }));
  const rendered = new Event('market-chart-rendered');
  rendered.detail = { ticker: 'TEST.ST', stock, eventsPayload: { events } };
  document.dispatchEvent(rendered);
  const positions = () => {
    const data = chart.getModel().getSeries().find((s) => s.name === 'Händelser').getData();
    return Array.from({ length: data.count() }, (_, index) => {
      const item = data.getRawDataItem(index), graphic = data.getItemGraphicEl(index);
      return { id: data.getId(index), value: item.value, layout: data.getItemLayout(index),
        rendered: [graphic.x, graphic.y] };
    });
  };
  return { chart, controls, positions };
}

test('overlapping dividend stays on its candle when reports toggle, including zoom', () => {
  const ui = setup();
  try {
    for (const zoom of [null, { startValue: '2026-01-06', endValue: '2026-01-07' }]) {
      if (zoom) ui.chart.dispatchAction({ type: 'dataZoom', ...zoom });
      const initial = ui.positions();
      const dividend = initial.find((p) => p.id.endsWith('|D'));
      const report = initial.find((p) => p.id === dividend.id.replace('|D', '|E'));
      assert.deepEqual(dividend.rendered, report.rendered);
      assert.equal(dividend.rendered[0], ui.chart.convertToPixel({ xAxisIndex: 0 }, dividend.value[0]));
      const baseline = new Map(initial.map((p) => [p.id, p.rendered]));
      for (let mask = 0; mask < 8; mask++) {
        ['report', 'dividend', 'news'].forEach((key, index) => {
          ui.controls[key].checked = Boolean(mask & (1 << index));
          ui.controls[key].dispatchEvent(new Event('change'));
        });
        for (const point of ui.positions()) {
          assert.deepEqual(point.rendered, baseline.get(point.id), `${point.id} moved with toggle mask ${mask}`);
          assert.deepEqual(point.rendered, point.layout);
          assert.equal(point.rendered[0], ui.chart.convertToPixel({ xAxisIndex: 0 }, point.value[0]));
        }
      }
      Object.values(ui.controls).forEach((control) => { control.checked = true; control.dispatchEvent(new Event('change')); });
    }
  } finally { ui.chart.dispose(); }
});
