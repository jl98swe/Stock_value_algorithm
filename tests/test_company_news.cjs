const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {render} = require('../docs/assets/company-news.js');
// Synthetic fixtures; newest first as supplied by the homepage renderer.
const events = [1,2,3].map(id=>({event_id:String(id),title:`Rubrik ${id}`,summary:`Innehåll ${id}`,published_at:'2026-10-09',source:'Testkälla'}));
function ui() {
  return {target:{querySelectorAll:()=>[],innerHTML:''},toggle:{setAttribute(key,value){this[key]=value;}}};
}
test('initial list shows only one title with native collapsed details', () => {
  const {target,toggle}=ui();render(target,toggle,events,false,'TEST.ST',String);
  assert.equal((target.innerHTML.match(/<article /g)||[]).length,1);
  assert(target.innerHTML.includes('<h3>Rubrik 1</h3>'));
  assert(!target.innerHTML.includes('Rubrik 2'));
  assert(target.innerHTML.indexOf('<details') < target.innerHTML.indexOf('Innehåll 1'));
  assert(!/<details[^>]* open/.test(target.innerHTML));
  assert.equal(toggle.textContent,'Visa alla nyheter');assert.equal(toggle.hidden,false);
  assert.equal(toggle['aria-expanded'],'false');
});
test('show all expands all titles; collapse returns to one; zero/one hides list toggle', () => {
  const {target,toggle}=ui();render(target,toggle,events,true,'TEST.ST',String);
  assert.equal((target.innerHTML.match(/<article /g)||[]).length,3);
  assert.equal(toggle.textContent,'Visa färre nyheter');assert.equal(toggle['aria-expanded'],'true');
  render(target,toggle,events,false,'TEST.ST',String);
  assert.equal((target.innerHTML.match(/<article /g)||[]).length,1);
  render(target,toggle,events.slice(0,1),false,'TEST.ST',String);assert.equal(toggle.hidden,true);
  render(target,toggle,[],false,'TEST.ST',String);assert.equal(toggle.hidden,true);
  assert(target.innerHTML.includes('Inga bolagsnyheter'));
});
test('open detail is preserved on re-render and does not leak to another stock', () => {
  const {target,toggle}=ui();target.querySelectorAll=()=>[{dataset:{newsKey:'TEST.ST|1'}}];
  render(target,toggle,events,true,'TEST.ST',String);
  assert.equal((target.innerHTML.match(/ open>/g)||[]).length,1);
  render(target,toggle,events,true,'OTHER.ST',String);
  assert(!/<details[^>]* open/.test(target.innerHTML));
});
test('titles and details are escaped and chart redraws cannot overwrite the list', () => {
  const {target,toggle}=ui();render(target,toggle,[{event_id:'a&b',title:'<script>',summary:'<b>text</b>'}],false,'TEST.ST',String);
  assert(target.innerHTML.includes('&lt;script&gt;'));assert(target.innerHTML.includes('&lt;b&gt;text&lt;/b&gt;'));
  const enhancement=fs.readFileSync(path.join(__dirname,'../docs/assets/chart-enhancements.js'),'utf8');
  assert(!enhancement.includes("getElementById('news-list')"));assert(!enhancement.includes('expandedNews'));
  const app=fs.readFileSync(path.join(__dirname,'../docs/assets/app.js'),'utf8');
  assert(app.includes("String(b.published_at || '').localeCompare(String(a.published_at || ''))"));
});
