const assert=require('node:assert/strict');
const {signalCandidate,number}=require('../docs/assets/overview.js');
const stock={latest:{score:.5},position:{lots:0,max_lots:1},next_action:{type:'NONE'},strategy_filter:{buy_allowed:true}};
const candidate=data=>signalCandidate('TEST',data,{name:'Test'},{buy_score:1,sell_score:99});
assert.equal(number(null),null);
assert.equal(candidate(stock).side,'BUY');
assert.equal(candidate({...stock,strategy_filter:{buy_allowed:false}}),null);
assert.equal(candidate({...stock,position:{lots:1,max_lots:1}}),null);
assert.equal(candidate({...stock,latest:{score:100}}),null); // no sell without a position
assert.equal(candidate({...stock,latest:{score:100},position:{lots:1},strategy_filter:{buy_allowed:false}}).side,'SELL');
const report={...stock,latest:{score:50,fundamental_lock:true},position:{lots:1,sell_armed:false},
 next_action:{type:'SELL',exit_reason:'report',execute_on:'2026-02-09'},strategy_filter:{buy_allowed:false}};
assert.equal(candidate(report).actual,true);
assert.equal(candidate(report).reportExit,true);
assert.equal(candidate(report).armed,true);
assert.equal(candidate({...report,latest:{score:null}}).side,'SELL');
assert.equal(candidate({...stock,latest:{score:11}}).side,'BUY');
assert.equal(candidate({...stock,latest:{score:11.01}}),null);
assert.equal(candidate({...stock,latest:{score:89},position:{lots:1}}).side,'SELL');
assert.equal(candidate({...stock,latest:{score:88.99},position:{lots:1}}),null);
const planned={...report,next_action:{type:'NONE'},strategy_filter:{buy_allowed:false,trading_days_to_report:5,next_report_date:'2026-02-10',report_exit_date:'2026-02-09'}};
assert.equal(candidate(planned).reportExit,true);
assert.equal(candidate(planned).actual,false);
assert.equal(candidate(planned).reportDays,5);
assert.equal(candidate({...planned,latest:{score:null}}).side,'SELL');
assert.equal(candidate({...planned,strategy_filter:{...planned.strategy_filter,trading_days_to_report:6}}),null);
assert.equal(candidate({...planned,position:{lots:0}}),null);
const earlierSell=candidate({...planned,next_action:{type:'SELL',exit_reason:'score'}});
assert.equal(earlierSell.actual,true);
assert.equal(earlierSell.reportExit,false); // A score sell tomorrow must not be delayed to the report exit.
console.log('Overview strategy filters and report-exit checks passed.');
// Synthetic examples: current intraday score controls inclusion and direction.
const interim={score:50,price:100,ma200:99,session:'2026-10-16',as_of:'2026-10-16T11:10:00+02:00'};
const preview=(data,v=interim,key='standard')=>signalCandidate('TEST',data,{name:'Test'},{buy_score:1,sell_score:99},v,key);
assert.equal(preview({...stock,next_action:{type:'BUY',label:'Köp'}}),null);
assert.equal(preview({...stock,latest:{score:50}},{...interim,score:.5}).side,'BUY');
assert.equal(preview(stock,{...interim,score:.5}).actual,false);
assert.equal(preview({...stock,position:{lots:1,max_lots:1}},{...interim,score:99.5}).side,'SELL');
assert.equal(preview({...stock,strategy_filter:{buy_allowed:false}},{...interim,score:.5},'ma200').side,'BUY');
assert.equal(preview(stock,{...interim,score:.5,ma200:101},'ma200'),null);
assert.equal(preview({...stock,strategy_filter:{buy_allowed:true,trading_days_to_report:12,next_report_date:'2026-11-02'}},{...interim,score:.5},'report_avoidance'),null);
assert.equal(preview({...stock,strategy_filter:{buy_allowed:true,trading_days_to_report:13,next_report_date:'2026-11-03'}},{...interim,score:.5},'report_avoidance').side,'BUY');
assert.equal(preview({...stock,strategy_filter:{buy_allowed:true,basis_date:'2026-10-16',trading_days_to_report:12,next_report_date:'2026-11-03'}},{...interim,score:.5},'report_avoidance').side,'BUY');
assert.equal(preview({...planned,strategy_filter:{...planned.strategy_filter,next_report_date:'2026-10-23',report_exit_date:'2026-10-22',trading_days_to_report:6}},interim,'report_avoidance').reportDays,5);
