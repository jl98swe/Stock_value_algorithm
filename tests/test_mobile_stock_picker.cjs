const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'docs/assets/mobile-stock-picker.js'), 'utf8');

function setup(isMobile = true) {
  const document = new EventTarget();
  document.readyState = 'complete';
  class Element extends EventTarget {
    constructor() {
      super(); this.attributes = {}; this.classes = new Set(); this.value = '';
      this.classList = { toggle: (name, add) => add ? this.classes.add(name) : this.classes.delete(name) };
    }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name]; }
    focus() { document.activeElement = this; this.dispatchEvent(new Event('focus')); }
    blur() { if (document.activeElement === this) document.activeElement = null; }
  }
  const sidebar = new Element(), toggle = new Element(), label = new Element(), search = new Element(), option = new Element();
  const elements = { 'stock-picker-toggle': toggle, 'stock-picker-label': label, 'stock-search': search };
  sidebar.contains = (node) => [sidebar, toggle, label, search, option].includes(node);
  document.querySelector = () => sidebar;
  document.getElementById = (id) => elements[id];
  const media = new EventTarget(); media.matches = isMobile;
  vm.runInNewContext(script, { document, window: { matchMedia: () => media }, Event });
  const selected = (name) => {
    const event = new Event('stock-selected'); event.detail = { ticker: 'EMBRAC-B.ST', name };
    document.dispatchEvent(event);
  };
  return { document, sidebar, toggle, label, search, option, media, selected };
}

test('mobile starts collapsed, opens on search, closes after successful selection and clears the filter', () => {
  const ui = setup();
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'false');
  assert(!ui.sidebar.classes.has('stock-picker-open'));
  ui.search.focus(); ui.search.value = 'embracer';
  assert(ui.sidebar.classes.has('stock-picker-open'));
  // The picker stays available until the async selection emits success.
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'true');
  let filtered = null;
  ui.search.addEventListener('input', () => { filtered = ui.search.value; });
  ui.selected('Embracer');
  assert.equal(ui.label.textContent, 'Byt aktie · Embracer');
  assert.equal(filtered, '');
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(ui.document.activeElement, ui.toggle);
  ui.toggle.dispatchEvent(new Event('click'));
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'true');
  assert.equal(ui.document.activeElement, ui.search);
});

test('Escape and outside clicks dismiss the mobile picker', () => {
  const ui = setup(); ui.search.focus();
  const escape = new Event('keydown', { cancelable: true }); escape.key = 'Escape';
  ui.sidebar.dispatchEvent(escape);
  assert(escape.defaultPrevented);
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(ui.document.activeElement, ui.toggle);
  ui.search.focus(); ui.document.dispatchEvent(new Event('click'));
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'false');
});

test('desktop search remains unchanged and resizing resets mobile expansion', () => {
  const ui = setup(false); ui.search.value = 'embracer'; ui.search.focus(); ui.selected('Embracer');
  assert.equal(ui.search.value, 'embracer');
  assert(!ui.sidebar.classes.has('stock-picker-open'));
  ui.media.matches = true; ui.media.dispatchEvent(new Event('change'));
  assert.equal(ui.toggle.getAttribute('aria-expanded'), 'false');
  ui.search.focus(); assert(ui.sidebar.classes.has('stock-picker-open'));
  ui.media.matches = false; ui.media.dispatchEvent(new Event('change'));
  assert(!ui.sidebar.classes.has('stock-picker-open'));
});

test('mobile CSS caps the list height, keeps touch targets usable and does not change desktop list display', () => {
  const css = fs.readFileSync(path.join(root, 'docs/assets/style.css'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8');
  const app = fs.readFileSync(path.join(root, 'docs/assets/app.js'), 'utf8');
  assert(css.indexOf('.sidebar:not(.stock-picker-open) .stock-list') > css.indexOf('@media (max-width: 780px)'));
  assert(css.includes('max-height: min(44vh, 320px)'));
  assert(css.includes('min-height: 44px !important'));
  assert(html.includes('aria-controls="stock-list"'));
  assert(html.includes('mobile-stock-picker.js?v=20261006-1'));
  assert(app.includes("new CustomEvent('stock-selected'"));
});
