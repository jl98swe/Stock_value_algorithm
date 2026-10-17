// Synthetic examples: refresh a complete published snapshot without reloading.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup() {
 const elements=new Map(),renders=[];
 const element=id=>{if(!elements.has(id))elements.set(id,{textContent:'',value:'search preserved'});return elements.get(id)};
 let generation='2026-10-16T19:00:00+02:00',bad=false,hold=null;
 const payload=url=>{
  if(url.includes('stocks.json'))return {generated_at:generation,stocks:[{ticker:'EXAMPLE.ST'}]};
  if(url.endsWith('dashboard/index.json'))return {meta:{generated_at:generation},files:{'EXAMPLE.ST':'EXAMPLE.ST.json'}};
  if(url.includes('strategy_overviews'))return {meta:{generated_at:bad?'old':generation},strategies:{standard:{stocks:{'EXAMPLE.ST':{latest:{close:105}}}}}};
  if(url.includes('backtests'))return {standard:{closed_trades:[]}};
  if(url.includes('dashboard/EXAMPLE'))return {latest:{close:105,date:'2026-10-16'}};
  return {};
 };
 const window={strategySelection:{get:()=> 'standard'}};
 let source=fs.readFileSync('docs/assets/app.js','utf8');
 source=source.replace("document.addEventListener('DOMContentLoaded', init);", `
  renderRules=()=>window.renders.push('rules');
  renderStockList=()=>window.renders.push('list');
  renderSelected=()=>window.renders.push('selected');
  window.testing={state,refreshPublishedData};`);
 window.renders=renders;
 vm.runInNewContext(source,{window,document:{getElementById:element},Intl,Date,fetch:async url=>{
  if(hold && url.includes('backtests'))await hold;
  return {ok:true,json:async()=>payload(url)};
 }});
 const api=window.testing;
 Object.assign(api.state,{selectedTicker:'EXAMPLE.ST',stocksPayload:{generated_at:'old'},dashboard:{stocks:{}},overviews:{old:true},range:'1m'});
 return {...api,renders,element,setBad:()=>bad=true,setHold:p=>hold=p};
}
test('new final data replaces the complete snapshot while retaining stock, strategy, range and search',async()=>{
 const ui=setup();
 assert.equal(await ui.refreshPublishedData(),true);
 assert.equal(ui.state.dashboard.stocks['EXAMPLE.ST'].latest.close,105);
 assert.equal(ui.state.selectedTicker,'EXAMPLE.ST');
 assert.equal(ui.state.strategy,'standard');
 assert.equal(ui.state.range,'1m');
 assert.equal(ui.element('stock-search').value,'search preserved');
 assert.deepEqual(ui.renders,['rules','list','selected']);
 assert.equal(await ui.refreshPublishedData(),false);
 assert.equal(ui.renders.length,3);
});
test('an incomplete publication keeps the old snapshot intact',async()=>{
 const ui=setup();ui.setBad();const old=ui.state.dashboard;
 await assert.rejects(ui.refreshPublishedData(),/publicering pågår/);
 assert.equal(ui.state.dashboard,old);
 assert.equal(ui.renders.length,0);
});
test('a stock switch while loading is never replaced by the former stock',async()=>{
 const ui=setup();let release;
 ui.setHold(new Promise(resolve=>release=resolve));
 const pending=ui.refreshPublishedData();
 await new Promise(resolve=>setImmediate(resolve));
 ui.state.selectedTicker='OTHER.ST';release();
 assert.equal(await pending,false);
 assert.equal(ui.state.selectedTicker,'OTHER.ST');
 assert.equal(ui.renders.length,0);
});
