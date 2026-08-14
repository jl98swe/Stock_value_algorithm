(() => {
  'use strict';

  const REPO = 'https://github.com/jl98swe/Stock_value_algorithm';
  const $ = (id) => document.getElementById(id);
  const state = { stocks: [], events: [], selectedTicker: '', selectedEventId: '' };
  const dateFmt = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'medium', timeStyle: 'short' });

  async function loadJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path} gav HTTP ${response.status}`);
    return response.json();
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[c]));
  }

  function currentEvent() {
    return state.events.find((event) => event.event_id === state.selectedEventId) || null;
  }

  function eventsForTicker() {
    return state.events.filter((event) => event.ticker === state.selectedTicker);
  }

  function formatTime(value) {
    const d = new Date(value);
    return Number.isNaN(d.valueOf()) ? value || '–' : dateFmt.format(d);
  }

  function setQuery() {
    const url = new URL(location.href);
    if (state.selectedTicker) url.searchParams.set('ticker', state.selectedTicker);
    if (state.selectedEventId) url.searchParams.set('event', state.selectedEventId);
    history.replaceState({}, '', url);
  }

  function populateStocks() {
    $('review-stock').innerHTML = state.stocks.map((stock) => `<option value="${esc(stock.ticker)}">${esc(stock.ticker)} · ${esc(stock.name)}</option>`).join('');
    $('review-stock').value = state.selectedTicker;
  }

  function populateEvents() {
    const events = eventsForTicker();
    if (!events.some((event) => event.event_id === state.selectedEventId)) {
      state.selectedEventId = events[0]?.event_id || '';
    }
    $('review-event').innerHTML = events.length
      ? events.map((event) => `<option value="${esc(event.event_id)}">${esc(event.title)}</option>`).join('')
      : '<option value="">Inga nyheter</option>';
    $('review-event').value = state.selectedEventId;

    $('review-event-list').innerHTML = events.map((event) => `
      <button type="button" class="review-event-button ${event.event_id === state.selectedEventId ? 'active' : ''}" data-event-id="${esc(event.event_id)}">
        <strong>${esc(event.title)}</strong>
        <span>${esc(formatTime(event.published_at))} · ${esc(event.review_status === 'reviewed' ? 'Granskad' : 'Ogranskad')}</span>
      </button>`).join('') || '<div class="empty-state">Inga bolagsnyheter för aktien.</div>';

    document.querySelectorAll('.review-event-button').forEach((button) => {
      button.addEventListener('click', () => {
        state.selectedEventId = button.dataset.eventId;
        $('review-event').value = state.selectedEventId;
        populateEvents();
        renderEvent();
        setQuery();
      });
    });
  }

  function renderEvent() {
    const event = currentEvent();
    $('eps-ticker').value = state.selectedTicker;
    $('cal-ticker').value = state.selectedTicker;
    $('trade-ticker').value = state.selectedTicker;

    if (!event) {
      $('event-empty').hidden = false;
      $('event-detail').hidden = true;
      updateCommands();
      return;
    }

    $('event-empty').hidden = true;
    $('event-detail').hidden = false;
    $('event-source').textContent = `${event.source || 'Okänd källa'}${event.is_regulatory ? ' · regulatorisk' : ''}`;
    $('event-heading').textContent = event.title || 'Bolagsnyhet';
    $('event-time').textContent = formatTime(event.published_at);
    $('event-summary').textContent = event.summary || 'Ingen sammanfattning sparad.';
    $('event-id').textContent = event.event_id;
    $('event-status').textContent = event.review_status === 'reviewed' ? 'Granskad' : 'Ogranskad';
    $('event-current-classification').textContent = event.classification || 'unreviewed';
    $('event-locking').textContent = event.locking ? 'Ja' : 'Nej';
    $('event-original').href = event.link || '#';

    if (event.classification && event.classification !== 'unreviewed') {
      $('classification').value = event.classification;
    }
    if (event.lock_action && [...$('lock-action').options].some((o) => o.value === event.lock_action)) {
      $('lock-action').value = event.lock_action;
    }
    $('review-note').value = event.review_note || '';
    updateCommands();
  }

  function quoted(value) {
    return `"${String(value ?? '').replaceAll('"', '\\"')}"`;
  }

  function updateCommands() {
    const event = currentEvent();
    $('review-command').textContent = event
      ? `event_id=${event.event_id} classification=${$('classification').value} lock_action=${$('lock-action').value} note=${quoted($('review-note').value)}`
      : 'Välj en bolagsnyhet först.';

    const epsParts = [
      `ticker=${$('eps-ticker').value || state.selectedTicker}`,
      `period=${$('eps-period').value}`,
      `period_end=${$('eps-period-end').value}`,
      `published_at=${quoted($('eps-published').value)}`,
      `effective_date=${$('eps-effective').value}`,
      `eps_ttm=${$('eps-value').value}`,
      `source=${quoted($('eps-source').value)}`,
      `note=${quoted($('eps-note').value)}`
    ];
    $('eps-command').textContent = epsParts.join(' ');

    const calParts = [
      `ticker=${$('cal-ticker').value || state.selectedTicker}`,
      `report_period=${$('cal-period').value}`,
      `scheduled_at=${quoted($('cal-scheduled').value)}`,
      `lock_from_date=${$('cal-lock').value}`,
      `source=${quoted($('cal-source').value)}`,
      `url=${quoted($('cal-url').value)}`
    ];
    $('calendar-command').textContent = calParts.join(' ');

    const tradeParts = [
      `ticker=${$('trade-ticker').value || state.selectedTicker}`,
      `date=${$('trade-date').value}`,
      `side=${$('trade-side').value}`,
      `quantity=${$('trade-quantity').value}`,
      `price=${$('trade-price').value}`,
      `note=${quoted($('trade-note').value)}`
    ];
    $('trade-command').textContent = tradeParts.join(' ');
  }

  async function copyFrom(codeId, statusId) {
    const text = $(codeId).textContent;
    try {
      await navigator.clipboard.writeText(text);
      if (statusId && $(statusId)) {
        $(statusId).textContent = 'Kopierat';
        setTimeout(() => { $(statusId).textContent = ''; }, 1500);
      }
    } catch {
      const range = document.createRange();
      range.selectNodeContents($(codeId));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  function bindCopy(buttonId, codeId, statusId = null) {
    $(buttonId)?.addEventListener('click', () => copyFrom(codeId, statusId));
  }

  function bindInputs() {
    $('review-stock').addEventListener('change', (e) => {
      state.selectedTicker = e.target.value;
      state.selectedEventId = eventsForTicker()[0]?.event_id || '';
      populateEvents();
      renderEvent();
      setQuery();
    });
    $('review-event').addEventListener('change', (e) => {
      state.selectedEventId = e.target.value;
      populateEvents();
      renderEvent();
      setQuery();
    });

    document.querySelectorAll('input, select, textarea').forEach((control) => {
      if (control.id !== 'review-stock' && control.id !== 'review-event') {
        control.addEventListener('input', updateCommands);
        control.addEventListener('change', updateCommands);
      }
    });

    bindCopy('copy-review-command', 'review-command', 'review-copy-status');
    bindCopy('copy-eps-command', 'eps-command', 'eps-copy-status');
    bindCopy('copy-calendar-command', 'calendar-command');
    bindCopy('copy-trade-command', 'trade-command');
  }

  function setWorkflowLinks() {
    $('repository-link').href = REPO;
    ['review-action-link','eps-action-link','calendar-action-link','trade-action-link'].forEach((id) => { $(id).href = `${REPO}/actions`; });
  }

  async function init() {
    try {
      const [stocksPayload, eventsPayload] = await Promise.all([
        loadJson('./data/stocks.json'),
        loadJson('./data/events.json')
      ]);
      state.stocks = stocksPayload.stocks || [];
      state.events = eventsPayload.events || [];
      if (!state.stocks.length) throw new Error('Ingen aktielista hittades.');

      const params = new URLSearchParams(location.search);
      const wantedTicker = params.get('ticker');
      state.selectedTicker = state.stocks.some((s) => s.ticker === wantedTicker) ? wantedTicker : state.stocks[0].ticker;
      const candidates = state.events.filter((e) => e.ticker === state.selectedTicker);
      const wantedEvent = params.get('event');
      state.selectedEventId = candidates.some((e) => e.event_id === wantedEvent) ? wantedEvent : (candidates[0]?.event_id || '');

      setWorkflowLinks();
      populateStocks();
      populateEvents();
      bindInputs();
      renderEvent();
      setQuery();
    } catch (error) {
      console.error(error);
      document.querySelector('.review-page').insertAdjacentHTML('afterbegin', `<div class="lock-alert"><div class="lock-icon">!</div><div><strong>Kunde inte ladda granskningsdata</strong><p>${esc(error.message)}</p></div></div>`);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
