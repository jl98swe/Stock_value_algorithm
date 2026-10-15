// Synthetic examples for expiry, daily-close precedence and stock switching.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', className: '', hidden: true, addEventListener() {} });
    return elements.get(id);
  };
  const now = Date.parse('2026-10-15T13:01:00+02:00');
  class Clock extends Date { static now() { return now; } }
  const payload = { schema_version: 1, session_date: '2026-10-15',
    generated_at: '2026-10-15T13:00:00+02:00', expires_at: '2026-10-16T00:00:00+02:00',
    stocks: { 'EXAMPLE.ST': { latest: { price: 102, currency: 'SEK', source: 'Nasdaq', as_of: '2026-10-15T12:44:00+02:00' },
      opening: { price: 100, source: 'Nasdaq', as_of: '2026-10-15T09:00:30+02:00' } } } };
  const window = {};
  vm.runInNewContext(fs.readFileSync('docs/assets/intraday.js', 'utf8'), { window,
    document: { getElementById: element, addEventListener() {} }, Date: Clock, Intl,
    setInterval() {}, fetch: async () => ({ ok: true, json: async () => payload }) });
  return { api: window.intradayQuotes, payload, now, element };
}

test('published daily close, expired quotes and wrong trading date are suppressed', () => {
  const { api, payload, now } = setup();
  assert.equal(api.currentQuote(payload, 'EXAMPLE.ST', '2026-10-14', now).latest.price, 102);
  assert.equal(api.currentQuote(payload, 'EXAMPLE.ST', '2026-10-15', now), null);
  assert.equal(api.currentQuote(payload, 'EXAMPLE.ST', '2026-10-14', now + 86400000), null);
  payload.stocks['EXAMPLE.ST'].latest.as_of = '2026-10-14T16:00:00+02:00';
  assert.equal(api.currentQuote(payload, 'EXAMPLE.ST', '2026-10-14', now), null);
});

test('stock switching restores matching daily price instead of previous stock quote', async () => {
  const { api, element } = setup();
  const daily = { date: '2026-10-14', close: 100, currency: 'SEK', changeText: '+1 %',
    changeClass: 'positive', dateText: 'Stängning 14 okt. 2026' };
  await api.refresh();
  api.select('EXAMPLE.ST', daily);
  assert.equal(element('latest-price').textContent, '102 SEK');
  assert.equal(element('intraday-open').textContent, '100');
  assert.equal(element('intraday-panel').hidden, false);
  api.select('OTHER.ST', { ...daily, close: 250 });
  assert.equal(element('latest-price').textContent, '250 SEK');
  assert.equal(element('intraday-panel').hidden, true);
  api.select('EXAMPLE.ST', { ...daily, date: '2026-10-15', close: 103 });
  assert.equal(element('latest-price').textContent, '103 SEK');
  assert.equal(element('stock-date').textContent, daily.dateText);
});
