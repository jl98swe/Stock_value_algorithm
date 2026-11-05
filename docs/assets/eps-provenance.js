(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function trigger(text, info, ticker, icon) {
    if (!info?.converted) return icon ? '' : esc(text);
    return `<button type="button" class="eps-fx-note${icon ? ' eps-fx-icon' : ''}" data-eps-fx="${esc(JSON.stringify(info))}" data-eps-ticker="${esc(ticker)}" data-eps-kind="${icon ? 'valuation' : 'eps'}" aria-label="${esc(icon ? 'Värderingen bygger på valutaomräknad EPS' : 'Valutaomräknat EPS: ' + text)}" aria-expanded="false" aria-controls="eps-fx-popover">${icon ? 'ⓘ' : esc(text)}</button>`;
  }
  window.epsProvenance = {
    value: (text, info, ticker) => trigger(text, info, ticker, false),
    icon: (info, ticker) => trigger('', info, ticker, true),
    publication: info => info?.publication_time_verified && info?.published_after_close
      ? `<button type="button" class="eps-fx-note eps-fx-icon" data-eps-fx="${esc(JSON.stringify({publication_note: info.publication_note}))}" aria-label="${esc(info.publication_note)}" aria-expanded="false" aria-controls="eps-fx-popover">ⓘ</button>` : ''
  };

  let popup, active, pinned = false, timer;
  const fmt = new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 6});
  function close() {
    clearTimeout(timer);
    if (!popup) return;
    if (popup.hidePopover && popup.matches(':popover-open')) popup.hidePopover();
    popup.hidden = true;
    active?.setAttribute('aria-expanded', 'false');
    active = null;
    pinned = false;
  }
  function position() {
    if (!active || !popup) return;
    const rect = active.getBoundingClientRect();
    popup.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - popup.offsetWidth - 12))}px`;
    popup.style.top = `${Math.max(12, Math.min(rect.bottom + 6, innerHeight - popup.offsetHeight - 12))}px`;
  }
  function show(button) {
    clearTimeout(timer);
    if (button === active) return;
    close();
    let info;
    try { info = JSON.parse(button.dataset.epsFx); } catch { return; }
    if (!popup) {
      popup = document.createElement('div');
      popup.id = 'eps-fx-popover';
      popup.className = 'eps-fx-popover';
      popup.setAttribute('role', 'note');
      if (popup.showPopover) popup.setAttribute('popover', 'manual');
      popup.addEventListener('pointerenter', () => clearTimeout(timer));
      popup.addEventListener('pointerleave', () => { if (!pinned) timer = setTimeout(close, 120); });
      document.body.append(popup);
    }
    popup.replaceChildren();
    const title = document.createElement('strong');
    title.textContent = info.publication_note ? 'Rapportinformation' : 'Valutaomräknat EPS';
    const text = document.createElement('p');
    text.textContent = `${button.dataset.epsKind === 'valuation' ? 'Värderingen bygger på valutaomräknad EPS. ' : ''}Beräknat från ${fmt.format(info.original_eps_ttm)} ${info.original_currency} till ${info.target_currency} med valutakurs ${fmt.format(info.rate)} från ${info.rate_date}.`;
    const link = document.createElement('a');
    link.href = `./review.html?ticker=${encodeURIComponent(button.dataset.epsTicker)}#eps-form-title`;
    link.textContent = 'Komplettera med verifierat TradingView-värde';
    if (info.publication_note) {
      text.textContent = info.publication_note;
      popup.append(text);
    } else popup.append(title, text, link);
    active = button;
    active.setAttribute('aria-expanded', 'true');
    popup.hidden = false;
    if (popup.showPopover) popup.showPopover();
    position();
  }
  const buttonFor = event => event.target.closest?.('button[data-eps-fx]');
  document.addEventListener('pointerover', event => { const b = buttonFor(event); if (b && !pinned) show(b); });
  document.addEventListener('pointerout', event => {
    if (buttonFor(event) && !pinned && !active?.contains(event.relatedTarget)) timer = setTimeout(close, 120);
  });
  document.addEventListener('focusin', event => { const b = buttonFor(event); if (b && !pinned) show(b); });
  document.addEventListener('focusout', event => {
    if (!pinned && !popup?.contains(event.relatedTarget)) timer = setTimeout(close, 120);
  });
  document.addEventListener('click', event => {
    const b = buttonFor(event);
    if (b) {
      if (active === b && pinned) close();
      else { show(b); pinned = true; }
    } else if (!popup?.contains(event.target)) close();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  document.addEventListener('scroll', position, true);
  window.addEventListener('resize', position);
  new MutationObserver(() => { if (active && !active.isConnected) close(); })
    .observe(document.documentElement, {childList: true, subtree: true});
})();
