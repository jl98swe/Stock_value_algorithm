// Synthetic examples exercise dynamic rows, touch clicks, hover and keyboard.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('docs/assets/eps-provenance.js','utf8');
const info = {converted:true,original_eps_ttm:1.3,original_currency:'EUR',target_currency:'SEK',rate:10,rate_date:'2026-10-30'};

function setup(width=1200) {
  const events={}, roots=[];
  class Element {
    constructor(){this.attrs={};this.children=[];this.listeners={};this.style={};this.hidden=true;this.offsetWidth=296;this.offsetHeight=150;this.isConnected=true;}
    setAttribute(k,v){this.attrs[k]=v;}
    addEventListener(k,v){this.listeners[k]=v;}
    append(...items){this.children.push(...items);}
    replaceChildren(){this.children=[];}
    closest(){return this.dataset?.epsFx ? this : null;}
    contains(el){return this===el||this.children.includes(el);}
    getBoundingClientRect(){return {left:width-70,bottom:700};}
    showPopover(){this.open=true;}
    hidePopover(){this.open=false;}
    matches(){return !!this.open;}
  }
  const document={body:{append:el=>roots.push(el)},documentElement:{},createElement:()=>new Element(),addEventListener:(k,v)=>events[k]=v};
  const window={addEventListener(){}};
  vm.runInNewContext(source,{window,document,innerWidth:width,innerHeight:760,Intl,JSON,encodeURIComponent,
    clearTimeout,setTimeout,MutationObserver:class{observe(){}}});
  const button=()=>Object.assign(new Element(),{dataset:{epsFx:JSON.stringify(info),epsTicker:'EXAMPLE.ST',epsKind:'eps'}});
  return {api:window.epsProvenance,events,roots,button};
}

test('only converted values are marked; strings and metadata are escaped',()=>{
  const {api}=setup();
  assert.equal(api.value('4,0000 SEK',null,'EXAMPLE.ST'),'4,0000 SEK');
  assert.equal(api.icon(null,'EXAMPLE.ST'),'');
  const html=api.value('<img onerror=x>',info,'EXAMPLE.ST');
  assert.match(html,/class="eps-fx-note"/);
  assert.match(html,/aria-expanded="false"/);
  assert.doesNotMatch(html,/<img/);
  assert.match(html,/&lt;img/);
  assert.match(api.icon(info,'EXAMPLE.ST'),/ⓘ/);
});

test('hover opens an interactive note, click pins it, second click or Escape closes',()=>{
  const {events,roots,button}=setup();const b=button();
  events.pointerover({target:b});
  const popup=roots[0];
  assert.equal(b.attrs['aria-expanded'],'true');
  assert.match(popup.children[1].textContent,/EUR till SEK/);
  assert.match(popup.children[1].textContent,/2026-10-30/);
  assert.equal(popup.children[2].href,'./review.html?ticker=EXAMPLE.ST#eps-form-title');
  events.click({target:b});
  events.pointerout({target:b,relatedTarget:null});
  assert.equal(popup.hidden,false);
  events.click({target:b});
  assert.equal(popup.hidden,true);
  events.focusin({target:b});
  assert.equal(popup.hidden,false);
  events.keydown({key:'Escape'});
  assert.equal(popup.hidden,true);
  assert.equal(b.attrs['aria-expanded'],'false');
});

test('mobile click stays within the viewport and outside click dismisses',()=>{
  const {events,roots,button}=setup(320);const b=button();
  events.click({target:b});
  assert.equal(roots[0].style.left,'12px');
  assert.equal(roots[0].style.top,'598px');
  events.click({target:{closest:()=>null}});
  assert.equal(roots[0].hidden,true);
});

test('report page marks each side independently, including converted zero',async()=>{
  const {api}=setup();
  const nodes=new Map();let init;
  const element=id=>{if(!nodes.has(id))nodes.set(id,{value:'',hidden:false,attrs:{},innerHTML:'',textContent:'',addEventListener(){},setAttribute(k,v){this.attrs[k]=v}});return nodes.get(id)};
  vm.runInNewContext(fs.readFileSync('docs/assets/reports.js','utf8'),{Intl,Date,console,window:{epsProvenance:api},
    document:{getElementById:element,addEventListener:(key,fn)=>{if(key==='DOMContentLoaded')init=fn}},setInterval(){},
    fetch:async()=>({ok:true,json:async()=>({as_of_date:'2026-11-02',trading_sessions:[],upcoming:[],recent:[
      {ticker:'EXAMPLE.ST',report_date:'2026-11-02',eps_ttm_before:4,eps_ttm_after:0,eps_ttm_before_currency:'SEK',eps_ttm_after_currency:'SEK',eps_ttm_after_conversion:info}
    ]})})});
  await init();
  const html=element('recent-body').innerHTML;
  assert.equal((html.match(/data-eps-fx=/g)||[]).length,1);
  assert.match(html,/4,0000 SEK<\/span>/);
  assert.match(html,/0,0000 SEK<\/button>/);
});

test('verified after-close publication has a neutral, keyboard and mobile accessible note',()=>{
  const {api,events,roots,button}=setup(320);
  const note='Rapporten publicerades efter börsstängning och används därför från nästa handelsdag.';
  assert.equal(api.publication({published_after_close:true,publication_note:note}),'');
  assert.equal(api.publication({publication_time_verified:true,published_after_close:false}),'');
  const html=api.publication({publication_time_verified:true,published_after_close:true,publication_note:note});
  assert.match(html,/ⓘ/); assert.match(html,/aria-expanded="false"/);
  assert.doesNotMatch(html,/warning|alert/);
  const b=button(); b.dataset.epsFx=JSON.stringify({publication_note:note});
  events.focusin({target:b}); assert.equal(roots[0].children[0].textContent,note);
  events.click({target:b}); assert.equal(roots[0].hidden,false);
  events.click({target:{closest:()=>null}}); assert.equal(roots[0].hidden,true);
});
