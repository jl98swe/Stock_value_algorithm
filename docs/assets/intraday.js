/* Shared display quotes; daily candles, scores and trades are kept separate. */
(() => {
  'use strict';
  const CACHE_URL = 'https://raw.githubusercontent.com/jl98swe/Stock_value_algorithm/intraday-cache/intraday.json';
  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const clock = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', hour: '2-digit', minute: '2-digit' });
  let cache = null;
  let selection = null;
  let pending = null;
  const el = id => document.getElementById(id);
  const validPrice = value => typeof value === 'number' && Number.isFinite(value) && value > 0;

  function currentQuote(payload, ticker, dailyDate, now = Date.now()) {
    if (!payload || payload.schema_version !== 1 || !payload.session_date ||
        !Number.isFinite(Date.parse(payload.expires_at)) || Date.parse(payload.expires_at) <= now ||
        !Number.isFinite(Date.parse(payload.generated_at)) || Date.parse(payload.generated_at) > now + 60000 ||
        payload.session_date <= (dailyDate || '')) return null;
    const item = payload.stocks?.[ticker];
    const quote = item?.latest;
    const asOf = Date.parse(quote?.as_of);
    if (!validPrice(quote?.price) || !Number.isFinite(asOf) || asOf > now + 60000) return null;
    const quoteDay = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm',
      year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(asOf));
    return quoteDay === payload.session_date ? item : null;
  }

  function restore() {
    if (!selection) return;
    const { daily } = selection;
    el('latest-price').textContent = `${fmt.format(daily.close)} ${daily.currency}`;
    el('price-change').textContent = daily.changeText;
    el('price-change').className = daily.changeClass;
    el('stock-date').textContent = daily.dateText;
    el('intraday-panel').hidden = true;
  }

  function render() {
    if (!selection) return;
    const item = currentQuote(cache, selection.ticker, selection.daily.date);
    if (!item || item.latest.currency !== selection.daily.currency) { restore(); return; }
    const quote = item.latest;
    el('intraday-panel').hidden = false;
    el('latest-price').textContent = `${fmt.format(quote.price)} ${quote.currency}`;
    const change = validPrice(selection.daily.close) ? (quote.price / selection.daily.close - 1) * 100 : null;
    el('price-change').textContent = change === null ? '–' :
      `${change > 0 ? '+' : ''}${new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 }).format(change)} %`;
    el('price-change').className = `change-value ${change >= 0 ? 'positive' : 'negative'}`;
    el('stock-date').textContent = `Senaste avslut ${clock.format(new Date(quote.as_of))} · ${quote.source} · ${quote.currency}`;
    el('intraday-open').textContent = validPrice(item.opening?.price) ? fmt.format(item.opening.price) : 'Inväntar avslut';
    el('intraday-open-time').textContent = item.opening?.as_of ?
      `${item.opening.source} · ${clock.format(new Date(item.opening.as_of))}` : '';
    el('intraday-daily').textContent = `${fmt.format(selection.daily.close)} ${quote.currency}`;
    el('intraday-daily-date').textContent = selection.daily.date;
    el('intraday-note').textContent = `Hämtad ${clock.format(new Date(cache.generated_at))}. ` +
      (quote.source === 'Nasdaq' ? 'Nasdaq har minst 15 minuters fördröjning. ' : 'Avanza används som reservkälla. ') +
      'Uppdatering kl. 09.00, 13.00, 17.00 och 17.30. Öppning och stängning efterkontrolleras efter 20 minuter. Poäng och signaler avser senaste stängning.';
  }

  async function refresh() {
    if (pending) return pending;
    pending = (async () => {
      try {
        const response = await fetch(`${CACHE_URL}?t=${Math.floor(Date.now() / 60000)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error('cache unavailable');
        cache = await response.json();
      } catch { /* Keep a still-valid shared quote until expiry; never block the dashboard. */ }
      finally { pending = null; render(); }
    })();
    return pending;
  }

  window.intradayQuotes = {
    select(ticker, daily) { selection = { ticker, daily }; render(); },
    currentQuote,
    refresh
  };
  el('intraday-refresh')?.addEventListener('click', refresh);
  document.addEventListener('stock-selected', () => { render(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(() => { render(); if (!document.hidden) refresh(); }, 5 * 60000);
  refresh();
})();
