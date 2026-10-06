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
console.log('Overview strategy filters and report-exit checks passed.');
