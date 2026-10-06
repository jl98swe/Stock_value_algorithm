(() => {
  'use strict';
  const names = {standard:'Standard',ma200:'MA200',report_avoidance:'Rapportundvikande'};
  let saved;
  try { saved = localStorage.getItem('overview-strategy'); } catch {}
  const params = new URLSearchParams(location.search);
  const requested = params.get('strategy');
  let savedTicker;
  try { savedTicker = localStorage.getItem('selected-stock'); } catch {}
  let ticker = params.get('ticker') && params.get('ticker') !== 'all' ? params.get('ticker') : savedTicker || null;
  let current = names[requested] ? requested : names[saved] ? saved : 'standard';
  function updateNavigation() {
    document.querySelectorAll('.page-nav a').forEach(link => {
      const url = new URL(link.href); url.searchParams.set('strategy',current);
      if (ticker) url.searchParams.set('ticker',ticker);
      link.href=url;
    });
  }
  function setTicker(value) {
    if (!value || value === 'all') return;
    ticker = value;
    try { localStorage.setItem('selected-stock',value); } catch {}
    updateNavigation();
  }
  function set(key) {
    if (!names[key]) return;
    current = key;
    try { localStorage.setItem('overview-strategy',key); } catch {}
    updateNavigation();
  }
  window.strategySelection = {names,get:()=>current,set,getTicker:()=>ticker,setTicker};
  document.addEventListener('DOMContentLoaded',()=>set(current));
})();
