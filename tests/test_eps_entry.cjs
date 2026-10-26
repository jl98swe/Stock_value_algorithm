// Synthetic examples: no live requests or production values are used.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {validate, createClient} = require('../docs/assets/eps-entry.js');
const sample = () => ({ticker:'TEST.ST', report_period:'2026-Q3', period_end:'2026-09-30', published_at:'2026-10-23', metric:'eps_ttm', value:'2,78', currency:'SEK', source:'Exempel', notes:''});
test('Swedish decimal comma, zero and negative EPS work; invalid and future values fail', () => {
  assert.equal(validate(sample(), '2026-10-26').value, 2.78);
  for (const value of ['0','-1,25']) assert.equal(validate({...sample(), value}, '2026-10-26').value, Number(value.replace(',','.')));
  for (const value of ['', 'NaN', 'Infinity', '1,2,3', '0xFF']) assert.throws(() => validate({...sample(), value}, '2026-10-26'));
  assert.throws(() => validate({...sample(), period_end:'2026-02-30'}, '2026-10-26'));
  assert.throws(() => validate(sample(), '2026-10-22'));
});
test('dispatch sends one validated request to main; key is removed after disconnect', async () => {
  const calls = [];
  const client = createClient(async (url, options) => {calls.push({url, options}); return url.startsWith('https://raw.githubusercontent.com/') ? {ok:false,status:404} : {ok:true,status:204};});
  await client.connect('github_pat_SYNTHETIC');
  const input = {...validate(sample(),'2026-10-26'), request_id:'a'.repeat(32)};
  await client.dispatch(input);
  const call = calls.at(-1);
  assert.equal(call.url, 'https://api.github.com/repos/jl98swe/Stock_value_algorithm/actions/workflows/web_eps_submission.yml/dispatches');
  assert.equal(call.options.headers.Authorization, 'Bearer github_pat_SYNTHETIC');
  assert.equal(call.options.redirect, 'error');
  const body = JSON.parse(call.options.body);
  assert.equal(body.ref, 'main');
  assert.deepEqual(JSON.parse(body.inputs.submission), input);
  assert(!call.options.body.includes('github_pat_'));
  client.disconnect();
  await client.receipt(input.request_id);
  assert.equal(calls.at(-1).options.headers?.Authorization, undefined);
});
test('expired credentials are cleared; failure is never treated as success', async () => {
  const calls = [];
  const client = createClient(async (url, options) => {calls.push(options); return {ok:false,status:401};});
  await assert.rejects(client.connect('github_pat_SYNTHETIC'), /behörighet/);
  await assert.rejects(client.run('a'.repeat(32)), /behörighet/);
  assert.equal(calls[1].headers.Authorization, undefined);
});
test('run matching uses the unique request id, never another stock or submission', async () => {
  const client = createClient(async () => ({ok:true,status:200,json:async()=>({workflow_runs:[{id:1,display_title:'Webb-EPS wrong'},{id:2,display_title:'Webb-EPS right'}]})}));
  assert.equal((await client.run('right')).id,2);
  assert.equal(await client.run('missing'), null);
});

async function page({outcome = 'applied', failDispatch = false, published = true} = {}) {
  const vm = require('node:vm'), fs = require('node:fs');
  const html = fs.readFileSync('docs/review.html', 'utf8');
  const elements = new Map([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], {
    value:'', hidden:false, disabled:false, textContent:'', listeners:{},
    addEventListener(name, fn) {this.listeners[name] = fn;},
    dispatchEvent(event) {return this.listeners[event.type]?.(event);}, focus() {}
  }]));
  const events = {}, memory = new Map(), calls = [], emitted = [];
  const id = 'a'.repeat(32);
  const receipt = {request_id:id, ticker:'TEST.ST', status:outcome, reason: outcome==='applied' ? '' : 'Saknar tidigare kvartals-EPS', result_eps_ttm:outcome==='applied' ? 2.78 : null, currency:'SEK'};
  let sent = false;
  const fetch = async (url, options = {}) => {
    calls.push({url, options});
    if (url.endsWith('/dispatches')) {sent=true; if(failDispatch) throw Error('Network'); return {ok:true,status:204};}
    if (url.startsWith('https://raw.githubusercontent.com/')) return {ok:sent,status:sent?200:404,json:async()=>receipt};
    if (url.startsWith('./data/manual_requests/')) return {ok:published,status:published?200:404,json:async()=>receipt};
    if (url.includes('/runs?')) return {ok:true,status:200,json:async()=>({workflow_runs:[{display_title:`Webb-EPS ${id}`, status:'in_progress'}]})};
    return {ok:true,status:200,json:async()=>({})};
  };
  const window = {fetch,addEventListener:(event,fn)=>{events[event]=fn;}};
  const localStorage = {getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value),removeItem:key=>memory.delete(key)};
  vm.runInNewContext(fs.readFileSync('docs/assets/eps-entry.js','utf8'), {
    window, document:{getElementById:id=>elements.get(id),dispatchEvent:event=>emitted.push(event.type)},
    localStorage,fetch,Intl,Date,Number,console,crypto:{randomUUID:()=>id},
    CustomEvent:class {constructor(type){this.type=type;}},Event:class {constructor(type){this.type=type;}},
    setTimeout:()=>1,clearTimeout:()=>{}
  });
  events.DOMContentLoaded();
  const e = id=>elements.get(id);
  const trigger = (id, name='submit') => e(id).listeners[name]({preventDefault(){}});
  const input = sample();
  for (const [key, suffix] of Object.entries({ticker:'ticker',report_period:'period',period_end:'period-end',published_at:'published',metric:'metric',value:'value',currency:'currency',source:'source',notes:'note'})) e(`eps-${suffix}`).value=input[key];
  e('eps-access-key').value='github_pat_SYNTHETIC';
  await trigger('eps-key-form');
  return {e,trigger,calls,memory,emitted,events};
}
test('UI clears key field and reports success only after the receipt is published', async () => {
  const p = await page();
  assert.equal(p.e('eps-access-key').value,'');
  await p.trigger('eps-entry-form');
  assert.match(p.e('eps-save-status').textContent,/Sparat och publicerat/);
  assert(p.emitted.includes('eps-saved'));
  assert.equal(p.memory.size,0);
  assert.equal(p.e('eps-save').disabled,false);
  p.events.pagehide();
});
test('UI preserves uncertain submissions for retry without leaking credentials into storage', async () => {
  const p = await page({failDispatch:true});
  await p.trigger('eps-entry-form');
  assert.match(p.e('eps-save-status').textContent,/bekräfta mottagandet/);
  assert.equal(p.e('eps-save').disabled,true);
  const stored = [...p.memory.values()].join('');
  assert(stored.includes('request_id'));
  assert(!stored.includes('github_pat_'));
});
test('UI does not claim publication while Pages is still serving old files', async () => {
  const p = await page({published:false});
  await p.trigger('eps-entry-form');
  assert.match(p.e('eps-save-status').textContent,/Väntar på publicering/);
  assert.equal(p.e('eps-save').disabled,true);
  assert(!p.emitted.includes('eps-saved'));
});
test('UI distinguishes a stored quarterly value from an applied TTM', async () => {
  const p = await page({outcome:'pending_ttm'});
  await p.trigger('eps-entry-form');
  assert.match(p.e('eps-save-status').textContent,/inte uppdaterats/);
  assert.match(p.e('eps-save-status').textContent,/Saknar tidigare/);
  assert(!p.e('eps-save-status').textContent.includes('EPS TTM: 0'));
});
