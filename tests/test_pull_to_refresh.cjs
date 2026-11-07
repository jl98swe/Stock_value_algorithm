// Synthetic touch gestures: no market data or network required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup() {
  const listeners = {}, style = new Map();
  let reloads = 0;
  const indicator = {setAttribute(){}, hidden:true};
  const root = {style:{setProperty:(k,v)=>style.set(k,v),removeProperty:k=>style.delete(k)}};
  const body = {append(){}};
  const target = {closest:()=>false, parentElement:body};
  const document = {documentElement:root,body,createElement:()=>indicator,querySelector:()=>null,
    addEventListener:(name,fn)=>listeners[name]=fn};
  const window = {scrollY:0,visualViewport:{scale:1}, matchMedia:()=>({matches:true}),
    getComputedStyle:()=>({overflowX:'visible',overflowY:'visible'}),
    location:{reload:()=>reloads++},requestAnimationFrame:fn=>fn(),addEventListener(){}};
  vm.runInNewContext(fs.readFileSync('docs/assets/pull-to-refresh.js','utf8'),{window,document});
  const touch=(x,y)=>({identifier:1,clientX:x,clientY:y});
  function send(type,x,y,extra={}) {
    let prevented=false;
    const point=touch(x,y);
    listeners[type]({target,touches:type==='touchend'?[]:[point],changedTouches:[point],cancelable:true,
      preventDefault:()=>prevented=true,...extra});
    return prevented;
  }
  return {window,document,target,indicator,style,send,touch,reloads:()=>reloads};
}
test('a deliberate downward pull reloads once, only on release',()=>{
  const ui=setup();ui.send('touchstart',20,40);
  assert.equal(ui.send('touchmove',20,145),true);
  assert.equal(ui.indicator.textContent,'Släpp för att uppdatera');
  assert.equal(ui.reloads(),0);
  ui.send('touchend',20,145);ui.send('touchend',20,145);
  assert.equal(ui.reloads(),1);
});
test('short pulls, reversing a pull and cancelling never refresh',()=>{
  for(const mode of ['short','reverse','cancel']) {
    const ui=setup();ui.send('touchstart',20,40);
    ui.send('touchmove',20,mode==='short'?80:145);
    if(mode==='reverse')ui.send('touchmove',20,45);
    if(mode==='cancel')ui.send('touchcancel',20,145);
    ui.send('touchend',20,mode==='reverse'?45:145);
    assert.equal(ui.reloads(),0,mode);assert.equal(ui.indicator.hidden,true);
  }
});
test('ordinary scrolling, horizontal gestures, pinch zoom and multitouch stay untouched',()=>{
  for(const mode of ['scrolled','horizontal','zoom','multitouch','uncancelable']) {
    const ui=setup();
    if(mode==='scrolled')ui.window.scrollY=200;
    if(mode==='zoom')ui.window.visualViewport.scale=2;
    ui.send('touchstart',20,40);
    const extra=mode==='multitouch'?{touches:[ui.touch(20,145),{identifier:2}]}:
      mode==='uncancelable'?{cancelable:false}:{};
    assert.equal(ui.send('touchmove',mode==='horizontal'?200:20,145,extra),false,mode);
    ui.send('touchend',20,145);assert.equal(ui.reloads(),0,mode);
  }
});
test('controls, charts, open popovers and nested scroll areas do not start refresh',()=>{
  for(const mode of ['control','popover','nested']) {
    const ui=setup();
    if(mode==='control')ui.target.closest=()=>true;
    if(mode==='popover')ui.document.querySelector=()=>({});
    if(mode==='nested') {
      Object.assign(ui.target,{scrollHeight:400,clientHeight:100});
      ui.window.getComputedStyle=()=>({overflowY:'auto',overflowX:'visible'});
    }
    ui.send('touchstart',20,40);assert.equal(ui.send('touchmove',20,145),false);
    ui.send('touchend',20,145);assert.equal(ui.reloads(),0,mode);
  }
});
test('all public pages include the shared gesture script',()=>{
  for(const name of fs.readdirSync('docs').filter(name=>name.endsWith('.html'))) {
    assert.match(fs.readFileSync(`docs/${name}`,'utf8'),/pull-to-refresh.js\?v=20261107/,name);
  }
});
