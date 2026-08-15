(() => {
  'use strict';

  let events = [];
  let scheduled = false;
  let changing = false;

  function eventType(event) {
    const classification = String(event.classification || '').toLocaleLowerCase('sv-SE');
    const explicitType = String(event.event_type || event.type || '').toLocaleLowerCase('sv-SE');
    const categories = Array.isArray(event.categories)
      ? event.categories.map((value) => String(value).toLocaleLowerCase('sv-SE'))
      : [];
    const tokens = [classification, explicitType, ...categories].join(' ');
    if (tokens.includes('report') || tokens.includes('earnings')) return 'report';
    if (tokens.includes('dividend') || tokens.includes('utdelning')) return 'dividend';
    return 'news';
  }

  function scheduleSync() {
    if (scheduled) return;
    scheduled = true;
    window.setTimeout(() => {
      scheduled = false;
      syncReviewEvents();
    }, 0);
  }

  function syncReviewEvents() {
    if (changing || !events.length) return;
    const stockSelect = document.getElementById('review-stock');
    const eventSelect = document.getElementById('review-event');
    const eventList = document.getElementById('review-event-list');
    if (!stockSelect || !eventSelect || !eventList) return;

    const ticker = stockSelect.value;
    const news = events.filter((event) => event.ticker === ticker && eventType(event) === 'news');
    const valid = new Set(news.map((event) => event.event_id));

    [...eventSelect.options].forEach((option) => {
      if (option.value && !valid.has(option.value)) option.remove();
    });
    eventList.querySelectorAll('.review-event-button').forEach((button) => {
      if (!valid.has(button.dataset.eventId)) button.remove();
    });

    const reviewForm = document.getElementById('review-form-title')?.closest('section.panel');
    const empty = document.getElementById('event-empty');
    const detail = document.getElementById('event-detail');

    if (!news.length) {
      eventSelect.innerHTML = '<option value="">Inga bolagsnyheter</option>';
      eventList.innerHTML = '<div class="empty-state">Inga bolagsnyheter för aktien.</div>';
      if (empty) {
        empty.textContent = 'Inga bolagsnyheter för aktien.';
        empty.hidden = false;
      }
      if (detail) detail.hidden = true;
      if (reviewForm) reviewForm.hidden = true;
      return;
    }

    if (reviewForm) reviewForm.hidden = false;
    const current = eventSelect.value;
    if (!valid.has(current)) {
      changing = true;
      eventSelect.value = news[0].event_id;
      eventSelect.dispatchEvent(new Event('change', { bubbles: true }));
      changing = false;
      scheduleSync();
    }
  }

  async function init() {
    try {
      const response = await fetch('./data/events.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`events.json gav HTTP ${response.status}`);
      const payload = await response.json();
      events = payload.events || [];

      const observer = new MutationObserver(scheduleSync);
      const select = document.getElementById('review-event');
      const list = document.getElementById('review-event-list');
      if (select) observer.observe(select, { childList: true, subtree: true });
      if (list) observer.observe(list, { childList: true, subtree: true });
      document.getElementById('review-stock')?.addEventListener('change', scheduleSync);
      scheduleSync();
    } catch (error) {
      console.warn('Kunde inte separera granskningshändelser:', error);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
