/* A deliberate one-finger pull from the top reloads every mobile page. */
(() => {
  'use strict';
  const touchDevice = window.matchMedia('(any-pointer: coarse)');
  const root = document.documentElement;
  const threshold = 90;
  let gesture = null;
  let refreshing = false;
  const indicator = document.createElement('div');
  indicator.className = 'pull-refresh-indicator';
  indicator.setAttribute('role', 'status');
  indicator.setAttribute('aria-live', 'polite');
  indicator.hidden = true;
  document.body.append(indicator);

  function reset() {
    gesture = null;
    root.style.removeProperty('--pull-refresh-distance');
    indicator.hidden = true;
    indicator.textContent = '';
  }

  function excluded(target) {
    if (document.querySelector('dialog[open], [popover]:popover-open')) return true;
    if (target.closest('input, textarea, select, button, a, [contenteditable], [role="dialog"], canvas, svg, .market-chart, .chart-panel')) return true;
    // Nested lists and tables keep their own scrolling, including at their edges.
    for (let node = target; node && node !== document.body && node !== root; node = node.parentElement) {
      const css = window.getComputedStyle(node);
      if ((/(auto|scroll)/.test(css.overflowY) && node.scrollHeight > node.clientHeight) ||
          (/(auto|scroll)/.test(css.overflowX) && node.scrollWidth > node.clientWidth)) return true;
    }
    return false;
  }

  document.addEventListener('touchstart', event => {
    if (refreshing) return;
    reset();
    if (!touchDevice.matches || event.touches.length !== 1 || window.scrollY > 0 ||
        (window.visualViewport?.scale ?? 1) !== 1 || excluded(event.target)) return;
    const touch = event.touches[0];
    gesture = {id: touch.identifier, x: touch.clientX, y: touch.clientY, distance: 0};
  }, {passive: true});

  document.addEventListener('touchmove', event => {
    if (!gesture || refreshing) return;
    const touch = event.touches[0];
    if (event.touches.length !== 1 || touch.identifier !== gesture.id || window.scrollY > 0) return reset();
    const dy = touch.clientY - gesture.y;
    const dx = Math.abs(touch.clientX - gesture.x);
    if (dy < 0 || (dx > 10 && dx > dy)) return reset();
    gesture.distance = dy;
    if (dy < 10) {
      root.style.removeProperty('--pull-refresh-distance');
      indicator.hidden = true;
      return;
    }
    if (!event.cancelable) return reset();
    event.preventDefault(); // Own this gesture; avoid a second native refresh.
    const distance = Math.min(80, dy * 0.55);
    root.style.setProperty('--pull-refresh-distance', `${distance}px`);
    indicator.hidden = false;
    const label = dy >= threshold ? 'Släpp för att uppdatera' : 'Dra nedåt för att uppdatera';
    if (indicator.textContent !== label) indicator.textContent = label;
  }, {passive: false});

  document.addEventListener('touchend', event => {
    if (!gesture || refreshing) return;
    const ended = Array.from(event.changedTouches).find(touch => touch.identifier === gesture.id);
    if (!ended) return;
    if (event.touches.length || gesture.distance < threshold || ended.clientY - gesture.y < threshold) return reset();
    refreshing = true;
    gesture = null;
    indicator.textContent = 'Uppdaterar…';
    // Give the indicator one frame before navigating to the current URL.
    window.requestAnimationFrame(() => window.location.reload());
  }, {passive: true});
  document.addEventListener('touchcancel', () => {if (!refreshing) reset();}, {passive: true});
  window.addEventListener('pageshow', () => {refreshing = false; reset();});
})();
