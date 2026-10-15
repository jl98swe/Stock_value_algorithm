const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('docs/assets/reports.js', 'utf8');

async function setup(today, upcoming, recent = []) {
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
  const payload = {as_of_date: '2026-10-14', trading_sessions: sessions, trading_sessions_start: '2026-09-01', trading_sessions_end: '2026-12-31', upcoming, recent};
  vm.runInNewContext(source, {Intl, Date: Clock, console, document: {getElementById: element, addEventListener(event, handler) {if(event === 'DOMContentLoaded') init=handler;}},
    fetch: async () => ({ok:true, json:async()=>payload}), setInterval: handler => {tick=handler;}});
  await init();
  return {element, tick};
}
const row = (ticker, day) => ({ticker, report_date_start: day, report_date_end: day});
const count = element => (element.innerHTML.match(/<tr[ >]/g)||[]).length;

test('today uses Stockholm date, shows all imminent reports, toggles both lists', async () => {
  const upcoming = Array.from({length:7},(_,i)=>row(`TODAY${i}`, '2026-10-15')).concat([row('NEXT','2026-10-16'), row('LATER','2026-10-19')]);
  const recent = Array.from({length:8},(_,i)=>({ticker:`R${i}`,report_date:`2026-10-${String(7+i).padStart(2,'0')}`,report_date_verified:true}));
  const {element:e} = await setup('2026-10-14T22:30:00Z', upcoming, recent);
  assert.equal(count(e('upcoming-body')),8);
  assert.equal((e('upcoming-body').innerHTML.match(/I dag/g)||[]).length,7);
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
