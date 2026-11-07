(() => {
  'use strict';
  // Keep popup presentation with its behavior, including pages with cached styles.
  const style = document.createElement('style');
  style.textContent = "/* Help content lives outside scrolling table containers. */\n.info-tip[data-help-ready]::after { content: none !important; display: none !important; }\n.help-popover {\n  position: fixed;\n  position-anchor: none;\n  position-area: none;\n  inset: auto;\n  box-sizing: border-box;\n  transform: none;\n  margin: 0;\n  width: min(300px, calc(100vw - 24px));\n  max-height: calc(100dvh - 24px);\n  overflow: auto;\n  padding: 12px;\n  border: 0;\n  border-radius: 8px;\n  background: #252423;\n  color: #fff;\n  box-shadow: 0 6px 24px #17212b33;\n  font-family: inherit;\n  font-size: 12px;\n  line-height: 1.5;\n}\n.info-tip[data-help-ready] { padding: 0; background: transparent; color: inherit; cursor: pointer; }\n.info-tip[data-help-ready]:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }\n\n";
  document.head.append(style);
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
      const viewport = window.visualViewport;
      const left = viewport?.offsetLeft || 0, top = viewport?.offsetTop || 0;
      const width = viewport?.width || innerWidth, height = viewport?.height || innerHeight;
      const edge = 12, gap = 8;
      if (rect.bottom <= top || rect.top >= top + height ||
          rect.right <= left || rect.left >= left + width) {
        popup.hidePopover();
        return;
      }
      // Measure only after opening, within the visible mobile viewport.
      popup.style.width = `${Math.min(300, width - edge * 2)}px`;
      const below = top + height - edge - rect.bottom - gap;
      const above = rect.top - gap - top - edge;
      popup.style.maxHeight = `${Math.max(0, height - edge * 2)}px`;
      const naturalHeight = popup.getBoundingClientRect().height;
      const useBelow = naturalHeight <= below || below >= above;
      popup.style.maxHeight = `${Math.max(0, useBelow ? below : above)}px`;
      const box = popup.getBoundingClientRect();
      const x = Math.max(left + edge, Math.min(rect.left, left + width - box.width - edge));
      const y = useBelow ? rect.bottom + gap : rect.top - gap - box.height;
      popup.style.left = `${x}px`;
      popup.style.top = `${Math.max(top + edge, y)}px`;
      popup.style.right = 'auto';
      popup.style.bottom = 'auto';
    };
    popup.addEventListener('beforetoggle', event => {
      if (event.newState === 'open') {
        popup.style.visibility = 'hidden';
        requestAnimationFrame(() => {
          if (popup.matches(':popover-open')) {
            position();
            popup.style.visibility = 'visible';
          }
        });
      }
    });
    popup.addEventListener('toggle', () => {
      const open = popup.matches(':popover-open');
      trigger.setAttribute('aria-expanded', String(open));
      if (open) {
        position();
        popup.style.visibility = 'visible';
      }
    });
    const reposition = () => { if (popup.matches(':popover-open')) position(); };
    window.addEventListener('resize', reposition);
    document.addEventListener('scroll', reposition, true);
    window.visualViewport?.addEventListener('resize', reposition);
    window.visualViewport?.addEventListener('scroll', reposition);
    active.set(trigger, () => {
      popup.remove();
      window.removeEventListener('resize', reposition);
      document.removeEventListener('scroll', reposition, true);
      window.visualViewport?.removeEventListener('resize', reposition);
      window.visualViewport?.removeEventListener('scroll', reposition);
    });
    });
  }
  window.initializeHelpPopovers = initialize;
  initialize();
})();
