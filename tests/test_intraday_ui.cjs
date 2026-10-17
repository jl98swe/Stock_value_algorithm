// Synthetic examples for expiry, daily-close precedence and stock switching.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(request = null) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', className: '', hidden: true, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; } });
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
    document: { getElementById: element, addEventListener() {}, dispatchEvent() {} }, CustomEvent: class { constructor(type) { this.type = type; } }, Date: Clock, Intl,
    setInterval() {}, fetch: async () => request ? request(payload) : ({ ok: true, json: async () => payload }) });
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


test('synthetic provisional quote uses real OHLC only and requires matching score provenance', async () => {
  const { api, payload, element } = setup();
  await api.refresh();
  const item = payload.stocks['EXAMPLE.ST'];
  assert.equal(api.preview('EXAMPLE.ST', '2026-10-14').candle.completeOHLC, false);
  item.day_high = 105; item.day_low = 99;
  item.valuation = { preliminary: true, score: 42, price: 102, as_of: item.latest.as_of, currency: 'SEK', basis_date: '2026-10-14', session: '2026-10-15' };
  let preview = api.preview('EXAMPLE.ST', '2026-10-14');
  assert.equal(preview.candle.completeOHLC, true);
  assert.equal(preview.score, 42);
  item.valuation.price = 101;
  assert.equal(api.preview('EXAMPLE.ST', '2026-10-14').score, null);
  assert.equal(api.preview('EXAMPLE.ST', '2026-10-15'), null);
  assert.equal(api.preview('OTHER.ST', '2026-10-14'), null);
});

test('preliminary score must match the exact quote, session and daily basis', async () => {
  const { api, payload, now } = setup();
  const item = payload.stocks['EXAMPLE.ST'];
  item.valuation = { preliminary: true, score: 0, price: 102, currency: 'SEK',
    as_of: item.latest.as_of, basis_date: '2026-10-14', session: '2026-10-15' };
  const get = () => api.currentValuation(payload, 'EXAMPLE.ST', '2026-10-14', 'SEK', now);
  assert.equal(get().score, 0);
  assert.equal(api.currentValuation(payload, 'EXAMPLE.ST', '2026-10-15', 'SEK', now), null);
  assert.equal(api.currentValuation(payload, 'EXAMPLE.ST', '2026-10-14', 'EUR', now), null);
  item.latest.price = 103;
  assert.equal(get(), null);
  item.latest.price = 102;
  item.valuation.score = null;
  assert.equal(get(), null);
});


test('manual refresh shows progress, updates values automatically and distinguishes unchanged and failed reads', async () => {
  let responder = payload => ({ok:true,json:async()=>payload});
  const ui = setup(payload => responder(payload));
  await ui.api.refresh();
  ui.api.select('EXAMPLE.ST', {date:'2026-10-14',close:100,currency:'SEK'});
  let release, calls = 0;
  responder = payload => { calls++; return new Promise(resolve => {release=()=>resolve({ok:true,json:async()=>payload});}); };
  const button = ui.element('intraday-refresh');
  const pending = button.listeners.click();
  assert.equal(button.disabled, true);
  assert.equal(ui.element('quote-refresh-spinner').hidden, false);
  assert.match(ui.element('quote-refresh-status').textContent, /1–5 sekunder/);
  const duplicate = ui.api.refresh();
  assert.equal(calls, 1, 'duplicate clicks share the active request');
  ui.payload.stocks['EXAMPLE.ST'].latest.price = 103;
  release(); await pending; await duplicate;
  assert.equal(ui.element('latest-price').textContent, '103 SEK');
  assert.equal(button.disabled, false);
  assert.equal(ui.element('quote-refresh-spinner').hidden, true);
  assert.match(ui.element('quote-refresh-status').textContent, /Nyare publicerade data/);
  responder = payload => ({ok:true,json:async()=>payload});
  await button.listeners.click();
  assert.match(ui.element('quote-refresh-status').textContent, /Inga nyare/);
  responder = () => {throw new Error('synthetic network error');};
  await button.listeners.click();
  assert.match(ui.element('quote-refresh-status').textContent, /inte fullständig/);
  assert.equal(ui.element('latest-price').textContent, '103 SEK');
  assert.equal(button.disabled, false);
});

test('daily-data refresh is awaited and still runs when the intraday cache fails', async () => {
  let fail = false;
  const ui = setup(payload => {if(fail) throw new Error('synthetic failure'); return {ok:true,json:async()=>payload};});
  await ui.api.refresh();
  let called = 0;
  ui.api.onRefresh(async () => { called++; return true; });
  fail = true;
  await ui.api.refresh();
  assert.equal(called, 1);
  assert.equal(ui.element('intraday-refresh').disabled, false);
});

test('refresh control lives outside the temporary panel so closing data cannot hide it', () => {
  const html=fs.readFileSync('docs/index.html','utf8');
  const button=html.indexOf('id="intraday-refresh"');
  assert(button > html.indexOf('class="quote-refresh-controls"'));
  assert(button < html.indexOf('<section id="intraday-panel"'));
  assert.match(html,/id="quote-refresh-status"[^>]*role="status"/);
});
