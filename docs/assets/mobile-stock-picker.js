(() => {
  'use strict';

  function init() {
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.getElementById('stock-picker-toggle');
    const label = document.getElementById('stock-picker-label');
    const search = document.getElementById('stock-search');
    const list = document.getElementById('stock-list');
    if (!sidebar || !toggle || !label || !search || !list) return;
    const mobile = window.matchMedia('(max-width: 780px)');

    // Select before dismissing the keyboard can move the result under the finger.
    // Leave scrolling and multi-touch gestures to the browser.
    let touchSelection = null;
    list.addEventListener('touchstart', (event) => {
      touchSelection = null;
      if (!mobile.matches || event.touches.length !== 1) return;
      const button = event.target.closest('.stock-button');
      if (!button || !list.contains(button)) return;
      const touch = event.touches[0];
      touchSelection = { button, id: touch.identifier, x: touch.clientX, y: touch.clientY };
    }, { passive: true });
    list.addEventListener('touchmove', (event) => {
      if (!touchSelection) return;
      const touch = Array.from(event.touches).find(item => item.identifier === touchSelection.id);
      if (event.touches.length !== 1 || !touch || Math.hypot(touch.clientX - touchSelection.x, touch.clientY - touchSelection.y) > 10) touchSelection = null;
    }, { passive: true });
    list.addEventListener('touchcancel', () => { touchSelection = null; }, { passive: true });
    list.addEventListener('touchend', (event) => {
      const selection = touchSelection;
      touchSelection = null;
      if (!mobile.matches || !selection || !event.cancelable || !selection.button.isConnected) return;
      const touch = Array.from(event.changedTouches).find(item => item.identifier === selection.id);
      if (!touch || Math.hypot(touch.clientX - selection.x, touch.clientY - selection.y) > 10) return;
      event.preventDefault();
      selection.button.click();
      search.blur();
    }, { passive: false });

    function setOpen(open, restoreFocus = false) {
      sidebar.classList.toggle('stock-picker-open', mobile.matches && open);
      toggle.setAttribute('aria-expanded', String(mobile.matches && open));
      if (restoreFocus && mobile.matches) toggle.focus({ preventScroll: true });
    }

    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      setOpen(open);
      if (open) search.focus({ preventScroll: true });
      else search.blur();
    });
    search.addEventListener('focus', () => setOpen(true));
    search.addEventListener('input', () => setOpen(true));
    sidebar.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && mobile.matches) {
        event.preventDefault();
        setOpen(false, true);
      }
    });
    document.addEventListener('click', (event) => {
      if (mobile.matches && !sidebar.contains(event.target)) {
        search.blur();
        setOpen(false);
      }
    });
    document.addEventListener('stock-selected', (event) => {
      label.textContent = `Byt aktie · ${event.detail.name}`;
      if (!mobile.matches) return;
      // Collapse only once the requested stock has actually loaded.
      const restoreFocus = sidebar.contains(document.activeElement);
      search.value = '';
      search.dispatchEvent(new Event('input', { bubbles: true }));
      search.blur();
      setOpen(false, restoreFocus);
    });
    mobile.addEventListener('change', () => setOpen(false));
    setOpen(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();

