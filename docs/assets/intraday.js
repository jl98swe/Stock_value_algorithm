/* Shared display quotes; preliminary scores are separate from daily candles and trades. */
(() => {
  'use strict';
  const CACHE_URL = 'https://raw.githubusercontent.com/jl98swe/Stock_value_algorithm/intraday-cache/intraday.json';
  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const clock = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Stockholm', hour: '2-digit', minute: '2-digit' });
  let cache = null;
  let selection = null;
  let pending = null;
  const listeners = new Set();
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

  function currentValuation(payload, ticker, dailyDate, currency = 'SEK', now = Date.now()) {
    const item = currentQuote(payload, ticker, dailyDate, now);
    const v = item?.valuation, q = item?.latest;
    if (!v || v.preliminary !== true || typeof v.score !== 'number' || !Number.isFinite(v.score) ||
        v.score < 0 || v.score > 100 || v.session !== payload.session_date ||
        v.basis_date !== dailyDate || v.as_of !== q.as_of || v.price !== q.price ||
        v.currency !== currency || q.currency !== currency) return null;
    return v;
  }

  function preview(ticker, dailyDate, now = Date.now()) {
    const item = currentQuote(cache, ticker, dailyDate, now);
    if (!item || (selection?.ticker === ticker && item.latest.currency !== selection.daily.currency)) return null;
    const price = item.latest.price, open = item.opening?.price;
    const high = item.day_high, low = item.day_low;
    const completeOHLC = [open, high, low].every(validPrice) && high >= Math.max(open, price) && low <= Math.min(open, price);
    // Consume only a valuation computed for this exact cached quote.
    const score = currentValuation(cache, ticker, dailyDate, item.latest.currency, now)?.score ?? null;
    return { score, candle: { date: cache.session_date, open, close: price, high, low, preliminary: true, completeOHLC } };
  }

  function notify() {
    document.dispatchEvent?.(new CustomEvent('intraday-updated'));
  }

  function restore() {
    if (!selection) return;
    const { daily } = selection;
    el('latest-price').textContent = `${fmt.format(daily.close)} ${daily.currency}`;
    el('price-change').textContent = daily.changeText;
    el('price-change').className = daily.changeClass;
    el('stock-date').textContent = daily.dateText;
    el('intraday-panel').hidden = true;
    notify();
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
      (quote.source === 'Nasdaq' ? 'Nasdaq har minst 15 minuters fördröjning. ' : 'Avanza är huvudkälla; kursen kan vara fördröjd. ') +
      'Öppningskurs från 09.20. Övriga hämtningar kl. 13.00, 17.00 och 17.30, med efterkontroll 17.50. Schemalagda starter kan försenas. Preliminär poäng gäller om aktien stänger på den visade kursen, med senast verifierad EPS. Ordinarie poäng och signaler fastställs efter stängning.';
    notify();
  }

  async function refresh() {
    if (pending) return pending;
    pending = (async () => {
      try {
        const response = await fetch(`${CACHE_URL}?t=${Math.floor(Date.now() / 60000)}`, { cache: 'no-store' });
        if (!response.ok) throw new Error('cache unavailable');
        cache = await response.json();
      } catch { /* Keep a still-valid shared quote until expiry; never block the dashboard. */ }
      finally { pending = null; render(); listeners.forEach(callback => callback()); }
    })();
    return pending;
  }

  window.intradayQuotes = {
    select(ticker, daily) { selection = { ticker, daily }; render(); },
    currentQuote,
    preview,
    currentValuation,
    valuation(ticker, dailyDate, currency) { return currentValuation(cache, ticker, dailyDate, currency); },
    onUpdate(callback) { listeners.add(callback); },
    refresh
  };
  el('intraday-refresh')?.addEventListener('click', refresh);
  document.addEventListener('stock-selected', () => { render(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(() => { render(); if (!document.hidden) refresh(); }, 5 * 60000);
  refresh();
})();
