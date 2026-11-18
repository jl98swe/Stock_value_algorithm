// Synthetic publication race: a client must retry the same version until applied.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
test('initial and repeated checks notify consumers; hidden pages wait',async()=>{
 const listeners={},events=[];let interval,hidden=false;
 const document={get hidden(){return hidden},addEventListener:(n,f)=>listeners[n]=f};
 const window={addEventListener:(n,f)=>listeners[n]=f,dispatchEvent:e=>events.push(e.detail.version)};
 vm.runInNewContext(fs.readFileSync('docs/assets/live-refresh.js','utf8'),{
  document,window,console,CustomEvent:class{constructor(n,o){this.detail=o.detail}},
  fetch:async()=>({ok:true,json:async()=>({generated_at:'example-version'})}),
  setInterval:f=>interval=f
 });
 await new Promise(setImmediate);
 assert.deepEqual(events,['example-version']);
 await interval();assert.equal(events.length,2); // retry after consumer rejected incomplete files
 hidden=true;await interval();assert.equal(events.length,2);
 hidden=false;await listeners.visibilitychange();await new Promise(setImmediate);
 assert.equal(events.length,3);
});
test('signals retain the old snapshot during publication and apply the same version on retry',async()=>{
 const elements=new Map(),listeners={};
 const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',addEventListener(){}});return elements.get(id)};
 let version='2026-11-18T09:00:00+01:00',complete=true,executed=false;
 const window={addEventListener:(n,f)=>listeners[n]=f,strategySelection:{set(){}},reportDataStatus:{setTickers(){}}};
 const document={body:{dataset:{overview:'signals'}},getElementById:el,querySelectorAll:()=>[],addEventListener:(n,f)=>listeners[n]=f};
 vm.runInNewContext(fs.readFileSync('docs/assets/overview.js','utf8'),{
  window,document,Intl,Date,URL,URLSearchParams,console,localStorage:{getItem(){}},location:{href:'https://example.test/signals.html',search:''},history:{replaceState(){}},
  fetch:async url=>({ok:true,json:async()=>{
   if(url.includes('signal_prices'))return {generated_at:complete?version:'old',stocks:{}};
   if(url.includes('strategy_overviews'))return {meta:{generated_at:version,trading_dates:['2026-11-17'],latest_execution_date:'2026-11-18'},strategies:{standard:{stocks:{'EXAMPLE.ST':{latest:{score:50},position:{lots:0},signals:executed?[{status:'executed',execution_date:'2026-11-18',signal_date:'2026-11-17',side:'BUY',execution_price:100}]:[]}}}}};
   return {generated_at:version,stocks:[{ticker:'EXAMPLE.ST'}]};
  }})
 });
 await listeners.DOMContentLoaded();assert.doesNotMatch(el('recent-signals-body').innerHTML,/EXAMPLE/);
 version='2026-11-18T09:20:00+01:00';executed=true;complete=false;
 await listeners['stock-data-version']({detail:{version}});
 assert.doesNotMatch(el('recent-signals-body').innerHTML,/EXAMPLE/);
 complete=true;await listeners['stock-data-version']({detail:{version}});
 assert.match(el('recent-signals-body').innerHTML,/EXAMPLE/);
 assert.equal(el('recent-count').textContent,'1');
});
