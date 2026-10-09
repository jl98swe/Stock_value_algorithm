(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const percent = value => value == null || !Number.isFinite(value) ? '–' : `${value > 0 ? '+' : ''}${new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 2}).format(value)} %`;
  const number = value => value == null ? '–' : new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 4}).format(value);
  const ratio = value => value == null || !Number.isFinite(value) ? '–' : new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 2}).format(value);
  const names = {standard:'Standard', ma200:'MA200', report_avoidance:'Rapportundvikande', buy_and_hold:'Buy and hold', omxsgi:'OMXSGI'};
  const reference = key => key === 'buy_and_hold' || key === 'omxsgi';

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
  function equityMetrics(values) {
    if (!values.length) return {return_pct:null, max_drawdown_pct:null, sharpe_ratio:null};
    let previous = 1, peak = 1, worst = 0;
    const returns = values.map(value => {
      const change = value / previous - 1; previous = value;
      peak = Math.max(peak,value); worst = Math.min(worst,(value / peak - 1) * 100);
      return change;
    });
    const mean = returns.reduce((a,b) => a+b,0) / returns.length;
    const deviation = returns.length > 1 ? Math.sqrt(returns.reduce((sum,r) => sum + (r-mean)**2,0) / (returns.length-1)) : 0;
    return {return_pct:(values.at(-1)-1)*100, max_drawdown_pct:worst,
      sharpe_ratio:deviation > 1e-12 ? mean / deviation * Math.sqrt(252) : null};
  }
  function closedEquity(candles, trades, dividends, dates) {
    let capital = 1;
    const factors = new Map(), dividendMap = new Map();
    for (const d of dividends) dividendMap.set(d.date,(dividendMap.get(d.date) || 0) + Number(d.amount || 0));
    for (const trade of [...trades].sort((a,b) => a.entry_date.localeCompare(b.entry_date))) {
      let paid = 0;
      for (const c of candles.filter(c => c.date >= trade.entry_date && c.date <= trade.exit_date)) {
        // The ex-date dividend belongs only to a share held before that opening.
        if (c.date > trade.entry_date) paid += dividendMap.get(c.date) || 0;
        const factor = c.date === trade.exit_date ? 1 + trade.return_pct / 100 : (c.close + paid) / (trade.entry_price * 1.0025);
        factors.set(c.date,capital * factor);
      }
      capital *= 1 + trade.return_pct / 100;
      factors.set(trade.exit_date,capital);
    }
    let current = 1;
    return dates.map(day => {current = factors.get(day) ?? current; return current;});
  }
  function closedDrawdown(candles, trades, dividends) {
    return trades.length ? equityMetrics(closedEquity(candles,trades,dividends,candles.map(c=>c.date))).max_drawdown_pct : null;
  }
  function holdCurve(candles, dividends, dates, commission=.0025) {
    const window = dates.length ? candles.filter(c => c.date >= dates[0] && c.date <= dates.at(-1)) : [];
    if (window.length < 2) return {equity:dates.map(()=>1),trade:null};
    const first = window[0], last = window.at(-1), byDay = new Map(window.map(c=>[c.date,c]));
    const dividendMap = new Map();
    for (const d of dividends.filter(d=>d.date>first.date && d.date<=last.date)) dividendMap.set(d.date,(dividendMap.get(d.date)||0)+Number(d.amount||0));
    let current=1, paid=0;
    const equity=dates.map(day=>{
      paid += dividendMap.get(day)||0;
      const c=byDay.get(day);
      if(c) current=(c.close*(day===last.date ? 1-commission : 1)+paid)/(first.close*(1+commission));
      return current;
    });
    return {equity,trade:{entry_date:first.date,exit_date:last.date,entry_price:first.close,exit_price:last.close,
      return_pct:(equity.at(-1)-1)*100,exit_reason:'period_end'}};
  }
  function referenceSummary(candles, dividends, dates, commission=.0025) {
    const {equity,trade}=holdCurve(candles,dividends,dates,commission);
    return {summary:{...equityMetrics(trade ? equity : []),trade_count:trade ? 1 : 0,
      win_rate_pct:trade ? trade.return_pct>0 ? 100 : 0 : null,average_trade_pct:trade?.return_pct ?? null,
      open_count:0,open_return_pct:null},trades:trade ? [trade] : []};
  }
  function fullHistoryRows(stock, variants, indexData) {
    const candles = stock.candles || [], dates = candles.map(c => c.date);
    const start = dates[0], end = dates.at(-1);
    const indexCandles = (indexData?.candles || []).filter(c => c.date >= start && c.date <= end);
    const indexDates = dates.filter(d => indexCandles.length && d >= indexCandles[0].date && d <= indexCandles.at(-1).date);
    const references = {
      buy_and_hold: referenceSummary(candles, variants?._dividends || [], dates),
      omxsgi: referenceSummary(indexCandles, [], indexDates, 0)
    };
    return Object.entries(names).map(([id, name]) => {
      const closed = reference(id) ? references[id].trades : variants?.[id]?.closed_trades || [];
      const summary = reference(id) ? references[id].summary : {
        return_pct: compound(closed), trade_count: closed.length,
        win_rate_pct: closed.length ? closed.filter(t => t.return_pct > 0).length / closed.length * 100 : null
      };
      return { id, name, start: id === 'omxsgi' ? indexDates[0] : start,
        end: id === 'omxsgi' ? indexDates.at(-1) : end, ...summary };
    });
  }
  // Also exposed for deterministic tests of the period rules.
  if (typeof module !== 'undefined') module.exports = {periodStart, selectTrades, compound, closedDrawdown, closedEquity, equityMetrics, holdCurve, referenceSummary, fullHistoryRows};
  if (typeof window !== 'undefined') window.backtestMetrics = {fullHistoryRows};
  if (typeof document === 'undefined' || !document.getElementById('method-stock')) return;

  const params = new URLSearchParams(location.search);
  let stock = null, variants = null, stockMeta = null, indexData = null, requestId = 0, visibleTrades = 50;
  async function json(path) {
    const response = await fetch(path, {cache:'no-store'});
    if (!response.ok) throw new Error(`Kunde inte läsa ${path} (HTTP ${response.status}).`);
    return response.json();
  }
  function render() {
    if (!variants) return;
    const ticker = $('method-stock').value, all = ticker === 'all';
    window.strategySelection.setTicker(ticker);
    const key = $('method-strategy').value, period = $('method-period').value;
    window.strategySelection.set(key);
    const end = all ? variants.meta.end_date : stock.candles.at(-1).date;
    const first = all ? variants.meta.start_date : stock.candles[0].date;
    const start = all ? variants.periods[period].start_date : periodStart(end, period, first);
    const url = new URL(location.href);
    url.searchParams.set('ticker', ticker); url.searchParams.set('strategy',key);
    url.searchParams.set('period', $('method-period').value); history.replaceState({}, '', url);
    $('as-of-date').textContent = end;
    $('period-caption').textContent = `${start} – ${end}${start < first ? ` · Tillgänglig data från ${first}` : ''}`;
    $('method-stock-link').hidden = all || key === 'omxsgi';
    $('method-stock-link').href = `./index.html?ticker=${encodeURIComponent(ticker)}&strategy=${window.strategySelection.get()}`;
    $('method-name').textContent = names[key];
    $('method-summary').textContent = ({standard:'Köp under 1, sälj över 99. Högst en aktiv position per aktie.',ma200:'Standard med köp endast över MA200. Säljregeln är oförändrad.',report_avoidance:'Inga köp inom 10 handelsdagar före rapport. Sälj handelsdagen före rapport.',buy_and_hold:'Köp aktieurvalet vid periodens första tillgängliga stängning och behåll till periodens slut.',omxsgi:'Stockholmsbörsens breda avkastningsindex med återinvesterade utdelningar.'})[key];
    $('scope-note').textContent = all ? `${variants.meta.stock_count} aktier · Lika kapitalandel per aktie · Öppna positioner redovisas separat.${variants.meta.excluded_stocks.length ? ` ${variants.meta.excluded_stocks.length} aktier saknar komplett underlag och ingår inte.` : ''}` : 'Enskild aktie · Öppna positioner redovisas separat.';
    document.querySelectorAll('[data-method]').forEach(el => el.hidden = el.dataset.method !== key);
    document.querySelectorAll('[data-signal-rules]').forEach(el => el.hidden = reference(key));
    const windowCandles = all ? [] : stock.candles.filter(c => c.date >= start && c.date <= end);
    const dates = windowCandles.map(c=>c.date);
    const indexWindow = (indexData?.candles || []).filter(c=>c.date >= (all ? start : dates[0] || start) && c.date <= end);
    const indexDates = all ? [] : dates.filter(d=>indexWindow.length && d>=indexWindow[0].date && d<=indexWindow.at(-1).date);
    const references = all ? null : {
      buy_and_hold:referenceSummary(windowCandles,variants._dividends || [],dates),
      omxsgi:referenceSummary(indexWindow,[],indexDates,0)
    };
    const selected = reference(key) ? {closed:all ? variants.periods[period].reference_trades?.[key] || [] : references[key].trades, open:[]} : selectTrades(variants[key] || {}, start, end);
    $('backtest-summary').innerHTML = Object.entries(names).map(([id,name]) => {
      const trades = reference(id) ? {closed:all ? variants.periods[period].reference_trades?.[id] || [] : references[id].trades,open:[]} : selectTrades(variants[id] || {}, start,end), closed = trades.closed;
      const summary = all ? variants.periods[period].strategies[id] || {} : reference(id) ? references[id].summary : {
        ...equityMetrics(closed.length ? closedEquity(stock.candles,closed,variants._dividends || [],dates) : []),
        return_pct:compound(closed),trade_count:closed.length,
        win_rate_pct:closed.length ? closed.filter(t=>t.return_pct>0).length/closed.length*100 : null,
        average_trade_pct:closed.length ? closed.reduce((sum,t)=>sum+t.return_pct,0)/closed.length : null
      };
      const open = trades.open[0];
      const openText = all ? summary.open_count ? `${summary.open_count} st · snitt ${percent(summary.open_return_pct)} (preliminärt)` : 'Ingen' : open ? `${percent(open.current_return_pct)} (preliminärt)` : 'Ingen';
      return `<tr><td>${name}</td><td>${percent(summary.return_pct)}</td><td>${percent(summary.max_drawdown_pct)}</td><td>${ratio(summary.sharpe_ratio)}</td><td>${summary.trade_count ?? closed.length}</td><td>${percent(summary.win_rate_pct)}</td><td>${percent(summary.average_trade_pct)}</td><td>${openText}</td></tr>`;
    }).join('');
    const indexTrades = all ? variants.periods[period].reference_trades?.omxsgi || [] : references.omxsgi.trades;
    $('index-coverage').textContent = indexTrades.length ? `OMXSGI: ${indexTrades[0].entry_date} – ${indexTrades[0].exit_date} · Nasdaq via FRED · Utdelningar återinvesteras före skatt; inga fondavgifter eller courtage.` : 'OMXSGI saknar tillräckligt underlag för perioden.';
    const trades = [...selected.closed.map(t => ({...t, open:false})), ...selected.open.map(t => ({...t,open:true}))].sort((a,b) => b.entry_date.localeCompare(a.entry_date));
    $('method-trades').innerHTML = trades.length ? trades.slice(0,visibleTrades).map(t => {
      const result = t.open ? t.current_return_pct : t.return_pct;
      const days = Math.round((Date.parse(t.open ? (t.valuation_date || end) : t.exit_date) - Date.parse(t.entry_date)) / 86400000);
      const label = key === 'omxsgi' ? 'OMXSGI' : `<a href="./method.html?ticker=${encodeURIComponent(t.ticker || ticker)}&amp;strategy=${key}&amp;period=${period}">${esc(stockMeta.stocks.find(s => s.ticker === (t.ticker || ticker))?.name || t.ticker || ticker)}</a>`;
      return `<tr class="trade-${result > 5 ? 'win' : result < -5 ? 'loss' : 'flat'}"><td>${label}</td><td>${esc(t.entry_date)}</td><td>${t.open ? 'Öppen' : esc(t.exit_date)}</td><td>${days} dagar</td><td>${number(t.entry_price)}</td><td>${t.open ? '–' : number(t.exit_price)}</td><td>${percent(result)}${t.open ? ' (preliminärt)' : ''}</td><td>${t.open ? '–' : t.exit_reason === 'period_end' ? 'Periodens slut' : t.exit_reason === 'report' ? 'Inför rapport' : 'Värderingspoäng'}</td></tr>`;
    }).join('') : '<tr><td colspan="8">Inga affärer som uppfyller periodens villkor.</td></tr>';
    $('method-trades-more').hidden = trades.length <= visibleTrades;
    $('method-trades-count').textContent = `Visar ${Math.min(visibleTrades,trades.length)} av ${trades.length} affärer.`;
    $('report-coverage').textContent = key === 'report_avoidance' ? `${variants[key]?.report_dates_count || 0} rapportdatum i underlaget. Nya köp blockeras när nästa rapportdatum saknas.` : '';
  }
  async function loadStock() {
    const id = ++requestId, ticker = $('method-stock').value;
    window.strategySelection.setTicker(ticker);
    stock = null; variants = null; $('method-results').hidden = true; $('error-state').hidden = true; $('loading-state').hidden = false;
    try {
      const [data, tests] = ticker === 'all' ? [null, await json('./data/backtests/all.json')] : await Promise.all([json(`./data/dashboard/${encodeURIComponent(ticker)}.json`),json(`./data/backtests/${encodeURIComponent(ticker)}.json`)]);
      if (id !== requestId) return;
      stock = data; variants = tests;
      if (!tests.standard || !tests.ma200 || !tests.report_avoidance) throw new Error('Backtest saknas för aktien eftersom värderingsunderlaget ännu inte är komplett.');
      visibleTrades = 50; $('method-results').hidden = false; render();
    } catch(error) {
      if (id !== requestId) return;
      $('error-state').hidden = false; $('error-message').textContent = error.message;
    } finally { if (id === requestId) $('loading-state').hidden = true; }
  }
  async function init() {
    try {
      [stockMeta,indexData] = await Promise.all([json('./data/stocks.json'),json('./data/benchmarks/omxsgi.json').catch(()=>null)]);
      $('last-updated').textContent = (stockMeta.generated_at || stockMeta.meta?.generated_at)?.slice(0,10) || '–';
      $('method-stock').innerHTML = '<option value="all">Alla aktier</option>' + stockMeta.stocks.map(s => `<option value="${esc(s.ticker)}">${esc(s.name)} · ${esc(s.ticker)}</option>`).join('');
      const wantedTicker = params.get('ticker') === 'all' ? 'all' : window.strategySelection.getTicker();
      if (stockMeta.stocks.some(s => s.ticker === wantedTicker)) $('method-stock').value = wantedTicker;
      $('method-strategy').value = names[params.get('strategy')] ? params.get('strategy') : window.strategySelection.get();
      if (['all','1','3','5'].includes(params.get('period'))) $('method-period').value = params.get('period');
      $('method-stock').addEventListener('change', loadStock);
      const reset = () => { visibleTrades = 50; render(); };
      $('method-strategy').addEventListener('change', reset); $('method-period').addEventListener('change', reset);
      $('method-trades-more').addEventListener('click', () => { visibleTrades += 50; render(); });
      $('method-details-toggle').addEventListener('click', () => {
        const expanded = $('method-details-toggle').getAttribute('aria-expanded') !== 'true';
        $('method-details').hidden = !expanded;
        $('method-details-toggle').setAttribute('aria-expanded', String(expanded));
        $('method-details-toggle').textContent = expanded ? 'Visa mindre' : 'Visa mer';
      });
      await loadStock();
    } catch(error) { $('loading-state').hidden=true; $('error-state').hidden=false; $('error-message').textContent=error.message; }
  }
  init();
})();

