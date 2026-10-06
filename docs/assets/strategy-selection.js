(() => {
  'use strict';
  const names = {standard:'Standard',ma200:'MA200',report_avoidance:'Rapportundvikande'};
  let saved;
  try { saved = localStorage.getItem('overview-strategy'); } catch {}
  const requested = new URLSearchParams(location.search).get('strategy');
  let current = names[requested] ? requested : names[saved] ? saved : 'standard';
  function set(key) {
    if (!names[key]) return;
    current = key;
    try { localStorage.setItem('overview-strategy',key); } catch {}
    document.querySelectorAll('.page-nav a').forEach(link => {
      const url = new URL(link.href); url.searchParams.set('strategy',key); link.href=url;
    });
  }
  window.strategySelection = {names,get:()=>current,set};
  document.addEventListener('DOMContentLoaded',()=>set(current));
})();
