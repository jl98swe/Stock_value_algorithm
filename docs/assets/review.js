(() => {
  'use strict';

  const REPO = 'https://github.com/jl98swe/Stock_value_algorithm';
  const $ = (id) => document.getElementById(id);
  const state = {
    stocks: [], events: [], earnings: [], quarterly: [], manualReports: [], dashboardFiles: {},
    activeStock: null, selectedTicker: '', selectedEventId: ''
  };
  const dateFmt = new Intl.DateTimeFormat('sv-SE', { dateStyle: 'medium', timeStyle: 'short' });
  const numFmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 6 });

  async function loadJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path} gav HTTP ${response.status}`);
    return response.json();
  }

  async function loadJsonOptional(path) {
    try {
      return await loadJson(path);
    } catch (error) {
      console.warn(`Valfri granskningsdata kunde inte laddas från ${path}:`, error);
      return null;
    }
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>'\"]/g, (c) => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '\"':'&quot;' }[c]));
  }

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

  function isNewsEvent(event) {
    return eventType(event) === 'news';
  }

  function currentEvent() {
    return state.events.find((event) => event.event_id === state.selectedEventId) || null;
  }

  function currentEarnings() {
    return state.earnings.find((item) => item.ticker === state.selectedTicker) || null;
  }

  function eventsForTicker() {
    return state.events.filter((event) => event.ticker === state.selectedTicker);
  }

  function manualReportsForTicker() {
    return state.manualReports.filter((item) => item.ticker === state.selectedTicker);
  }

  async function loadActiveStock() {
    state.activeStock = null;
    const filename = state.dashboardFiles[state.selectedTicker];
    if (filename) state.activeStock = await loadJsonOptional(`./data/dashboard/${filename}`);
  }

  function formatTime(value) {
    const d = new Date(value);
    return Number.isNaN(d.valueOf()) ? value || '–' : dateFmt.format(d);
  }

  function formatNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? numFmt.format(number) : '–';
  }

  function setQuery() {
    const url = new URL(location.href);
    if (state.selectedTicker) url.searchParams.set('ticker', state.selectedTicker);
    if (state.selectedEventId) url.searchParams.set('event', state.selectedEventId);
    else url.searchParams.delete('event');
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
      : '<option value="">Inga bolagsnyheter</option>';
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

  function ensureEarningsPanel() {
    if ($('eps-candidate-panel')) return;
    const epsValue = $('eps-value');
    const section = epsValue?.closest('section.panel');
    const header = section?.querySelector('.panel-header');
    if (!section || !header) return;

    const panel = document.createElement('div');
    panel.id = 'eps-candidate-panel';
    panel.className = 'lock-alert';
    panel.style.marginBottom = '18px';
    panel.innerHTML = `
      <div class="lock-icon">i</div>
      <div style="width:100%">
        <strong id="eps-candidate-title">Aktivt EPS TTM</strong>
        <p id="eps-candidate-summary" style="margin:.35rem 0 .65rem"></p>
        <div id="eps-candidate-meta" class="fine-print"></div>
      </div>`;
    header.insertAdjacentElement('afterend', panel);
  }

  function priorYearPeriod() {
    const periodText = $('eps-period-end')?.value;
    if (!periodText) return null;
    const target = new Date(`${periodText}T12:00:00Z`);
    if (Number.isNaN(target.valueOf())) return null;
    target.setUTCFullYear(target.getUTCFullYear() - 1);
    const priority = { manualDilutedEPS: 0, quarterlyDilutedEPS: 1 };
    return state.quarterly
      .filter((item) => item.ticker === state.selectedTicker && item.period_end && Object.hasOwn(priority, item.metric))
      .map((item) => {
        const date = new Date(`${item.period_end}T12:00:00Z`);
        return { item, distance: Math.abs(date.valueOf() - target.valueOf()) / 86400000 };
      })
      .filter((entry) => Number.isFinite(entry.distance) && entry.distance <= 21)
      .sort((a, b) => a.distance - b.distance || priority[a.item.metric] - priority[b.item.metric])[0]?.item || null;
  }

  function renderEarnings() {
    ensureEarningsPanel();
    const panel = $('eps-candidate-panel');
    if (!panel) return;
    const item = currentEarnings();
    const prior = priorYearPeriod();
    panel.hidden = false;
    const activeEps = state.activeStock?.latest?.eps_ttm;
    const activeReport = state.activeStock?.report;
    $('eps-candidate-title').textContent = `Aktivt EPS TTM i strategin · ${state.selectedTicker}`;
    $('eps-candidate-summary').textContent = Number.isFinite(Number(activeEps))
      ? `${formatNumber(activeEps)}${activeReport?.period ? ` för ${activeReport.period}` : ''}${activeReport?.effective_date ? `, används från ${activeReport.effective_date}` : ''}.`
      : '–';

    const details = [];
    if (item) {
      details.push(`Yahoo trailing EPS TTM som jämförelse: ${formatNumber(item.eps_ttm)}${item.period_end ? ` för perioden ${item.period_end}` : ''}.`);
    } else {
      details.push('Yahoo-jämförelse: –');
    }
    if (prior) {
      details.push(`Kvartals-EPS föregående år: ${formatNumber(prior.eps)} (${prior.period_end}).`);
    } else if ($('eps-metric')?.value === 'quarterly_eps') {
      details.push('Kvartals-EPS föregående år: –. Ett kvartalsvärde kan inte räknas om utan detta underlag.');
    }
    $('eps-candidate-meta').textContent = details.join(' ');
  }

  function renderManualReports() {
    const target = $('manual-report-list');
    if (!target) return;
    const items = manualReportsForTicker();
    target.innerHTML = items.length ? items.map((item) => {
      const direct = item.input_metric === 'eps_ttm';
      const inputLabel = direct ? 'Inmatat EPS TTM' : 'Inmatad kvartals-EPS';
      const dateLabel = item.published_at
        ? `Publicerad ${formatTime(item.published_at)}`
        : `Används från ${item.effective_date || '–'}`;
      return `<article class="manual-report-item">
        <div><strong>${esc(item.report_period || 'Rapport')}</strong><span>${esc(dateLabel)}</span></div>
        <dl>
          <div><dt>${inputLabel}</dt><dd>${esc(formatNumber(item.input_eps))}${item.eps_currency ? ` ${esc(item.eps_currency)}` : ''}</dd></div>
          <div><dt>Sparat EPS TTM</dt><dd>${esc(formatNumber(item.result_eps_ttm))}${item.eps_currency ? ` ${esc(item.eps_currency)}` : ''}</dd></div>
          <div><dt>Källa</dt><dd>${esc(item.source || '–')}</dd></div>
          <div><dt>Registrerad</dt><dd>${esc(formatTime(item.submitted_at))}</dd></div>
        </dl>
        ${item.notes ? `<p>${esc(item.notes)}</p>` : ''}
      </article>`;
    }).join('') : '<div class="empty-state">Inga manuella rapporteringar för aktien.</div>';
  }

  function updateEpsMetric() {
    const direct = $('eps-metric')?.value === 'eps_ttm';
    if ($('eps-value-label')) $('eps-value-label').textContent = direct ? 'EPS TTM' : 'Kvartals-EPS (utspädd)';
    renderEarnings();
    updateCommands();
  }

  function renderEvent() {
    const event = currentEvent();
    const reviewForm = $('review-form-title')?.closest('section.panel');
    $('eps-ticker').value = state.selectedTicker;
    $('cal-ticker').value = state.selectedTicker;
    $('trade-ticker').value = state.selectedTicker;
    renderEarnings();
    renderManualReports();

    if (!event) {
      $('event-empty').textContent = 'Inga bolagsnyheter för aktien.';
      $('event-empty').hidden = false;
      $('event-detail').hidden = true;
      if (reviewForm) reviewForm.hidden = true;
      updateCommands();
      return;
    }

    if (reviewForm) reviewForm.hidden = false;
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
      `metric=${$('eps-metric').value}`,
      `value=${$('eps-value').value}`,
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
    $('review-stock').addEventListener('change', async (e) => {
      state.selectedTicker = e.target.value;
      state.selectedEventId = eventsForTicker()[0]?.event_id || '';
      await loadActiveStock();
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
    $('eps-period-end')?.addEventListener('change', renderEarnings);
    $('eps-metric')?.addEventListener('change', updateEpsMetric);

    bindCopy('copy-review-command', 'review-command', 'review-copy-status');
    bindCopy('copy-eps-command', 'eps-command', 'eps-copy-status');
    bindCopy('copy-calendar-command', 'calendar-command');
    bindCopy('copy-trade-command', 'trade-command');
  }

  function setWorkflowLinks() {
    $('repository-link').href = REPO;
    ['review-action-link','calendar-action-link','trade-action-link'].forEach((id) => { $(id).href = `${REPO}/actions`; });
    $('eps-action-link').href = `${REPO}/actions/workflows/add_verified_eps.yml`;
  }

  async function init() {
    try {
      const [stocksPayload, eventsPayload, earningsPayload, quarterlyPayload, manualPayload, dashboardIndex] = await Promise.all([
        loadJson('./data/stocks.json'),
        loadJson('./data/events.json'),
        loadJsonOptional('./data/earnings.json'),
        loadJsonOptional('./data/quarterly_eps.json'),
        loadJsonOptional('./data/manual_reports.json'),
        loadJsonOptional('./data/dashboard/index.json')
      ]);
      state.stocks = stocksPayload.stocks || [];
      state.events = (eventsPayload.events || []).filter(isNewsEvent);
      state.earnings = earningsPayload?.latest || [];
      state.quarterly = quarterlyPayload?.history || [];
      state.manualReports = manualPayload?.submissions || [];
      state.dashboardFiles = dashboardIndex?.files || {};
      if (!state.stocks.length) throw new Error('Ingen aktielista hittades.');

      const params = new URLSearchParams(location.search);
      const wantedTicker = params.get('ticker');
      state.selectedTicker = state.stocks.some((s) => s.ticker === wantedTicker) ? wantedTicker : state.stocks[0].ticker;
      const events = eventsForTicker();
      const wantedEvent = params.get('event');
      state.selectedEventId = events.some((e) => e.event_id === wantedEvent) ? wantedEvent : (events[0]?.event_id || '');
      await loadActiveStock();

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
