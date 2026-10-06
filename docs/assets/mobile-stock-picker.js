(() => {
  'use strict';

  function init() {
    const sidebar = document.querySelector('.sidebar');
    const toggle = document.getElementById('stock-picker-toggle');
    const label = document.getElementById('stock-picker-label');
    const search = document.getElementById('stock-search');
    if (!sidebar || !toggle || !label || !search) return;
    const mobile = window.matchMedia('(max-width: 780px)');

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
