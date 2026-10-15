(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      const response = await fetch('./data/reports.json', { cache: 'no-store' });
      if (!response.ok) return;
      const payload = await response.json();
      const missing = payload.missing_data || [];
      const withoutEps = location.pathname.endsWith('reports.html') ? (payload.reports_without_eps || []) : [];
      if (!missing.length && !withoutEps.length) return;
      const host = document.querySelector('main');
      if (!host) return;
      const panel = document.createElement('section');
      panel.className = `report-data-alert ${missing.length ? 'report-data-alert-warning' : ''}`;
      panel.setAttribute('role', 'status');
      const title = document.createElement('strong');
      title.textContent = missing.length ? `EPS-data saknas för ${missing.length} rapport${missing.length === 1 ? '' : 'er'}` : 'Redogörelse utan EPS';
      panel.append(title);
      if (missing.length) {
        const description = document.createElement('p');
        description.textContent = 'Rapportdatumet har passerat, men nya EPS-data har inte kommit in. Värderingspoäng och signaler använder fortfarande äldre rapportdata.';
        panel.append(description);
      }
      const list = document.createElement('ul');
      for (const row of [...missing, ...withoutEps]) {
        const item = document.createElement('li');
        const link = document.createElement('a');
        link.href = `./index.html?ticker=${encodeURIComponent(row.ticker)}`;
        link.textContent = row.ticker;
        item.append(link, ` · ${row.report_date} · ${row.message}`);
        list.append(item);
      }
      panel.append(list);
      host.prepend(panel);
    } catch (error) {
      console.error('Kunde inte läsa rapportdatastatus', error);
    }
  });
})();
