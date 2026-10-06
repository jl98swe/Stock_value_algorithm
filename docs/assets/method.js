(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const percent = value => value == null || !Number.isFinite(value) ? '–' : `${value > 0 ? '+' : ''}${new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 2}).format(value)} %`;
  const number = value => value == null ? '–' : new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 4}).format(value);
  const names = {standard:'Standard', ma200:'MA200', report_avoidance:'Rapportundvikande'};

  function periodStart(end, years, first) {
    if (!years || years === 'all') return first;
    const d = new Date(`${end}T12:00:00Z`), month = d.getUTCMonth();
    d.setUTCFullYear(d.getUTCFullYear() - Number(years));
    if (d.getUTCMonth() !== month) d.setUTCDate(0);
    return d.toISOString().slice(0,10);
  }
  function selectTrades(variant, start, end) {
    return {
      closed: (variant.closed_trades || []).filter(t => t.entry_date >= start && t.entry_date <= end && t.exit_date >= t.entry_date && t.exit_date <= end),
      open: (variant.open_lots || []).filter(t => t.entry_date >= start && t.entry_date <= end)
    };
  }
  function compound(trades) {
    return trades.length ? (trades.reduce((v,t) => v * (1 + t.return_pct / 100), 1) - 1) * 100 : null;
  }
  function closedDrawdown(candles, trades, dividends) {
    if (!trades.length) return null;
    let capital = 1, peak = 1, worst = 0;
    for (const trade of [...trades].sort((a,b) => a.entry_date.localeCompare(b.entry_date))) {
      let paid = 0;
      for (const c of candles.filter(c => c.date >= trade.entry_date && c.date <= trade.exit_date)) {
        // The ex-date dividend belongs only to a share held before that opening.
        if (c.date > trade.entry_date) paid += dividends.filter(d => d.date === c.date).reduce((sum,d) => sum + Number(d.amount || 0),0);
        const factor = c.date === trade.exit_date ? 1 + trade.return_pct / 100 : (c.close + paid) / (trade.entry_price * 1.0025);
        const equity = capital * factor;
        peak = Math.max(peak,equity); worst = Math.min(worst,(equity / peak - 1) * 100);
      }
      capital *= 1 + trade.return_pct / 100;
    }
    return worst;
  }
  // Also exposed for deterministic tests of the period rules.
  if (typeof module !== 'undefined') module.exports = {periodStart, selectTrades, compound, closedDrawdown};
  if (typeof document === 'undefined') return;

  const params = new URLSearchParams(location.search);
  let stock = null, variants = null, stockMeta = null, requestId = 0;
  async function json(path) {
    const response = await fetch(path, {cache:'no-store'});
    if (!response.ok) throw new Error(`Kunde inte läsa ${path} (HTTP ${response.status}).`);
    return response.json();
  }
  function render() {
    if (!stock || !variants) return;
    const key = $('method-strategy').value, end = stock.candles.at(-1).date;
    const first = stock.candles[0].date;
    const start = periodStart(end, $('method-period').value, first);
    const ticker = $('method-stock').value;
    const url = new URL(location.href);
    url.searchParams.set('ticker', ticker); url.searchParams.set('strategy',key);
    url.searchParams.set('period', $('method-period').value); history.replaceState({}, '', url);
    $('as-of-date').textContent = end;
    $('period-caption').textContent = `${start} – ${end}${start < first ? ` · Tillgänglig data från ${first}` : ''}`;
    $('method-stock-link').href = `./index.html?ticker=${encodeURIComponent(ticker)}`;
    document.querySelectorAll('[data-method]').forEach(el => el.hidden = el.dataset.method !== key);
    const windowCandles = stock.candles.filter(c => c.date >= start && c.date <= end);
    let benchmark = null;
    if (windowCandles.length >= 2) {
      const firstC = windowCandles[0], lastC = windowCandles.at(-1);
      const dividends = (variants._dividends || []).filter(e => e.date > firstC.date && e.date <= lastC.date)
        .reduce((sum,e) => sum + Number(e.amount || 0), 0);
      // A held share plus cash dividends, with the same entry/exit commission.
      benchmark = ((lastC.close * .9975 + dividends) / (firstC.close * 1.0025) - 1) * 100;
    }
    const selected = selectTrades(variants[key] || {}, start, end);
    $('backtest-summary').innerHTML = Object.entries(names).map(([id,name]) => {
      const trades = selectTrades(variants[id] || {}, start,end), closed = trades.closed;
      const value = compound(closed);
      const win = closed.length ? closed.filter(t => t.return_pct > 0).length / closed.length * 100 : null;
      const open = trades.open[0];
      return `<tr${id === key ? ' class="selected-method"' : ''}><td><button class="text-button" data-strategy="${id}">${name}</button></td><td>${percent(value)}</td><td>${percent(closedDrawdown(stock.candles,closed,variants._dividends || []))}</td><td>${closed.length}</td><td>${percent(win)}</td><td>${closed.length ? percent(closed.reduce((sum,t) => sum + t.return_pct,0) / closed.length) : '–'}</td><td>${open ? `${percent(open.current_return_pct)} (preliminärt)` : 'Ingen'}</td></tr>`;
    }).join('');
    $('benchmark-result').textContent = `Köp och behåll under perioden: ${percent(benchmark)} (inklusive utdelningar och courtage).`;
    const trades = [...selected.closed.map(t => ({...t, open:false})), ...selected.open.map(t => ({...t,open:true}))].sort((a,b) => b.entry_date.localeCompare(a.entry_date));
    $('method-trades').innerHTML = trades.length ? trades.map(t => {
      const result = t.open ? t.current_return_pct : t.return_pct;
      const days = Math.round((Date.parse(t.open ? end : t.exit_date) - Date.parse(t.entry_date)) / 86400000);
      return `<tr class="trade-${result > 5 ? 'win' : result < -5 ? 'loss' : 'flat'}"><td>${esc(t.entry_date)}</td><td>${t.open ? 'Öppen' : esc(t.exit_date)}</td><td>${days} dagar</td><td>${number(t.entry_price)}</td><td>${t.open ? '–' : number(t.exit_price)}</td><td>${percent(result)}${t.open ? ' (preliminärt)' : ''}</td><td>${t.open ? '–' : t.exit_reason === 'report' ? 'Inför rapport' : 'Värderingspoäng'}</td></tr>`;
    }).join('') : '<tr><td colspan="7">Inga affärer som uppfyller periodens villkor.</td></tr>';
    $('report-coverage').textContent = key === 'report_avoidance' ? `${variants[key]?.report_dates_count || 0} rapportdatum i underlaget. Nya köp blockeras när nästa rapportdatum saknas.` : '';
  }
  async function loadStock() {
    const id = ++requestId, ticker = $('method-stock').value;
    stock = null; variants = null; $('method-results').hidden = true; $('error-state').hidden = true; $('loading-state').hidden = false;
    try {
      const [data, tests] = await Promise.all([json(`./data/dashboard/${encodeURIComponent(ticker)}.json`),json(`./data/backtests/${encodeURIComponent(ticker)}.json`)]);
      if (id !== requestId) return;
      stock = data; variants = tests;
      if (!tests.standard || !tests.ma200 || !tests.report_avoidance) throw new Error('Backtest saknas för aktien eftersom värderingsunderlaget ännu inte är komplett.');
      $('method-results').hidden = false; render();
    } catch(error) {
      if (id !== requestId) return;
      $('error-state').hidden = false; $('error-message').textContent = error.message;
    } finally { if (id === requestId) $('loading-state').hidden = true; }
  }
  async function init() {
    try {
      stockMeta = await json('./data/stocks.json');
      $('last-updated').textContent = stockMeta.meta?.generated_at?.slice(0,10) || '–';
      $('method-stock').innerHTML = stockMeta.stocks.map(s => `<option value="${esc(s.ticker)}">${esc(s.name)} · ${esc(s.ticker)}</option>`).join('');
      if (stockMeta.stocks.some(s => s.ticker === params.get('ticker'))) $('method-stock').value = params.get('ticker');
      if (names[params.get('strategy')]) $('method-strategy').value = params.get('strategy');
      if (['all','1','3','5'].includes(params.get('period'))) $('method-period').value = params.get('period');
      $('method-stock').addEventListener('change', loadStock);
      $('method-strategy').addEventListener('change', render); $('method-period').addEventListener('change', render);
      $('backtest-summary').addEventListener('click', e => { const b=e.target.closest('[data-strategy]'); if(b){ $('method-strategy').value=b.dataset.strategy; render(); } });
      await loadStock();
    } catch(error) { $('loading-state').hidden=true; $('error-state').hidden=false; $('error-message').textContent=error.message; }
  }
  init();
})();
