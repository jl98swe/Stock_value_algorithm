(() => {
  'use strict';
  // null means all warnings; an empty set means no visible stocks yet.
  let tickers = document.body.dataset.overview === 'signals'
    || location.pathname.endsWith('/reports.html') ? null : new Set();
  let missing = [];
  let panel;
  window.reportDataStatus = {
    setTickers(values) {
      tickers = new Set(values);
      render();
    }
  };

  function render() {
    panel?.remove();
    const visible = missing.filter(row => tickers === null || tickers.has(row.ticker));
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
      description.textContent = 'Rapportdatumet har passerat, men nya EPS-data har inte kommit in. Värderingspoäng och signaler använder fortfarande äldre rapportdata.';
      panel.append(description);
    }
    const list = document.createElement('ul');
    for (const row of visible) {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = `./index.html?ticker=${encodeURIComponent(row.ticker)}`;
      link.textContent = row.ticker;
      item.append(link, ` · ${row.report_date} · ${row.message}`);
      list.append(item);
    }
    panel.append(list);
    host.prepend(panel);
  }

  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const response = await fetch('./data/reports.json', { cache: 'no-store' });
      if (!response.ok) return;
      const payload = await response.json();
      missing = payload.missing_data || [];
      render();
    } catch (error) {
      console.error('Kunde inte läsa rapportdatastatus', error);
    }
  });
})();
