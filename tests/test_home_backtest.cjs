const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {fullHistoryRows} = require('../docs/assets/method.js');
const app = fs.readFileSync(path.join(__dirname, '../docs/assets/app.js'), 'utf8');
const candles = [{date:'2019-09-02',close:100},{date:'2024-10-09',close:110},{date:'2026-10-08',close:120}];
// Synthetic fixtures, deliberately different results for each strategy.
const variants = {
  standard:{closed_trades:[{return_pct:10},{return_pct:20}],open_lots:[{current_return_pct:999}]},
  ma200:{closed_trades:[{return_pct:-10}]},
  report_avoidance:{closed_trades:[]},
  _dividends:[{date:'2024-10-09',amount:5}]
};
const index = {candles:[{date:'2024-10-09',close:200},{date:'2026-10-08',close:240}]};

test('shared calculations load on homepage without starting the method page', () => {
  const window = {}, document = {getElementById:()=>null};
  new Function('window','document',fs.readFileSync(path.join(__dirname,'../docs/assets/method.js'),'utf8'))(window,document);
  assert.equal(typeof window.backtestMetrics.fullHistoryRows,'function');
  const html = fs.readFileSync(path.join(__dirname,'../docs/index.html'),'utf8');
  assert(html.indexOf('./assets/method.js') < html.indexOf('./assets/app.js'));
});

test('all strategies and references use full history and disclose actual benchmark coverage', () => {
  const rows = fullHistoryRows({candles}, variants, index);
  assert.deepEqual(rows.map(r=>r.id), ['standard','ma200','report_avoidance','buy_and_hold','omxsgi']);
  assert(Math.abs(rows[0].return_pct - 32) < 1e-9);
  assert.equal(rows[0].trade_count,2); // excludes the unrealized open position
  assert(Math.abs(rows[1].return_pct + 10) < 1e-9);
  assert.equal(rows[2].return_pct,null);
  assert(Math.abs(rows[3].return_pct - ((120*.9975+5)/(100*1.0025)-1)*100) < 1e-9);
  assert(Math.abs(rows[4].return_pct - 20) < 1e-9);
  assert.equal(rows[3].start,'2019-09-02');
  assert.equal(rows[4].start,'2024-10-09');
  assert(rows.every(r=>r.end==='2026-10-08'));
  assert.equal(fullHistoryRows({candles},variants,null)[4].return_pct,null);
});

test('homepage comparison render ignores active strategy and chart range', () => {
  const functionSource = app.slice(app.indexOf('  function renderTables(data) {'), app.indexOf('  function sliceData('));
  assert(functionSource.includes('fullHistoryRows'));
  // Execute the production renderer, including its separate filtered trade list.
  const elements = new Map();
  const $ = id => { if(!elements.has(id)) elements.set(id,{querySelectorAll:()=>[]}); return elements.get(id); };
  const state = {selectedTicker:'TEST.ST', strategy:'standard',range:'3m',dashboard:{stocks:{'TEST.ST':{candles}}},
    backtests:{'TEST.ST':variants},indexData:index,expanded:{trades:new Set()}};
  const render = new Function('state','window','$','prettyDate','pct','holdingDays','fmt','updateToggle',
    `${functionSource}; return renderTables;`)(state,
      {backtestMetrics:{fullHistoryRows},strategySelection:{names:{standard:'Standard',ma200:'MA200',report_avoidance:'Rapportundvikande'}}},
      $, value=>value || '–', value=>value == null ? '–' : String(value),()=>0,{format:String},()=>{});
  render({candles,closed_trades:[],open_lots:[]});
  const initial = $('strategy-table').innerHTML;
  for(const strategy of ['standard','ma200','report_avoidance']) for(const range of ['3m','ytd','1y','3y','5y','all']) {
    state.strategy=strategy;state.range=range;
    render({candles:candles.slice(-1),closed_trades:[],open_lots:[]});
    assert.equal($('strategy-table').innerHTML,initial);
  }
  assert.equal((initial.match(/<tr>/g)||[]).length,6);
  assert(initial.includes('2019-09-02'));
});
