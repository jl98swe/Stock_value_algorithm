// Synthetic confirmed orders rendered by the actual page, before and after opening.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

test('confirmed buys/sells render without fills, then update in place after execution',async()=>{
 const elements=new Map(),listeners={};
 const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',addEventListener(){}});return elements.get(id)};
 let version='2026-11-17T18:00:00+01:00';
 const dates=Array.from({length:21},(_,i)=>`2026-10-${String(i+1).padStart(2,'0')}`);
 const signals=[
  {signal_id:'buy',signal_date:'2026-10-21',side:'BUY',status:'awaiting_next_session',score:.5,execute_on:'2026-10-22'},
  {signal_id:'sell',signal_date:'2026-10-20',side:'SELL',status:'pending',score:99.5,execution_date:'2026-10-22',execution_price:999},
  ...['cancelled_lock','suppressed_capacity','deferred_cooldown','cancelled_filter'].map(status=>({signal_id:status,signal_date:'2026-10-21',side:'BUY',status})),
  {signal_id:'old',signal_date:'2026-10-01',side:'BUY',status:'executed',execution_date:'2026-10-03'},
  {signal_id:'future',signal_date:'2026-10-23',side:'SELL',status:'pending'}
 ];
 const overviews=()=>({meta:{generated_at:version,trading_dates:dates,latest_execution_date:'2026-10-22'},strategies:{standard:{stocks:{'EXAMPLE.ST':{latest:{score:50},position:{lots:0},signals}}}}});
 const window={addEventListener:(n,f)=>listeners[n]=f,strategySelection:{set(){}},reportDataStatus:{setTickers(){}}};
 const document={body:{dataset:{overview:'signals'}},getElementById:el,querySelectorAll:()=>[],addEventListener:(n,f)=>listeners[n]=f};
 vm.runInNewContext(fs.readFileSync('docs/assets/overview.js','utf8'),{
  window,document,Intl,Date,URL,URLSearchParams,console,localStorage:{getItem(){}},location:{href:'https://example.test/signals.html',search:''},history:{replaceState(){}},
  fetch:async url=>({ok:true,json:async()=>{
   if(url.includes('signal_prices'))return {generated_at:version,stocks:{}};
   if(url.includes('strategy_overviews'))return overviews();
   return {generated_at:version,stocks:[{ticker:'EXAMPLE.ST'}]};
  }})
 });
 await listeners.DOMContentLoaded();
 assert.equal(el('recent-count').textContent,'2');
 const before=el('recent-signals-body').innerHTML;
 assert(before.indexOf('Köp')<before.indexOf('Sälj'));
 assert.equal((before.match(/<strong>–<\/strong>/g)||[]).length,2);
 assert.doesNotMatch(before,/999|22 okt/); // planned or incomplete fills must stay blank
 assert.match(before,/Signal /);
 Object.assign(signals[0],{status:'executed',execution_date:'2026-10-22',execution_price:123});
 version='2026-11-18T09:20:00+01:00';
 await listeners['stock-data-version']({detail:{version}});
 assert.equal(el('recent-count').textContent,'2');
 assert.match(el('recent-signals-body').innerHTML,/123 SEK/);
 assert.equal((el('recent-signals-body').innerHTML.match(/<strong>–<\/strong>/g)||[]).length,1);
});
