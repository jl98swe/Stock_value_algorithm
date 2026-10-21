// Synthetic examples for expiry, daily-close precedence and stock switching.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(request = null, withoutControl = false, time = '2026-10-15T13:01:00+02:00') {
  const elements = new Map();
  let interval;
  const element = id => {
    if (/^intraday-(panel|open|daily|note)/.test(id)) return null;
    if (withoutControl && (id === 'intraday-refresh' || id.startsWith('quote-refresh-'))) return null;
    if (!elements.has(id)) elements.set(id, { textContent: '', className: '', hidden: true, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; } });
    return elements.get(id);
  };
  const now = Date.parse(time);
  class Clock extends Date { static now() { return now; } }
  const payload = { schema_version: 1, session_date: '2026-10-15',
    generated_at: '2026-10-15T13:00:00+02:00', expires_at: '2026-10-16T00:00:00+02:00',
    stocks: { 'EXAMPLE.ST': { latest: { price: 102, currency: 'SEK', source: 'Nasdaq', as_of: '2026-10-15T12:44:00+02:00' },
      opening: { price: 100, source: 'Nasdaq', as_of: '2026-10-15T09:00:30+02:00' } } } };
  const window = {};
  vm.runInNewContext(fs.readFileSync('docs/assets/intraday.js', 'utf8'), { window,
    document: { getElementById: element, addEventListener() {}, dispatchEvent() {} }, CustomEvent: class { constructor(type) { this.type = type; } }, Date: Clock, Intl,
    setInterval(fn) { interval = fn; }, fetch: async () => request ? request(payload) : ({ ok: true, json: async () => payload }) });
  return { api: window.intradayQuotes, payload, now, element, runInterval: () => interval() };
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
  api.select('OTHER.ST', { ...daily, close: 250 });
  assert.equal(element('latest-price').textContent, '250 SEK');
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

test('the unused manual refresh control and explanatory copy are absent from the homepage', () => {
  const html=fs.readFileSync('docs/index.html','utf8');
  assert.doesNotMatch(html,/id="intraday-refresh"|quote-refresh-controls|quote-refresh-status|Kontrollera senaste data|En kontroll tar vanligen/);
});

test('the redundant quote panel is absent while intraday updates remain enabled', () => {
  const html = fs.readFileSync('docs/index.html', 'utf8');
  const script = fs.readFileSync('docs/assets/intraday.js', 'utf8');
  assert.doesNotMatch(html, /intraday-panel|intraday-open|intraday-daily|intraday-note|Tillfälliga dagskurser/);
  assert.doesNotMatch(script, /intraday-panel|intraday-open|intraday-daily|intraday-note/);
  assert.match(html, /assets\/intraday\.js\?v=[^"\s]+/);
});

test('automatic quote and daily refresh still run with no refresh control in the DOM', async () => {
  const ui = setup(null, true);
  await ui.api.refresh();
  ui.api.select('EXAMPLE.ST', {date:'2026-10-14',close:100,currency:'SEK'});
  let dailyRefreshes = 0;
  ui.api.onRefresh(async () => { dailyRefreshes++; return false; });
  ui.payload.stocks['EXAMPLE.ST'].latest.price = 104;
  ui.runInterval();
  await ui.api.refresh();
  assert.equal(ui.element('latest-price').textContent, '104 SEK');
  assert.equal(dailyRefreshes, 1);
});


test('source trade time at 17:30 determines status even when retrieved late', async () => {
  const {api, payload, now} = setup(null, false, '2026-10-15T20:00:00+02:00');
  await api.refresh();
  const item = payload.stocks['EXAMPLE.ST'];
  item.valuation = {preliminary:false,score:42,price:102,currency:'SEK',
    as_of:item.latest.as_of,basis_date:'2026-10-14',session:'2026-10-15'};
  for (const [quoted, expected] of [
    ['2026-10-15T17:29:59+02:00',true],
    ['2026-10-15T17:30:00+02:00',false],
    ['2026-10-15T15:30:00Z',false],
    ['2026-10-15T19:00:00+02:00',false],
  ]) {
    item.latest.as_of = quoted;
    item.latest.fetched_at = '2026-10-15T19:30:00+02:00';
    item.valuation.as_of = quoted;
    // Cache publication at 19:30 cannot reclassify an older quote.
    payload.generated_at = '2026-10-15T19:30:00+02:00';
    const preview = api.preview('EXAMPLE.ST','2026-10-14',now);
    assert.equal(preview.preliminary,expected,quoted);
    assert.equal(preview.candle.preliminary,expected,quoted);
    assert.equal(preview.score,42);
    assert.equal(api.currentValuation(payload,'EXAMPLE.ST','2026-10-14','SEK',now).preliminary,expected);
  }
});


test('homepage score and chart use ordinary styling for data fetched after 17:30', () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id,{textContent:'',hidden:true,style:{},
      classList:{toggle(name,value){this[name]=value}},closest(){return this},hidePopover(){}});
    return elements.get(id);
  };
  let option;
  const preview = {score:42,as_of:'2026-10-15T13:15:00+02:00',preliminary:true,candle:{date:'2026-10-15',open:100,high:105,low:99,close:102,completeOHLC:true,preliminary:true}};
  const window = {strategySelection:{get:()=> 'standard'},intradayQuotes:{preview:()=>preview},echarts:{}};
  const source = fs.readFileSync('docs/assets/app.js','utf8').replace(
    "document.addEventListener('DOMContentLoaded', init);",
    'window.testing={state,renderMetrics,renderChart};');
  vm.runInNewContext(source,{window,document:{getElementById:element,dispatchEvent(){}},Intl,Date,
    CustomEvent:class{},echarts:{}});
  const api=window.testing;
  Object.assign(api.state,{selectedTicker:'EXAMPLE.ST',range:'all',chart:{setOption(value){option=value}},stocksPayload:{stocks:[]}});
  const data={latest:{date:'2026-10-14',score:50},candles:[{date:'2026-10-14',open:99,high:101,low:98,close:100}],scores:[{date:'2026-10-14',value:50}]};
  api.renderMetrics(data);api.renderChart('EXAMPLE.ST',data);
  assert.match(element('metric-score-status').textContent,/Preliminär/);
  assert.equal(element('chart-preliminary-note').hidden,false);
  assert.equal(option.series[0].data.at(-1).itemStyle.color,'#8056b3');
  const preliminaryTooltip=option.tooltip.formatter([{axisValue:'2026-10-15'}]);
  assert.match(preliminaryTooltip,/2026-10-15 · 13:15/);
  assert.match(preliminaryTooltip,/O 100 · H 105 · L 99 · C 102/);
  preview.preliminary=false;preview.candle.preliminary=false;
  api.renderMetrics(data);api.renderChart('EXAMPLE.ST',data);
  assert.doesNotMatch(element('metric-score-status').textContent,/Preliminär/);
  assert.equal(element('metric-score').classList['is-preliminary'],false);
  assert.notEqual(element('metric-score').style.color,'#8056b3');
  assert.equal(element('chart-preliminary-note').hidden,true);
  assert.equal(option.series[1].data.at(-1),42);
  assert.equal(option.series[0].data.at(-1)[1],102);
  const tooltip=option.tooltip.formatter([{axisValue:'2026-10-15'}]);
  assert.doesNotMatch(tooltip,/Preliminär|Kan ändras före/);
  assert.doesNotMatch(tooltip,/Efter stängning|Senaste avslut|13:15|Score/);
  assert.match(tooltip,/O 100 · H 105 · L 99 · C 102/);
  assert.match(tooltip,/Värderingspoäng <strong>42/);
  assert.equal(element('metric-score-status').hidden,true);
  assert.equal(element('metric-zone').textContent,'Neutral');
  const historicalTooltip=option.tooltip.formatter([{axisValue:'2026-10-14'}]);
  assert.match(historicalTooltip,/Värderingspoäng/);
  assert.doesNotMatch(historicalTooltip,/Score/);
});

// Synthetic example: a closing fetch uses the ordinary closing label, without trade time.
test('header keeps trade time only for preliminary quotes', async () => {
  const ui = setup(null, false, '2026-10-15T18:00:00+02:00');
  await ui.api.refresh();
  const daily = {date:'2026-10-14',close:100,currency:'SEK'};
  const quote = ui.payload.stocks['EXAMPLE.ST'].latest;
  quote.as_of = '2026-10-15T17:29:00+02:00';
  quote.fetched_at = '2026-10-15T17:29:00+02:00';
  ui.api.select('EXAMPLE.ST',daily);
  assert.match(ui.element('stock-date').textContent,/Senaste avslut 17:29/);
  quote.fetched_at = '2026-10-15T18:00:00+02:00';
  ui.api.select('EXAMPLE.ST',daily);
  assert.match(ui.element('stock-date').textContent,/Senaste avslut 17:29/);
  quote.as_of = '2026-10-15T17:30:00+02:00';
  ui.api.select('EXAMPLE.ST',daily);
  assert.equal(ui.element('stock-date').textContent,'Stängning 2026-10-15 · Nasdaq · SEK');
  assert.doesNotMatch(ui.element('quote-refresh-status').textContent,/Senaste avslut/);
  assert.equal(ui.api.preview('EXAMPLE.ST',daily.date).as_of,quote.as_of);
});
