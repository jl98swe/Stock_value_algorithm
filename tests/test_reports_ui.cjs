const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('docs/assets/reports.js', 'utf8');

async function setup(today, upcoming, recent = [], missing_data = []) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {hidden: false, textContent: '', innerHTML: '', listeners: {}, attrs: {},
      addEventListener(event, handler) { this.listeners[event] = handler; },
      setAttribute(key, value) { this.attrs[key] = value; }});
    return elements.get(id);
  };
  let init;
  let tick;
  class Clock extends Date {
    constructor(...args) { super(...(args.length ? args : [today])); }
  }
  const sessions = [];
  for (let date = new Date('2026-09-01T00:00Z'); date <= new Date('2026-12-31T00:00Z'); date.setUTCDate(date.getUTCDate()+1)) {
    // Synthetic calendar fixture: Christmas and Boxing Day are closed.
    const day = date.toISOString().slice(0,10);
    if (![0,6].includes(date.getUTCDay()) && !['2026-12-24','2026-12-25','2026-12-31'].includes(day)) sessions.push(day);
  }
  const payload = {as_of_date: '2026-10-14', trading_sessions: sessions, trading_sessions_start: '2026-09-01', trading_sessions_end: '2026-12-31', upcoming, recent, missing_data};
  vm.runInNewContext(source, {Intl, Date: Clock, console, document: {getElementById: element, addEventListener(event, handler) {if(event === 'DOMContentLoaded') init=handler;}},
    fetch: async () => ({ok:true, json:async()=>payload}), setInterval: handler => {tick=handler;}});
  await init();
  return {element, tick};
}
const row = (ticker, day) => ({ticker, report_date_start: day, report_date_end: day});
const count = element => (element.innerHTML.match(/<tr[ >]/g)||[]).length;

test('previous EPS stays separate from current EPS, including zero and missing values', async () => {
  // Synthetic examples: waiting, newly reported, unchanged and missing history.
  const {element:e} = await setup('2026-10-15T12:00Z', [
    {...row('WAITING','2026-10-15'), previous_eps_ttm:4, previous_eps_ttm_currency:'SEK'},
    {...row('REPORTED','2026-10-15'), previous_eps_ttm:4, previous_eps_ttm_currency:'SEK', current_eps_ttm:5, new_eps_ttm:5, new_eps_ttm_currency:'USD'},
    {...row('UNCHANGED','2026-10-15'), previous_eps_ttm:0, previous_eps_ttm_currency:'SEK', new_eps_ttm:0, new_eps_ttm_currency:'SEK'},
    {...row('NOHISTORY','2026-10-15'), current_eps_ttm:5, previous_eps_ttm:null, new_eps_ttm:5, new_eps_ttm_currency:'SEK'},
  ]);
  const cells = [...e('upcoming-body').innerHTML.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)]
    .map(tr => [...tr[1].matchAll(/<td>([\s\S]*?)<\/td>/g)].map(td => td[1]));
  const byTicker = ticker => cells.find(row => row[0].includes(`>${ticker}</strong>`));
  assert(byTicker('WAITING')[5].includes('4,0000 SEK'));
  assert.equal(byTicker('WAITING')[6], '–');
  assert(byTicker('REPORTED')[5].includes('4,0000 SEK'));
  assert(byTicker('REPORTED')[6].includes('5,0000 USD'));
  assert(byTicker('UNCHANGED')[5].includes('0,0000 SEK'));
  assert(byTicker('UNCHANGED')[6].includes('0,0000 SEK'));
  assert.equal(byTicker('NOHISTORY')[5], '–');
  assert(byTicker('NOHISTORY')[6].includes('5,0000 SEK'));
});

test('new reported TTM is separate from estimates, missing data stays a dash', async () => {
  const {element:e} = await setup('2026-10-15T12:00Z', [
    {...row('REPORTED','2026-10-15'), new_eps_ttm:9.22, new_eps_ttm_currency:'SEK'},
    {...row('MISSING','2026-10-16'), new_eps_ttm:null},
    {...row('ZERO','2026-10-16'), new_eps_ttm:0, new_eps_ttm_currency:'USD'},
  ]);
  const html = e('upcoming-body').innerHTML;
  assert(html.includes('9,2200 SEK'));
  assert(html.includes('0,0000 USD'));
  for (const tr of html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
    assert.equal((tr[1].match(/<td>/g)||[]).length,9);
    if(tr[1].includes('MISSING')) assert.equal([...tr[1].matchAll(/<td>([\s\S]*?)<\/td>/g)][6][1],'–');
  }
});

test('today uses Stockholm date, shows all imminent reports, toggles both lists', async () => {
  const upcoming = Array.from({length:7},(_,i)=>row(`TODAY${i}`, '2026-10-15')).concat([row('NEXT','2026-10-16'), row('LATER','2026-10-19')]);
  const recent = Array.from({length:8},(_,i)=>({ticker:`R${i}`,report_date:`2026-10-${String(7+i).padStart(2,'0')}`,report_date_verified:true}));
  const {element:e} = await setup('2026-10-14T22:30:00Z', upcoming, recent);
  assert.equal(count(e('upcoming-body')),8);
  assert.equal((e('upcoming-body').innerHTML.match(/Idag/g)||[]).length,7);
  assert.equal(e('upcoming-count').textContent,'9');
  assert.equal(count(e('recent-body')),5);
  assert(!e('recent-body').innerHTML.includes('R0</strong>'));
  for (const id of ['upcoming','recent']) {
    assert.equal(e(`${id}-more`).hidden,false);
    e(`${id}-more`).listeners.click();
    assert.equal(e(`${id}-more`).textContent,'Visa mindre');
    assert.equal(e(`${id}-more`).attrs['aria-expanded'],'true');
    assert.equal(count(e(`${id}-body`)),id==='upcoming'?9:8);
    e(`${id}-more`).listeners.click();
    assert.equal(count(e(`${id}-body`)),id==='upcoming'?8:5);
  }
});

test('exchange holidays and weekends are excluded; old reports expire', async () => {
  const {element:e} = await setup('2026-12-23T12:00Z', [row('PAST','2026-12-22'),row('MONDAY','2026-12-28')], [{ticker:'OLD',report_date:'2026-09-01'}]);
  assert.equal(count(e('upcoming-body')),1);
  assert(e('upcoming-body').innerHTML.includes('1 handelsdag'));
  assert(!e('upcoming-body').innerHTML.includes('PAST'));
  assert.equal(e('recent-count').textContent,'0');
  assert.equal(e('upcoming-more').hidden,true);
  assert.equal(e('recent-more').hidden,true);
});

test('five future reports shown when none are imminent', async () => {
  const {element:e} = await setup('2026-10-15T12:00Z', Array.from({length:8},(_,i)=>row(`F${i}`,'2026-10-20')));
  assert.equal(count(e('upcoming-body')),5);
  e('upcoming-more').listeners.click();
  assert.equal(count(e('upcoming-body')),8);
});

// Synthetic examples: only confirmed missing report data gets an entry link.
test('missing EPS links to the selected stock form; future reports and zero stay unchanged', async () => {
  const {element:e} = await setup('2026-10-26T12:00Z', [
    {...row('MISSING.ST','2026-10-26'), new_eps_ttm:null},
    {...row('FUTURE.ST','2026-10-27'), new_eps_ttm:null},
    {...row('ZERO.ST','2026-10-26'), new_eps_ttm:0},
  ], [{ticker:'RECENT.ST',report_date:'2026-10-23',report_date_verified:true,eps_ttm_after:null}], [{ticker:'MISSING.ST'}]);
  const rows = [...e('upcoming-body').innerHTML.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)].map(x=>x[1]);
  assert(rows.find(x=>x.includes('>MISSING.ST</strong>')).includes('./review.html?ticker=MISSING.ST#eps-form-title'));
  assert(!rows.find(x=>x.includes('>FUTURE.ST</strong>')).includes('Lägg in EPS'));
  assert(!rows.find(x=>x.includes('>ZERO.ST</strong>')).includes('Lägg in EPS'));
  assert(e('recent-body').innerHTML.includes('./review.html?ticker=RECENT.ST#eps-form-title'));
});

test('homepage manual EPS action follows stock changes and opens the form on the website', () => {
  const app = fs.readFileSync('docs/assets/app.js','utf8');
  const section = app.slice(app.indexOf('  function renderStatus('), app.indexOf('  function isCompanyNews('));
  const state = {selectedTicker:'FIRST.ST', dashboard:{meta:{}}};
  const nodes = {};
  const render = new Function('state','$','prettyDate','formatModelEps', section + '; return renderStatus;')(state, id=>nodes[id] ||= {}, x=>x || '–', ()=> '–');
  render({});
  assert.equal(nodes['report-workflow-link'].href, './review.html?ticker=FIRST.ST#eps-form-title');
  state.selectedTicker='SECOND-B.ST';
  render({});
  assert.equal(nodes['report-workflow-link'].href, './review.html?ticker=SECOND-B.ST#eps-form-title');
});
