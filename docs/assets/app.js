(() => {
  'use strict';

  const PATHS = {
    stocks: './data/stocks.json',
    dashboard: './data/dashboard.json',
    events: './data/events.json'
  };

  const state = {
    stocksPayload: null,
    dashboard: null,
    eventsPayload: null,
    selectedTicker: null,
    range: '125',
    chart: null
  };

  const $ = (id) => document.getElementById(id);
  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const pctFmt = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dateFmt = new Intl.DateTimeFormat('sv-SE', { year: 'numeric', month: 'short', day: 'numeric' });

  function safeNumber(value, fallback = null) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function money(value, currency = 'SEK') {
    const n = safeNumber(value);
    if (n === null) return '–';
    return `${fmt.format(n)} ${currency}`;
  }

  function pct(value) {
    const n = safeNumber(value);
    if (n === null) return '–';
    return `${n > 0 ? '+' : ''}${pctFmt.format(n)} %`;
  }

  function prettyDate(value) {
    if (!value) return '–';
    const d = new Date(value.length === 10 ? `${value}T12:00:00` : value);
    return Number.isNaN(d.valueOf()) ? value : dateFmt.format(d);
  }

  function zoneClass(score) {
    const n = safeNumber(score, 50);
    if (n <= 25) return 'zone-buy';
    if (n >= 75) return 'zone-sell';
    return 'zone-mid';
  }

  function scoreColor(score) {
    const n = safeNumber(score, 50);
    if (n <= 25) return '#1f8f67';
    if (n >= 75) return '#c74747';
    return '#c88722';
  }

  async function loadJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path} gav HTTP ${response.status}`);
    return response.json();
  }

  function setHidden(id, hidden) {
    const el = $(id);
    if (el) el.hidden = hidden;
  }

  function renderRules() {
    const rules = state.dashboard.meta?.rules || {};
    const rows = [
      ['Köp', `Score ${rules.buy_score ?? 0}`],
      ['Sälj', `Score ${rules.sell_score ?? 100}`],
      ['Cooldown', `${rules.cooldown_trading_days ?? 5} handelsdagar`],
      ['Max köp', `${rules.max_buys_per_cycle ?? 2} per cykel`],
      ['Exekvering', rules.execution || 'Nästa öppning']
    ];
    $('rules-list').innerHTML = rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('');
  }

  function renderStockList(filter = '') {
    const needle = filter.trim().toLocaleLowerCase('sv-SE');
    const stocks = (state.stocksPayload?.stocks || []).filter((stock) => {
      return !needle || stock.ticker.toLocaleLowerCase().includes(needle) || stock.name.toLocaleLowerCase('sv-SE').includes(needle);
    });

    $('stock-count').textContent = String(stocks.length);
    $('stock-list').innerHTML = stocks.map((stock) => {
      const active = stock.ticker === state.selectedTicker ? ' active' : '';
      const lock = stock.locked ? ' · spärr' : '';
      return `
        <button type="button" class="stock-button${active}" role="option" aria-selected="${stock.ticker === state.selectedTicker}" data-ticker="${stock.ticker}">
          <div class="row-top"><strong>${stock.ticker}</strong><span class="mini-score">${fmt.format(stock.latest_score)}</span></div>
          <div class="stock-name-small">${stock.name}${lock}</div>
        </button>`;
    }).join('') || '<div class="empty-state">Ingen aktie matchar sökningen.</div>';

    document.querySelectorAll('.stock-button').forEach((button) => {
      button.addEventListener('click', () => selectTicker(button.dataset.ticker));
    });
  }

  function stockMeta(ticker) {
    return (state.stocksPayload?.stocks || []).find((item) => item.ticker === ticker) || {};
  }

  function renderHero(ticker, data) {
    const meta = stockMeta(ticker);
    const latest = data.latest || {};
    $('stock-ticker').textContent = ticker;
    $('stock-name').textContent = meta.name || ticker;
    $('stock-date').textContent = `Stängning ${prettyDate(latest.date)} · ${meta.market || 'Marknad'} · ${meta.currency || 'SEK'}`;
    $('data-badge').textContent = state.dashboard.meta?.is_demo ? 'Exempeldata' : 'Live';
    $('data-badge').className = `badge ${state.dashboard.meta?.is_demo ? 'badge-warning' : 'badge-success'}`;
    $('quality-badge').textContent = meta.data_quality === 'demo' ? 'Syntetisk kvalitet' : 'Verifierad data';
    $('latest-price').textContent = money(latest.close, meta.currency || 'SEK');
    $('price-change').textContent = pct(latest.change_pct);
    $('price-change').className = `change-value ${safeNumber(latest.change_pct, 0) >= 0 ? 'positive' : 'negative'}`;

    const locked = Boolean(latest.fundamental_lock);
    setHidden('lock-badge', !locked);
    setHidden('lock-alert', !locked);
    if (locked) {
      $('lock-badge').textContent = 'HANDELSSPÄRR';
      $('lock-reason').textContent = latest.lock_reason || 'Fundamentaldata väntar på manuell verifiering.';
    }
  }

  function renderMetrics(data) {
    const latest = data.latest || {};
    const position = data.position || {};
    const action = data.next_action || {};

    $('metric-score').textContent = latest.score == null ? '–' : fmt.format(latest.score);
    $('metric-score').style.color = scoreColor(latest.score);
    $('metric-zone').textContent = latest.zone || '–';
    $('metric-zone').className = `zone-pill ${zoneClass(latest.score)}`;
    $('metric-pe').textContent = latest.pe_ttm == null ? '–' : fmt.format(latest.pe_ttm);
    $('metric-eps').textContent = latest.eps_ttm == null ? 'EPS –' : `EPS TTM ${fmt.format(latest.eps_ttm)}`;
    $('metric-position').textContent = `${position.lots || 0} / ${position.max_lots || 2} delposter`;
    $('metric-unrealized').textContent = position.lots ? `Orealiserat ${pct(position.unrealized_pct)}` : 'Ingen aktiv modellposition';
    $('metric-action').textContent = action.label || 'Ingen signal';
    $('metric-action').className = `metric-value metric-action ${action.type === 'BUY' ? 'positive' : action.type === 'SELL' ? 'negative' : ''}`;
    $('metric-action-detail').textContent = action.detail || '–';
  }

  function renderStatus(data) {
    const p = data.position || {};
    const report = data.report || {};
    const repo = state.dashboard.meta?.repository_url || 'https://github.com/jl98swe/Stock_value_algorithm';

    $('position-content').innerHTML = `
      <div class="status-stack">
        <div class="status-line"><span>Aktiva delposter</span><strong>${p.lots || 0} av ${p.max_lots || 2}</strong></div>
        <div class="status-line"><span>Genomsnittligt inköp</span><strong>${p.avg_entry ? money(p.avg_entry) : '–'}</strong></div>
        <div class="status-line"><span>Senaste köp</span><strong>${prettyDate(p.last_buy_date)}</strong></div>
        <div class="status-line"><span>Köp återaktiverat</span><strong>${p.buy_armed ? 'Ja' : 'Nej'}</strong></div>
        <div class="status-line"><span>Sälj återaktiverat</span><strong>${p.sell_armed ? 'Ja' : 'Nej'}</strong></div>
      </div>`;

    $('report-content').innerHTML = `
      <div class="status-stack">
        <div class="status-line"><span>Senaste rapport</span><strong>${report.period || '–'}</strong></div>
        <div class="status-line"><span>EPS TTM</span><strong>${report.eps_ttm == null ? '–' : fmt.format(report.eps_ttm)}</strong></div>
        <div class="status-line"><span>Effektiv handelsdag</span><strong>${prettyDate(report.effective_date)}</strong></div>
        <div class="status-line"><span>Verifierad</span><strong>${report.verified ? 'Ja' : 'Nej'}</strong></div>
        <div class="status-line"><span>Nästa rapport</span><strong>${prettyDate(report.next_report)}</strong></div>
      </div>`;

    $('trade-workflow-link').href = `${repo}/actions`;
    $('report-workflow-link').href = `${repo}/actions`;
    $('review-workflow-link').href = `${repo}/actions`;
  }

  function renderNews(ticker) {
    const events = (state.eventsPayload?.events || []).filter((event) => event.ticker === ticker);
    if (!events.length) {
      $('news-list').innerHTML = '<div class="empty-state">Inga bolagsnyheter i demo-underlaget.</div>';
      return;
    }
    $('news-list').innerHTML = events.map((event) => {
      const locking = Boolean(event.locking);
      const status = event.review_status === 'reviewed' ? 'Granskad' : 'Ogranskad';
      return `
        <article class="news-item">
          <div class="news-item-top">
            <div>
              <h3>${event.title}</h3>
              <div class="news-meta">${prettyDate(event.published_at)} · ${event.source} · ${event.is_regulatory ? 'Regulatorisk' : 'Bolagsnyhet'}</div>
            </div>
            <span class="news-badge ${locking ? 'locking' : ''}">${locking ? 'Spärrar' : status}</span>
          </div>
          <p class="news-summary">${event.summary || ''}</p>
          <a href="./review.html?ticker=${encodeURIComponent(ticker)}&event=${encodeURIComponent(event.event_id)}">Granska nyheten</a>
        </article>`;
    }).join('');
  }

  function renderTables(data) {
    const comparisons = data.strategy_comparison || [];
    $('strategy-table').innerHTML = `
      <thead><tr><th>Strategi</th><th>Avkastning</th><th>Max DD</th><th>Affärer</th><th>Win rate</th></tr></thead>
      <tbody>${comparisons.map((row) => `<tr><td>${row.strategy}</td><td>${pct(row.return_pct)}</td><td>${pct(row.max_drawdown_pct)}</td><td>${row.trades}</td><td>${pct(row.win_rate_pct)}</td></tr>`).join('')}</tbody>`;

    const trades = data.closed_trades || [];
    $('trades-table').innerHTML = `
      <thead><tr><th>In</th><th>Ut</th><th>Inkurs</th><th>Utkurs</th><th>Resultat</th></tr></thead>
      <tbody>${trades.length ? trades.map((row) => `<tr><td>${prettyDate(row.entry_date)}</td><td>${prettyDate(row.exit_date)}</td><td>${fmt.format(row.entry_price)}</td><td>${fmt.format(row.exit_price)}</td><td class="${row.return_pct >= 0 ? 'positive' : 'negative'}">${pct(row.return_pct)}</td></tr>`).join('') : '<tr><td colspan="5">Inga avslut.</td></tr>'}</tbody>`;
  }

  function sliceData(data) {
    const candles = data.candles || [];
    const scores = data.scores || [];
    if (state.range === 'all') return { candles, scores };
    const n = Math.max(1, Number(state.range));
    return { candles: candles.slice(-n), scores: scores.slice(-n) };
  }

  function renderChart(ticker, data) {
    const container = $('market-chart');
    if (!window.echarts) {
      setHidden('chart-message', false);
      $('chart-message').textContent = 'Diagrammotorn ECharts kunde inte laddas. Kontrollera internetanslutningen och ladda om sidan.';
      return;
    }
    setHidden('chart-message', true);
    if (!state.chart) state.chart = echarts.init(container, null, { renderer: 'canvas' });

    const sliced = sliceData(data);
    const dates = sliced.candles.map((d) => d.date);
    const candleValues = sliced.candles.map((d) => [d.open, d.close, d.low, d.high]);
    const scoreMap = new Map(sliced.scores.map((d) => [d.date, d.value]));
    const scores = dates.map((d) => scoreMap.get(d) ?? null);
    const startDate = dates[0];
    const endDate = dates[dates.length - 1];

    const events = (state.eventsPayload?.events || []).filter((event) => event.ticker === ticker && event.published_at.slice(0, 10) >= startDate && event.published_at.slice(0, 10) <= endDate);
    const signals = (data.signals || []).filter((signal) => signal.date >= startDate && signal.date <= endDate);

    const signalPoints = signals.map((signal) => {
      const candle = sliced.candles.find((d) => d.date === signal.date);
      if (!candle) return null;
      const buy = signal.side === 'BUY';
      return {
        name: `${signal.side} ${signal.status}`,
        coord: [signal.date, buy ? candle.low * 0.985 : candle.high * 1.015],
        symbol: buy ? 'triangle' : 'triangle',
        symbolRotate: buy ? 0 : 180,
        symbolSize: 13,
        itemStyle: { color: signal.status.includes('blocked') ? '#c88722' : buy ? '#1f8f67' : '#c74747' },
        label: { show: false }
      };
    }).filter(Boolean);

    const eventPoints = events.map((event) => {
      const day = event.published_at.slice(0, 10);
      const candle = sliced.candles.find((d) => d.date === day);
      if (!candle) return null;
      return {
        name: event.title,
        coord: [day, candle.high * 1.03],
        symbol: 'pin',
        symbolSize: 18,
        itemStyle: { color: event.locking ? '#c88722' : '#2f6fb0' },
        label: { show: false }
      };
    }).filter(Boolean);

    const option = {
      animation: false,
      backgroundColor: '#ffffff',
      axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: '#40515b' } },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        borderWidth: 1,
        borderColor: '#dfe6ea',
        backgroundColor: 'rgba(255,255,255,.97)',
        textStyle: { color: '#17212b', fontSize: 11 },
        formatter(params) {
          if (!params?.length) return '';
          const date = params[0].axisValue;
          const candle = sliced.candles.find((d) => d.date === date);
          const score = scoreMap.get(date);
          if (!candle) return date;
          return `<strong>${date}</strong><br>Ö ${fmt.format(candle.open)} · H ${fmt.format(candle.high)} · L ${fmt.format(candle.low)} · S ${fmt.format(candle.close)}<br>Score <strong>${score == null ? '–' : fmt.format(score)}</strong>`;
        }
      },
      grid: [
        { left: 58, right: 22, top: 24, height: '58%' },
        { left: 58, right: 22, top: '70%', height: '21%' }
      ],
      xAxis: [
        { type: 'category', data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#dfe6ea' } }, axisLabel: { show: false }, axisTick: { show: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' },
        { type: 'category', gridIndex: 1, data: dates, boundaryGap: true, axisLine: { lineStyle: { color: '#dfe6ea' } }, axisLabel: { color: '#687684', fontSize: 10, hideOverlap: true }, axisTick: { show: false }, splitLine: { show: false }, min: 'dataMin', max: 'dataMax' }
      ],
      yAxis: [
        { scale: true, position: 'right', axisLabel: { color: '#687684', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf1f3' } }, axisLine: { show: false }, axisTick: { show: false } },
        { gridIndex: 1, min: 0, max: 100, interval: 25, position: 'right', axisLabel: { color: '#687684', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf1f3' } }, axisLine: { show: false }, axisTick: { show: false } }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100, zoomOnMouseWheel: 'shift', moveOnMouseMove: true },
        { type: 'slider', xAxisIndex: [0, 1], bottom: 2, height: 18, borderColor: '#dfe6ea', backgroundColor: '#f6f8f9', fillerColor: 'rgba(15,89,103,.12)', handleStyle: { color: '#0f5967' }, textStyle: { color: '#687684', fontSize: 9 } }
      ],
      series: [
        {
          name: 'Pris', type: 'candlestick', data: candleValues,
          itemStyle: { color: '#20a486', color0: '#e65b5b', borderColor: '#20a486', borderColor0: '#e65b5b' },
          markPoint: { data: [...signalPoints, ...eventPoints], tooltip: { show: false } }
        },
        {
          name: 'Score', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: scores, symbol: 'none', smooth: false, lineStyle: { width: 2.5, color: '#2f6fb0' },
          areaStyle: { color: 'rgba(47,111,176,.05)' },
          markArea: { silent: true, data: [[{ yAxis: 0, itemStyle: { color: 'rgba(31,143,103,.10)' } }, { yAxis: 25 }], [{ yAxis: 75, itemStyle: { color: 'rgba(199,71,71,.10)' } }, { yAxis: 100 }]] },
          markLine: { silent: true, symbol: ['none','none'], label: { show: true, position: 'insideEndTop', fontSize: 9 }, lineStyle: { type: 'dashed', width: 1 }, data: [{ yAxis: 0, name: 'Köp 0', lineStyle: { color: '#1f8f67' } }, { yAxis: 100, name: 'Sälj 100', lineStyle: { color: '#c74747' } }] }
        }
      ]
    };
    state.chart.setOption(option, true);
  }

  function selectTicker(ticker) {
    if (!state.dashboard.stocks?.[ticker]) return;
    state.selectedTicker = ticker;
    const url = new URL(window.location.href);
    url.searchParams.set('ticker', ticker);
    window.history.replaceState({}, '', url);
    renderStockList($('stock-search').value);
    renderSelected();
  }

  function renderSelected() {
    const ticker = state.selectedTicker;
    const data = state.dashboard.stocks[ticker];
    renderHero(ticker, data);
    renderMetrics(data);
    renderStatus(data);
    renderNews(ticker);
    renderTables(data);
    renderChart(ticker, data);
  }

  function bindControls() {
    $('stock-search').addEventListener('input', (event) => renderStockList(event.target.value));
    document.querySelectorAll('[data-range]').forEach((button) => {
      button.addEventListener('click', () => {
        state.range = button.dataset.range;
        document.querySelectorAll('[data-range]').forEach((b) => b.classList.toggle('active', b === button));
        renderChart(state.selectedTicker, state.dashboard.stocks[state.selectedTicker]);
      });
    });
    const defaultRange = document.querySelector('[data-range="125"]');
    if (defaultRange) defaultRange.classList.add('active');
    window.addEventListener('resize', () => state.chart?.resize());
  }

  async function init() {
    try {
      const [stocksPayload, dashboard, eventsPayload] = await Promise.all([
        loadJson(PATHS.stocks), loadJson(PATHS.dashboard), loadJson(PATHS.events)
      ]);
      state.stocksPayload = stocksPayload;
      state.dashboard = dashboard;
      state.eventsPayload = eventsPayload;

      const generatedAt = dashboard.meta?.generated_at || stocksPayload.generated_at;
      $('last-updated').textContent = generatedAt ? new Date(generatedAt).toLocaleString('sv-SE') : 'Okänt';
      setHidden('demo-banner', !Boolean(dashboard.meta?.is_demo));
      renderRules();
      bindControls();

      const requested = new URLSearchParams(window.location.search).get('ticker');
      const firstTicker = stocksPayload.stocks?.[0]?.ticker;
      state.selectedTicker = dashboard.stocks?.[requested] ? requested : firstTicker;
      if (!state.selectedTicker) throw new Error('stocks.json innehåller inga aktier.');

      setHidden('loading-state', true);
      setHidden('dashboard-content', false);
      renderStockList();
      renderSelected();
    } catch (error) {
      console.error(error);
      setHidden('loading-state', true);
      setHidden('dashboard-content', true);
      setHidden('error-state', false);
      $('error-message').textContent = `${error.message}. Kontrollera att docs/data/*.json finns och att GitHub Pages publicerar mappen /docs.`;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
