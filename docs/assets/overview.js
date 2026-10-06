(() => {
  'use strict';

  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const pctFmt = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dateFmt = new Intl.DateTimeFormat('sv-SE', { year: 'numeric', month: 'short', day: 'numeric' });
  const $ = (id) => document.getElementById(id);
  const strategies = {standard:'Standard', ma200:'MA200', report_avoidance:'Rapportundvikande'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let strategy = 'standard';
  let priceBoundaries = {};
  let marketDate = null;
  const stockHref = ticker => `./index.html?ticker=${encodeURIComponent(ticker)}&strategy=${strategy}`;

  function number(value) {
    if (value == null || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function pct(value) {
    const n = number(value);
    return n === null ? '–' : `${n > 0 ? '+' : ''}${pctFmt.format(n)} %`;
  }

  function score(value) {
    const n = number(value);
    return n === null ? '–' : fmt.format(n);
  }

  function money(value, currency = 'SEK') {
    const n = number(value);
    return n === null ? '–' : `${fmt.format(n)} ${currency}`;
  }

  function prettyDate(value) {
    if (!value) return '–';
    const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
    return Number.isNaN(date.valueOf()) ? value : dateFmt.format(date);
  }

  function stockMeta(stocksPayload, ticker) {
    return (stocksPayload.stocks || []).find((item) => item.ticker === ticker) || { ticker, name: ticker, currency: 'SEK' };
  }

  function textIncludes(row, needle) {
    return !needle || `${row.ticker} ${row.name}`.toLocaleLowerCase('sv-SE').includes(needle);
  }

  function renderPositions(dashboard, stocksPayload, needle) {
    const rows = Object.entries(dashboard.stocks || {})
      .map(([ticker, data]) => {
        const meta = stockMeta(stocksPayload, ticker);
        return { ticker, name: meta.name || ticker, currency: meta.currency || 'SEK', data };
      })
      .filter((row) => row.data.active_for_updates !== false && Number(row.data.position?.lots || 0) > 0)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => Number(b.data.position?.unrealized_pct || 0) - Number(a.data.position?.unrealized_pct || 0));

    $('summary-count').textContent = String(rows.length);
    $('overview-body').innerHTML = rows.length ? rows.map((row) => {
      const p = row.data.position || {};
      const latest = row.data.latest || {};
      const action = row.data.next_action || {};
      return `<tr>
        <td><a class="stock-link" href="${stockHref(row.ticker)}"><strong>${esc(row.ticker)}</strong><span>${esc(row.name)}</span></a></td>
        <td>Aktiv</td>
        <td>${money(p.avg_entry, row.currency)}</td>
        <td>${money(latest.close, row.currency)}</td>
        <td class="${number(p.unrealized_pct) >= 0 ? 'positive' : 'negative'}">${pct(p.unrealized_pct)}</td>
        <td>${score(latest.score)}</td>
        <td>${latest.fundamental_lock ? action.exit_reason === 'report' ? 'Spärrad · rapportsälj tillåten' : 'Spärrad' : 'Fri'}</td>
        <td>${action.type && action.type !== 'NONE' ? `<span class="status-chip action">${esc(action.label)}</span>${action.execute_on ? `<span class="cell-detail">${prettyDate(action.execute_on)}</span>` : ''}` : row.data.strategy_filter?.report_exit_date ? `Sälj senast ${prettyDate(row.data.strategy_filter.report_exit_date)} inför rapport` : '–'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="empty-cell">Inga aktiva positioner matchar filtret.</td></tr>';
  }

  function signalCandidate(ticker, data, meta, rules) {
    if (data.active_for_updates === false) return null;
    const latest = data.latest || {};
    const position = data.position || {};
    const action = data.next_action || {};
    const value = number(latest.score);
    const filters = data.strategy_filter || {};
    const reportDays = number(filters.trading_days_to_report);
    const plannedReport = Number(position.lots || 0) > 0 && reportDays !== null && reportDays >= 0 && reportDays <= 5 && Boolean(filters.report_exit_date);
    const reportExit = (action.type === 'SELL' && action.exit_reason === 'report') || (plannedReport && action.type !== 'SELL');
    if (value === null && !reportExit) return null;

    const buy = number(rules.buy_score) ?? 1;
    const sell = number(rules.sell_score) ?? 99;
    const lots = Number(position.lots || 0);
    const maxLots = Number(position.max_lots || 1);
    const hasPosition = lots > 0;
    const canBuy = lots < maxLots && data.strategy_filter?.buy_allowed !== false;
    const canSell = hasPosition;
    const actual = (action.type === 'BUY' && canBuy) || (action.type === 'SELL' && canSell);
    const buyDistance = Math.max(0, value - buy);
    const sellDistance = Math.max(0, sell - value);

    let side = null;
    let distance = null;
    if (reportExit && hasPosition) {
      side = 'SELL';
      distance = reportDays ?? 0;
    } else if (actual && ((action.type === 'BUY' && canBuy) || (action.type === 'SELL' && canSell))) {
      side = action.type;
      distance = 0;
    } else if (value !== null && canBuy && buyDistance <= 10) {
      side = 'BUY';
      distance = buyDistance;
    } else if (value !== null && canSell && sellDistance <= 10) {
      side = 'SELL';
      distance = sellDistance;
    } else {
      return null;
    }

    return {
      ticker,
      name: meta.name || ticker,
      score: value,
      latestDate: latest.date,
      side,
      distance,
      actual,
      reportExit,
      reportDays,
      reportDate: filters.next_report_date,
      exitDate: filters.report_exit_date || action.execute_on,
      locked: Boolean(latest.fundamental_lock),
      lots,
      maxLots,
      armed: reportExit || (side === 'BUY' ? position.buy_armed !== false : position.sell_armed !== false),
      reached: actual || (side === 'BUY' ? value < buy : value > sell),
      action
    };
  }

  function boundaryText(row) {
    if (row.reportExit) return 'Rapportsälj';
    const forecast = priceBoundaries[row.ticker];
    const boundary = forecast?.[row.side.toLowerCase()];
    if (!boundary || forecast.as_of !== row.latestDate || forecast.session <= marketDate) return '–';
    return `<strong>${boundary.direction === 'below' ? 'Under' : 'Över'} ≈ ${fmt.format(boundary.price)} kr</strong><span class="cell-detail">Stängning ${prettyDate(forecast.session)}${boundary.multiple_crossings ? ' · Fler intervall finns' : ''}</span>`;
  }

  function renderSignals(dashboard, stocksPayload, needle) {
    const rules = dashboard.meta?.rules || {};
    const upcoming = Object.entries(dashboard.stocks || {})
      .map(([ticker, data]) => signalCandidate(ticker, data, stockMeta(stocksPayload, ticker), rules))
      .filter(Boolean)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => Number(b.actual) - Number(a.actual) || Number(b.reportExit) - Number(a.reportExit) || a.distance - b.distance || a.score - b.score);

    $('upcoming-count').textContent = String(upcoming.length);
    $('upcoming-signals-body').innerHTML = upcoming.length ? upcoming.map((row) => `<tr>
      <td><a class="stock-link" href="${stockHref(row.ticker)}"><strong>${esc(row.ticker)}</strong><span>${esc(row.name)}</span></a></td>
      <td><span class="status-chip ${row.side === 'BUY' ? 'buy' : 'sell'}">${row.side === 'BUY' ? 'Köp' : 'Sälj'}</span></td>
      <td>${score(row.score)}</td>
      <td>${row.reportExit ? `<strong>Inför rapport</strong>${row.reportDays !== null ? `<span class="cell-detail">${row.reportDays} börsdagar till rapport</span>` : ''}` : row.reached ? '<strong>Signalgräns nådd</strong>' : `${fmt.format(row.distance)} p från gräns`}</td>
      <td>${boundaryText(row)}</td>
      <td>${row.lots ? 'Aktiv' : 'Ingen'}</td>
      <td>${row.armed ? 'Ja' : 'Nej'}</td>
      <td>${row.locked ? row.reportExit ? 'Spärrad · rapportsälj tillåten' : 'Spärrad' : 'Fri'}</td>
      <td>${row.reportExit ? `Sälj inför rapport · ${prettyDate(row.exitDate)}${row.reportDate ? `<span class="cell-detail">Rapport ${prettyDate(row.reportDate)}</span>` : ''}` : row.locked ? 'Handel spärrad' : row.actual ? esc(row.action.label) : row.reached ? 'Gräns nådd; inväntar exekverbar signal' : 'Bevaka nästa stängning'}</td>
    </tr>`).join('') : '<tr><td colspan="9" class="empty-cell">Inga aktier ligger nära en signalgräns just nu.</td></tr>';

    const tradingDates = dashboard.meta?.trading_dates || [...new Set(Object.values(dashboard.stocks || {})
      .flatMap((data) => (data.candles || []).map((row) => row.date).filter(Boolean)))].sort();
    const recentCutoff = tradingDates.length > 20 ? tradingDates.at(-20) : tradingDates[0];
    const latestTradingDate = tradingDates.at(-1);
    const recent = Object.entries(dashboard.stocks || {})
      .flatMap(([ticker, data]) => {
        const meta = stockMeta(stocksPayload, ticker);
        return (data.signals || [])
          .filter((row) => row.status === 'executed' && row.execution_date)
          .map((row) => ({
            ...row,
            ticker,
            name: meta.name || ticker,
            currency: meta.currency || 'SEK'
          }));
      })
      .filter((row) => (!recentCutoff || row.execution_date >= recentCutoff)
        && (!latestTradingDate || row.execution_date <= latestTradingDate))
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => b.execution_date.localeCompare(a.execution_date)
        || String(b.signal_date || '').localeCompare(String(a.signal_date || ''))
        || a.ticker.localeCompare(b.ticker, 'sv-SE'));

    $('recent-count').textContent = String(recent.length);
    $('recent-signals-body').innerHTML = recent.length ? recent.map((row) => `<tr>
      <td><a class="stock-link" href="${stockHref(row.ticker)}"><strong>${esc(row.ticker)}</strong><span>${esc(row.name)}</span></a></td>
      <td><span class="status-chip ${row.side === 'BUY' ? 'buy' : 'sell'}">${row.side === 'BUY' ? 'Köp' : 'Sälj'}</span>${row.exit_reason === 'report' ? '<span class="cell-detail">Inför rapport</span>' : ''}</td>
      <td><strong>${prettyDate(row.execution_date)}</strong><span class="cell-detail">Signal ${prettyDate(row.signal_date)}</span></td>
      <td>${money(row.execution_price, row.currency)}</td>
      <td>${score(row.score)}</td>
    </tr>`).join('') : '<tr><td colspan="5" class="empty-cell">Inga exekverade signaler under de senaste 20 handelsdagarna.</td></tr>';

    $('summary-count').textContent = String(upcoming.length + recent.length);
  }

  if (typeof module !== 'undefined') module.exports = {signalCandidate, number};
  if (typeof document === 'undefined') return;

  async function init() {
    try {
      const [stocksPayload, overviews, forecasts] = await Promise.all([
        fetch('./data/stocks.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`stocks.json: HTTP ${r.status}`);
          return r.json();
        }),
        fetch('./data/strategy_overviews.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`strategy_overviews.json: HTTP ${r.status}`);
          return r.json();
        }),
        document.body.dataset.overview === 'signals' ? fetch('./data/signal_prices.json', {cache:'no-store'})
          .then(r => r.ok ? r.json() : {stocks:{}}).catch(() => ({stocks:{}})) : {stocks:{}}
      ]);
      priceBoundaries = forecasts.stocks || {};
      marketDate = overviews.meta?.trading_dates?.at(-1) || null;

      const page = document.body.dataset.overview;
      const params = new URLSearchParams(location.search);
      let saved;
      try { saved = localStorage.getItem('overview-strategy'); } catch {}
      strategy = strategies[params.get('strategy')] ? params.get('strategy') : strategies[saved] ? saved : 'standard';
      $('overview-strategy').value = strategy;
      const render = () => {
        strategy = $('overview-strategy').value;
        const selected = overviews.strategies?.[strategy];
        if (!selected) throw new Error(`Översiktsdata saknas för ${strategies[strategy]}.`);
        const dashboard = {meta:overviews.meta,stocks:selected.stocks};
        const url = new URL(location.href); url.searchParams.set('strategy',strategy); history.replaceState({},'',url);
        window.strategySelection.set(strategy);
        document.querySelectorAll('.page-nav a').forEach(link=>{
          if (!/\/(positions|signals|method)\.html$/.test(new URL(link.href).pathname)) return;
          const target=new URL(link.href); target.searchParams.set('strategy',strategy); link.href=target;
        });
        $('strategy-description').textContent = ({standard:'Köp under 1 och sälj över 99.',ma200:'Köp endast över MA200. Säljregeln är oförändrad.',report_avoidance:'Inga köp inom 10 handelsdagar före rapport. Sälj handelsdagen före rapport.'})[strategy];
        const needle = ($('overview-search')?.value || '').trim().toLocaleLowerCase('sv-SE');
        if (page === 'positions') renderPositions(dashboard, stocksPayload, needle);
        else renderSignals(dashboard, stocksPayload, needle);
      };

      const generated = overviews.meta?.generated_at || stocksPayload.generated_at;
      $('last-updated').textContent = generated ? new Date(generated).toLocaleString('sv-SE') : 'Okänt';
      $('overview-search')?.addEventListener('input', render);
      $('overview-strategy').addEventListener('change', render);
      render();
      $('loading-state').hidden = true;
      $('overview-content').hidden = false;
    } catch (error) {
      console.error(error);
      $('loading-state').hidden = true;
      $('error-state').hidden = false;
      $('error-message').textContent = error.message;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
