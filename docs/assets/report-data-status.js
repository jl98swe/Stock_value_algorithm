(() => {
  'use strict';
  // null means all warnings; an empty set means no visible stocks yet.
  let tickers = document.body.dataset.overview === 'signals'
    || location.pathname.endsWith('/reports.html') ? null : new Set();
  let payload = {};
  const stockholmDay = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Stockholm', year:'numeric', month:'2-digit', day:'2-digit'});

  function missingReports() {
    const today = stockholmDay.format(new Date());
    const key = row => `${row.ticker}:${row.report_date}`;
    const excluded = new Set((payload.reports_without_eps || []).map(key));
    const rows = new Map((payload.missing_data || [])
      .filter(row => row.report_date <= today && !excluded.has(key(row)))
      .map(row => [key(row), row]));
    // A static export may still be dated yesterday. Re-evaluate known calendar
    // events against Stockholm today, without waiting for the next data build.
    for (const event of payload.upcoming || []) {
      const date = event.report_date_end || event.report_date_start;
      if (!date || date > today) continue;
      const row = {ticker:event.ticker, report_date:date};
      const fresh = (payload.recent || []).some(report => report.ticker === event.ticker
        && report.report_date >= date && report.report_date <= today && report.eps_ttm_after != null);
      if (event.new_eps_ttm != null || fresh || excluded.has(key(row))) {
        rows.delete(key(row));
      } else {
        rows.set(key(row), row);
      }
    }
    return [...rows.values()].sort((a,b) => a.report_date.localeCompare(b.report_date) || a.ticker.localeCompare(b.ticker));
  }
  let panel;
  window.reportDataStatus = {
    setTickers(values) {
      tickers = new Set(values);
      render();
    }
  };

  function render() {
    panel?.remove();
    const visible = missingReports().filter(row => tickers === null || tickers.has(row.ticker));
    if (!visible.length) return;
    const host = document.querySelector('main');
    if (!host) return;

    panel = document.createElement('section');
    panel.className = 'report-data-alert report-data-alert-warning';
    panel.setAttribute('role', 'status');
    const title = document.createElement('strong');
    title.textContent = `EPS-data saknas för ${visible.length} rapport${visible.length === 1 ? '' : 'er'}`;
    panel.append(title);
    if (visible.length) {
      const description = document.createElement('p');
      description.textContent = 'Ny EPS TTM är ännu inte registrerad. Poäng och signaler använder äldre rapportdata.';
      panel.append(description);
    }
    const list = document.createElement('ul');
    for (const row of visible) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = `./index.html?ticker=${encodeURIComponent(row.ticker)}`;
      link.textContent = row.ticker;
      const entry = document.createElement('a');
      entry.href = location.pathname.endsWith('/review.html')
        ? '#eps-form-title'
        : `./review.html?ticker=${encodeURIComponent(row.ticker)}#eps-form-title`;
      entry.textContent = 'Lägg in EPS';
      entry.setAttribute('aria-label', `Lägg in EPS för ${row.ticker} på Nyheter och data`);
      item.append(link, ` · ${row.report_date} · `, entry);
      list.append(item);
    }
    panel.append(list);
    host.prepend(panel);
  }

  async function refresh() {
    try {
      const response = await fetch('./data/reports.json', { cache: 'no-store' });
      if (response.ok) payload = await response.json();
    } catch (error) {
      console.error('Kunde inte läsa rapportdatastatus', error);
    }
    render();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await refresh();
    setInterval(refresh, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) return refresh(); });
  });
})();
