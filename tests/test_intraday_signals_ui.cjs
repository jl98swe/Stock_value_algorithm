// Synthetic examples: shared cache flows through the actual page scripts.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('signals page refreshes preliminary selection and falls back without changing executions',async()=>{
 const elements=new Map(),events=new Map();
 const el=id=>{if(!elements.has(id)) elements.set(id,{value:'',textContent:'',innerHTML:'',hidden:true,addEventListener(){}});return elements.get(id)};
 let now=Date.parse('2026-10-16T11:30:00+02:00');
 class Clock extends Date {static now(){return now}}
 const stock=(score)=>({latest:{date:'2026-10-15',score},position:{lots:0,max_lots:1},next_action:{type:'NONE'},strategy_filter:{buy_allowed:true},signals:[]});
 const a=stock(50),b=stock(.5);
 a.signals=[{status:'executed',side:'SELL',execution_date:'2026-10-15',signal_date:'2026-10-14',execution_price:100,score:99.5}];
 const overviews={meta:{trading_dates:['2026-10-15'],rules:{buy_score:1,sell_score:99}},strategies:{standard:{stocks:{'A.ST':a,'B.ST':b}}}};
 const cache={schema_version:1,session_date:'2026-10-16',generated_at:'2026-10-16T11:20:00+02:00',expires_at:'2026-10-17T00:00:00+02:00',stocks:{}};
 function quote(ticker,score){cache.stocks[ticker]={latest:{price:100,currency:'SEK',as_of:'2026-10-16T11:10:00+02:00'},valuation:{preliminary:true,score,price:100,currency:'SEK',as_of:'2026-10-16T11:10:00+02:00',basis_date:'2026-10-15',session:'2026-10-16'}}}
 quote('A.ST',.25);quote('B.ST',50);
 const document={body:{dataset:{overview:'signals'}},hidden:false,getElementById:el,querySelectorAll:()=>[],addEventListener:(key,fn)=>{events.set(key,fn)}};
 const window={reportDataStatus:{setTickers(){}},strategySelection:{set(){}}};
 const context=vm.createContext({window,document,Date:Clock,Intl,URL,URLSearchParams,console,setInterval(){},localStorage:{getItem(){return null}},location:{href:'https://example.test/signals.html',search:''},history:{replaceState(){}},fetch:async url=>({ok:true,json:async()=>{
  if(url.includes('raw.githubusercontent')) return cache;
  if(url.includes('strategy_overviews')) return overviews;
  if(url.includes('signal_prices')) return {stocks:{}};
  return {stocks:[{ticker:'A.ST',currency:'SEK'},{ticker:'B.ST',currency:'SEK'}]};
 }})});
 for(const file of ['intraday.js','overview.js']) vm.runInContext(fs.readFileSync(`docs/assets/${file}`,'utf8'),context);
 await window.intradayQuotes.refresh();
 await events.get('DOMContentLoaded')();
 assert.match(el('upcoming-signals-body').innerHTML,/A.ST/);
 assert.doesNotMatch(el('upcoming-signals-body').innerHTML,/B.ST/);
 assert.match(el('upcoming-signals-body').innerHTML,/Preliminär · 11:10/);
 assert.match(el('upcoming-signals-body').innerHTML,/0,25/);
 const recent=el('recent-signals-body').innerHTML;
 assert.match(recent,/A.ST/);
 quote('A.ST',50);quote('B.ST',.75);
 await window.intradayQuotes.refresh();
 assert.doesNotMatch(el('upcoming-signals-body').innerHTML,/A.ST/);
 assert.match(el('upcoming-signals-body').innerHTML,/B.ST/);
 assert.match(el('upcoming-signals-body').innerHTML,/0,75/);
 assert.equal(el('recent-signals-body').innerHTML,recent);
 now=Date.parse('2026-10-16T18:00:00+02:00');
 cache.stocks['B.ST'].latest.fetched_at='2026-10-16T17:30:00+02:00';
 cache.stocks['B.ST'].valuation.preliminary=false;
 await window.intradayQuotes.refresh();
 assert.match(el('upcoming-signals-body').innerHTML,/Efter stängning/);
 assert.doesNotMatch(el('upcoming-signals-body').innerHTML,/Preliminär|inväntar stängning/);
 assert.match(el('upcoming-signals-body').innerHTML,/Inväntar ordinarie signalberäkning/);
 assert.equal(el('recent-signals-body').innerHTML,recent);
 now=Date.parse('2026-10-17T01:00:00+02:00');
 await window.intradayQuotes.refresh();
 assert.doesNotMatch(el('upcoming-signals-body').innerHTML,/Preliminär/);
 assert.match(el('upcoming-signals-body').innerHTML,/Stängning/);
 assert.match(el('upcoming-signals-body').innerHTML,/0,5/);
 assert.equal(el('recent-signals-body').innerHTML,recent);
});
