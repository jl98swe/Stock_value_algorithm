(() => {
  'use strict';
  let nextId = 0;
  const active = new Map();
  function initialize() {
    for (const [trigger, cleanup] of active) {
      if (!trigger.isConnected) { cleanup(); active.delete(trigger); }
    }
    document.querySelectorAll('.info-tip[data-tooltip]:not([data-help-ready])').forEach((original) => {
    const trigger = original.tagName === 'BUTTON' ? original : document.createElement('button');
    if (trigger !== original) {
      for (const attribute of original.attributes) trigger.setAttribute(attribute.name, attribute.value);
      trigger.textContent = original.textContent;
      original.replaceWith(trigger);
    }
    trigger.type = 'button';
    trigger.removeAttribute('role');
    trigger.dataset.helpReady = '';
    trigger.setAttribute('aria-label', trigger.getAttribute('aria-label') || 'Visa förklaring');
    trigger.setAttribute('aria-expanded', 'false');
    const popup = document.createElement('div');
    popup.id = `help-popover-${nextId++}`;
    popup.className = 'help-popover';
    popup.setAttribute('popover', 'auto');
    popup.textContent = trigger.dataset.tooltip;
    document.body.append(popup);
    trigger.setAttribute('popovertarget', popup.id);
    trigger.setAttribute('aria-controls', popup.id);
    const position = () => {
      const rect = trigger.getBoundingClientRect();
      const width = popup.offsetWidth, height = popup.offsetHeight;
      popup.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - width - 12))}px`;
      popup.style.top = `${Math.max(12, Math.min(rect.bottom + 8, innerHeight - height - 12))}px`;
    };
    popup.addEventListener('beforetoggle', event => {
      if (event.newState === 'open') requestAnimationFrame(position);
    });
    popup.addEventListener('toggle', () => {
      trigger.setAttribute('aria-expanded', String(popup.matches(':popover-open')));
    });
    const reposition = () => { if (popup.matches(':popover-open')) position(); };
    window.addEventListener('resize', reposition);
    document.addEventListener('scroll', reposition, true);
    active.set(trigger, () => {
      popup.remove();
      window.removeEventListener('resize', reposition);
      document.removeEventListener('scroll', reposition, true);
    });
    });
  }
  window.initializeHelpPopovers = initialize;
  initialize();
})();
