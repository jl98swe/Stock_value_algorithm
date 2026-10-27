// Synthetic fixtures: verify page scope, filter changes and slow warning responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'docs/assets/report-data-status.js'), 'utf8');
const missing = ['AAA.ST', 'BBB.ST', 'CCC.ST'].map(ticker => ({ticker, report_date:'2026-10-15', message:'Syntetisk varning'}));
function element() {
  return {children:[], textContent:'', append(...items){this.children.push(...items);},
    setAttribute(){}, remove(){this.parent.children = this.parent.children.filter(child => child !== this);},
    prepend(child){child.parent=this; this.children.unshift(child);}};
}
function setup(page, initialPayload = {missing_data:missing}, today = '2026-10-15T12:00Z') {
  const main = element();
  let ready;
  let resolveResponse;
  let interval;
  let visibility;
  let data = initialPayload;
  let currentDay = today;
  class Clock extends Date { constructor(...args) {super(...(args.length ? args : [currentDay]));} }
  const document = {body:{dataset:{overview:page==='positions' || page==='signals' ? page : undefined}},
    addEventListener(event, callback){if(event==='DOMContentLoaded') ready=callback; if(event==='visibilitychange') visibility=callback;}, querySelector(){return main;}, createElement:element};
  const window = {};
  vm.runInNewContext(source, {document, window, location:{pathname:`/project/${page}.html`},
    Date:Clock, Intl, setInterval:callback=>{interval=callback;},
    fetch:()=>resolveResponse ? Promise.resolve({ok:true,json:async()=>data}) : new Promise(resolve => {resolveResponse=resolve;}), console});
  return {main, api:window.reportDataStatus,
    async tick(day, nextPayload=data) { currentDay=day; data=nextPayload; await interval(); },
    async reopen(nextPayload=data) {data=nextPayload; await visibility();},
    async load(beforeResponse){
    const loading=ready();
    beforeResponse?.();
    resolveResponse({ok:true,json:async()=>data});
    await loading;
  }};
}
const shown = main => main.children.flatMap(panel => panel.children.at(-1).children.map(li=>li.children[0].textContent));
(async () => {
  for (const page of ['signals','reports']) {
    const test=setup(page); await test.load();
    assert.deepEqual(shown(test.main), ['AAA.ST','BBB.ST','CCC.ST']);
    const row = test.main.children[0].children.at(-1).children[1];
    assert.equal(row.children.at(-1).textContent, 'Lägg in EPS');
    assert.equal(row.children.at(-1).href, './review.html?ticker=BBB.ST#eps-form-title');
  }
  for (const page of ['index','review']) {
    const test=setup(page);
    await test.load(()=>test.api.setTickers(['BBB.ST']));
    assert.deepEqual(shown(test.main), ['BBB.ST']);
    const entry = test.main.children[0].children.at(-1).children[0].children.at(-1);
    assert.equal(entry.href, page === 'review' ? '#eps-form-title' : './review.html?ticker=BBB.ST#eps-form-title');
    test.api.setTickers(['NO-WARNING.ST']);
    assert.deepEqual(shown(test.main), []);
    test.api.setTickers(['AAA.ST']);
    assert.deepEqual(shown(test.main), ['AAA.ST']);
    assert.equal(test.main.children.length,1);
  }
  const test=setup('positions'); await test.load();
  assert.deepEqual(shown(test.main), []);
  // Run the actual table renderer so warning scope uses the same rows as the table.
  const overview=fs.readFileSync(path.join(root,'docs/assets/overview.js'),'utf8');
  const renderSource=overview.slice(overview.indexOf('  function renderPositions('),overview.indexOf('  function signalCandidate('));
  const nodes={};
  const render=new Function('window','$','stockMeta','textIncludes','stockHref','esc','money','number','pct','score','prettyDate',`${renderSource}; return renderPositions;`)(
    {reportDataStatus:test.api}, id=>nodes[id] ||= {}, (_,ticker)=>({name:ticker}),
    (row,needle)=>!needle || row.ticker.includes(needle), value=>value, value=>value,
    value=>value, Number, value=>value, value=>value, value=>value);
  const dashboard={stocks:{'AAA.ST':{position:{lots:1}},'BBB.ST':{position:{lots:0}},'CCC.ST':{position:{lots:2}},'DDD.ST':{position:{lots:1},active_for_updates:false}}};
  render(dashboard,{},'');
  assert.deepEqual(shown(test.main),['AAA.ST','CCC.ST']);
  assert.equal(nodes['summary-count'].textContent,'2');
  render(dashboard,{},'CCC');
  assert.deepEqual(shown(test.main),['CCC.ST']);
  render(dashboard,{},'BBB');
  assert.deepEqual(shown(test.main),[]);
  render({stocks:{'BBB.ST':{position:{lots:1}}}}, {}, '');
  assert.deepEqual(shown(test.main),['BBB.ST']);
  // Synthetic stale export rolls into report day before the next backend run.
  const calendar = [
    {ticker:'TODAY.ST',report_date_start:'2026-10-15',report_date_end:'2026-10-15',new_eps_ttm:null},
    {ticker:'TOMORROW.ST',report_date_start:'2026-10-16',report_date_end:'2026-10-16',new_eps_ttm:null},
    {ticker:'ZERO.ST',report_date_start:'2026-10-15',report_date_end:'2026-10-15',new_eps_ttm:0},
    {ticker:'NOEPS.ST',report_date_start:'2026-10-15',report_date_end:'2026-10-15',new_eps_ttm:null},
    {ticker:'RECENT.ST',report_date_start:'2026-10-15',report_date_end:'2026-10-15',new_eps_ttm:null},
  ];
  const stale = {data_checked_at:'2026-10-14',missing_data:[],upcoming:calendar,
    recent:[{ticker:'RECENT.ST',report_date:'2026-10-15',eps_ttm_after:0}],
    reports_without_eps:[{ticker:'NOEPS.ST',report_date:'2026-10-15'}]};
  const rollover=setup('reports',stale,'2026-10-14T21:30Z'); await rollover.load();
  assert.deepEqual(shown(rollover.main),[]);
  await rollover.tick('2026-10-14T22:30Z'); // Already Oct 15 in Stockholm.
  assert.deepEqual(shown(rollover.main),['TODAY.ST']);
  const updated={...stale,upcoming:calendar.map(r=>r.ticker==='TODAY.ST'?{...r,new_eps_ttm:5}:r)};
  await rollover.reopen(updated);
  assert.deepEqual(shown(rollover.main),[]);
  await rollover.tick('2026-10-16T08:00Z');
  assert.deepEqual(shown(rollover.main),['TOMORROW.ST']);
  console.log('EPS warning UI passed: all pages, stock changes, active positions, search, strategy changes and delayed data.');
})().catch(error=>{console.error(error);process.exitCode=1;});
