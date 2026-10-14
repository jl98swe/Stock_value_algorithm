const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {fullHistoryRows}=require('../docs/assets/method.js');
const first=['standard','standard_stop_loss_10','standard_two_positions'];
test('comparison starts with Standard, stop loss and two positions using em dashes',()=>{
 const rows=fullHistoryRows({candles:[]},{},null);
 assert.deepEqual(rows.slice(0,3).map(r=>r.id),first);
 assert.deepEqual(rows.slice(0,3).map(r=>r.name),['Standard','Standard — stop loss 10 %','Standard — två positioner']);
});
test('all existing strategy selectors use the same order and names',()=>{
 for(const page of ['index','method','positions','signals','alerts']){
  const html=fs.readFileSync(path.join(__dirname,'../docs',page+'.html'),'utf8');
  for(const match of html.matchAll(/<select\b[^>]*>([\s\S]*?)<\/select>/g)){
   const options=[...match[1].matchAll(/<option[^>]*value="([^"]+)"[^>]*>([^<]*)<\/option>/g)];
   if(!options.some(o=>o[1]==='standard'))continue;
   const keys=options.map(o=>o[1]).filter(k=>k!=='all');
   assert.deepEqual(keys.slice(0,page==='alerts'?2:3),first.slice(0,page==='alerts'?2:3),page);
   for(const o of options){if(o[1]==='standard_stop_loss_10')assert.equal(o[2],'Standard — stop loss 10 %');if(o[1]==='standard_two_positions')assert.equal(o[2],'Standard — två positioner');}
  }
 }
});
