// Synthetic examples: UI presentation never changes the published historical rows.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', hidden: false });
    return elements.get(id);
  };
  let option, rendered, preview = null;
  const chart = { getHeight: () => 600, setOption: o => { option = o; } };
  const window = { strategySelection: { get: () => 'standard' },
    intradayQuotes: { preview: () => preview }, echarts: { init: () => chart } };
  const document = { getElementById: element, querySelector: () => ({ textContent: '1M' }),
    dispatchEvent: e => { rendered = e.detail; } };
  const source = fs.readFileSync('docs/assets/app.js', 'utf8').replace("document.addEventListener('DOMContentLoaded', init);", 'window.testing = { state, renderChart, sliceData };');
  vm.runInNewContext(source, { window, document, echarts: window.echarts, Intl, Date, CustomEvent: class { constructor(type, data) { this.detail = data.detail; } } });
  const api = window.testing;
  return { ...api, element, chart, setPreview: p => { preview = p; }, get option() { return option; }, get rendered() { return rendered; } };
}
const candle = (date, close = 100) => ({ date, open: 100, high: 105, low: 95, close });
test('1M clamps a month-end cutoff instead of rolling into the next month', () => {
  const ui = setup(); ui.state.range = '1m';
  const sliced = ui.sliceData({ candles: [candle('2026-02-27'), candle('2026-02-28'), candle('2026-03-31')], scores: [] });
  assert.equal(sliced.candles[0].date, '2026-02-28');
});
test('provisional score is a separate dashed series and missing OHLC uses a price point', () => {
  const ui = setup(); ui.state.range = '1m';
  const data = { latest: { date: '2026-10-15' }, candles: [candle('2026-10-15')], scores: [{ date: '2026-10-15', value: 30 }] };
  ui.setPreview({ candle: { date: '2026-10-16', close: 102, preliminary: true, completeOHLC: false }, score: 42 });
  ui.renderChart('EXAMPLE.ST', data);
  assert.equal(ui.option.xAxis[0].data.at(-1), '2026-10-16');
  assert.equal(ui.option.series.find(s => s.name === 'Pris').data.at(-1).value, '-');
  assert.equal(ui.option.series.find(s => s.name === 'Preliminär kurs').data.at(-1), 102);
  assert.equal(ui.option.series.find(s => s.name === 'Score').data.at(-1), null);
  assert.equal(ui.option.series.find(s => s.name === 'Preliminär poäng').data.at(-1), 42);
  assert.equal(ui.option.series.find(s => s.name === 'Preliminär poäng').lineStyle.type, 'dashed');
  assert.equal(data.candles.length, 1);
  assert.equal(ui.rendered.stock.candles.length, 2, 'enhancements receive the same provisional date extent');
  ui.setPreview(null); ui.renderChart('EXAMPLE.ST', data);
  assert.equal(ui.option.xAxis[0].data.at(-1), '2026-10-15');
  assert.equal(ui.element('chart-preliminary-note').hidden, true);
});
