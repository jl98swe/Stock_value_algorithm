(() => {
  'use strict';

  let dashboard = null;
  let eventsPayload = null;
  let refreshTimer = null;
  const expandedDividends = new Set();
  const expandedNews = new Set();

  function esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  }

  function prettyDate(value) {
    if (!value) return '–';
    const date = new Date(String(value).length === 10 ? `${value}T12:00:00` : value);
    return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('sv-SE', { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
  }

  function ensureNavigation() {
    const actions = document.querySelector('.header-actions');
    if (!actions || document.getElementById('portfolio-nav')) return;
    const nav = document.createElement('nav');
    nav.id = 'portfolio-nav';
    nav.className = 'page-nav';
    nav.setAttribute('aria-label', 'Huvudnavigation');
    nav.innerHTML = `
      <a class="secondary-button active" href="./index.html?v=20260910-1" aria-current="page">Startsida</a>
      <a class="secondary-button" href="./positions.html?v=20260910-1">Aktiva positioner</a>
      <a class="secondary-button" href="./signals.html?v=20260910-1">Kommande signaler</a>
      <a class="secondary-button" href="./reports.html">Rapporter</a>
      <a class="secondary-button" href="./review.html?v=20260910-1">Granska nyheter och data</a>
      <a class="secondary-button" href="./method.html?v=20261006-1">Metod &amp; backtest</a>`;
    actions.insertBefore(nav, actions.firstChild);
  }

  function ensureLegend() {
    const legend = document.querySelector('.chart-legend');
    if (!legend) return;
    legend.innerHTML = `
      <span><i class="legend-swatch legend-buy"></i>Köpsignal</span>
      <span><i class="legend-swatch legend-sell"></i>Säljsignal</span>
      <span><i class="legend-swatch legend-lock"></i>Fundamental spärr</span>
      <span><i class="ma200-key"></i>MA200</span>
      <span><i class="event-key report">E</i>Rapport</span>
      <span><i class="event-key dividend">D</i>Utdelning</span>
      <span><i class="event-key news">N</i>Nyhet</span>`;

    if (!document.getElementById('chart-enhancement-styles')) {
      const style = document.createElement('style');
      style.id = 'chart-enhancement-styles';
      style.textContent = `
        .chart-legend > span { display:inline-flex; align-items:center; }
        .ma200-key { width:18px; height:0; margin-right:6px; border-top:2px solid #626d78; }
        .event-key { display:inline-grid; place-items:center; width:18px; height:18px; margin-right:5px; border-radius:50%; color:#fff; font-size:10px; font-style:normal; font-weight:900; line-height:1; }
        .event-key.report { background:#7b61a8; }
        .event-key.dividend { background:#0b7b72; }
        .event-key.news { background:#2f6fb0; }
        .dividend-history-list { display:grid; gap:0; }
        .dividend-history-row { display:flex; justify-content:space-between; gap:18px; align-items:center; padding:10px 0; border-bottom:1px solid #e7ecef; }
        .dividend-history-row:last-child { border-bottom:0; }
        .dividend-history-row strong { font-size:13px; }
        .dividend-history-row span { color:#66727a; font-size:12px; white-space:nowrap; }
      `;
      document.head.appendChild(style);
    }
  }

  function eventMarker(event) {
    const classification = String(event.classification || '').toLocaleLowerCase('sv-SE');
    const explicitType = String(event.event_type || event.type || '').toLocaleLowerCase('sv-SE');
    const categories = Array.isArray(event.categories)
      ? event.categories.map((value) => String(value).toLocaleLowerCase('sv-SE'))
      : [];
    const tokens = [classification, explicitType, ...categories].join(' ');

    if (tokens.includes('report') || tokens.includes('earnings')) {
      return { code: 'E', label: 'Rapport', color: '#7b61a8' };
    }
    if (tokens.includes('dividend') || tokens.includes('utdelning')) {
      return { code: 'D', label: 'Utdelning', color: '#0b7b72' };
    }
    return { code: 'N', label: 'Nyhet', color: '#2f6fb0' };
  }

  function reportDisplayTitle(event) {
    const source = String(event.source || '').trim();
    let sourceLabel = source.split('/')[0].trim();
    if (/yahoo/i.test(source)) sourceLabel = 'YAHOO';
    if (/tradingview/i.test(source)) sourceLabel = 'TRADINGVIEW';
    return ['Rapport', sourceLabel, eventDay(event)].filter(Boolean).join(' ');
  }

  function reportSourcePriority(event) {
    const source = String(event.source || '').trim();
    if (/yahoo/i.test(source)) return 0;
    return source ? 2 : 1;
  }

  function eventDay(event) {
    return String(event.event_date || event.ex_date || event.published_at || '').slice(0, 10);
  }

  function selectedTicker() {
    return new URLSearchParams(window.location.search).get('ticker') || document.getElementById('stock-ticker')?.textContent?.trim() || Object.keys(dashboard?.stocks || {})[0] || null;
  }

  function selectedRange() {
    const active = document.querySelector('[data-range].active');
    return active?.dataset.range || '3m';
  }

  function sliceCandles(candles) {
    const range = selectedRange();
    if (range === 'all' || !candles.length) return candles;
    const last = new Date(`${candles.at(-1).date}T12:00:00Z`);
    const cutoff = new Date(last);
    if (range === 'ytd') cutoff.setUTCFullYear(last.getUTCFullYear(), 0, 1);
    else cutoff.setUTCMonth(cutoff.getUTCMonth() - ({ '3m': 3, '6m': 6, '1y': 12, '3y': 36, '5y': 60 }[range] || 3));
    return candles.filter((row) => row.date >= cutoff.toISOString().slice(0, 10));
  }

  const markerEnabled = (name) => document.querySelector(`[data-marker="${name}"]`)?.checked !== false;
  const epsText = (value) => value == null ? '–' : new Intl.NumberFormat('sv-SE', { useGrouping: false, maximumFractionDigits: 20 }).format(Number(value));

  function ensureDividendPanel() {
    let panel = document.getElementById('dividend-history-panel');
    if (panel) return panel;
    const newsSection = document.getElementById('news-title')?.closest('section.panel');
    if (!newsSection) return null;

    panel = document.createElement('section');
    panel.id = 'dividend-history-panel';
    panel.className = 'panel';
    panel.setAttribute('aria-labelledby', 'dividend-history-title');
    panel.innerHTML = `
      <div class="panel-header">
        <div>
          <span class="eyebrow">Historik</span>
          <h2 id="dividend-history-title">Utdelningar</h2>
          <p class="panel-description">Verifierade kontantutdelningar. D-markörerna ligger kvar i prisgrafen.</p>
        </div>
      </div>
      <div id="dividend-history-list" class="dividend-history-list"></div>
      <div class="show-more-row">
        <button id="dividend-toggle" class="secondary-button" type="button" aria-expanded="false" hidden>Visa mer</button>
      </div>`;
    newsSection.insertAdjacentElement('beforebegin', panel);
    return panel;
  }

  function renderSeparatedEvents(ticker) {
    if (!eventsPayload) return;
    const tickerEvents = (eventsPayload.events || []).filter((event) => event.ticker === ticker);
    const news = tickerEvents
      .filter((event) => eventMarker(event).code === 'N')
      .sort((a, b) => eventDay(b).localeCompare(eventDay(a)));
    const dividends = tickerEvents
      .filter((event) => eventMarker(event).code === 'D')
      .sort((a, b) => eventDay(b).localeCompare(eventDay(a)));

    const newsList = document.getElementById('news-list');
    if (newsList) {
      const expanded = expandedNews.has(ticker);
      const visibleNews = expanded ? news : news.slice(0, 4);
      newsList.innerHTML = news.length ? visibleNews.map((event) => {
        const locking = Boolean(event.locking);
        const status = event.review_status === 'reviewed' ? 'Granskad' : 'Ogranskad';
        const meta = [prettyDate(event.published_at), event.source, event.is_regulatory ? 'Regulatorisk' : 'Bolagsnyhet'].filter(Boolean).map(esc).join(' · ');
        return `
          <article class="news-item">
            <div class="news-item-top">
              <div>
                <h3>${esc(event.title)}</h3>
                <div class="news-meta">${meta}</div>
              </div>
              <span class="news-badge ${locking ? 'locking' : ''}">${locking ? 'Spärrar' : status}</span>
            </div>
            <p class="news-summary">${esc(event.summary || '')}</p>
            <a href="./review.html?ticker=${encodeURIComponent(ticker)}&event=${encodeURIComponent(event.event_id)}">Granska nyheten</a>
          </article>`;
      }).join('') : '<div class="empty-state">Inga bolagsnyheter för aktien.</div>';
      const newsToggle = document.getElementById('news-toggle');
      if (newsToggle) {
        newsToggle.hidden = news.length <= 4;
        newsToggle.textContent = expanded ? 'Visa mindre' : 'Visa mer';
        newsToggle.setAttribute('aria-expanded', String(expanded));
      }
    }

    ensureDividendPanel();
    const dividendList = document.getElementById('dividend-history-list');
    if (dividendList) {
      const expanded = expandedDividends.has(ticker);
      const visibleDividends = expanded ? dividends : dividends.slice(0, 4);
      dividendList.innerHTML = dividends.length
        ? visibleDividends.map((event) => `
            <div class="dividend-history-row">
              <strong>${esc(event.title || 'Utdelning')}</strong>
              <span>${esc(prettyDate(eventDay(event)))}</span>
            </div>`).join('')
        : '<div class="empty-state">Ingen registrerad utdelningshistorik för aktien.</div>';
      const dividendToggle = document.getElementById('dividend-toggle');
      if (dividendToggle) {
        dividendToggle.hidden = dividends.length <= 4;
        dividendToggle.textContent = expanded ? 'Visa mindre' : 'Visa mer';
        dividendToggle.setAttribute('aria-expanded', String(expanded));
      }
    }
  }

  function scheduleRefresh() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(applyEnhancements, 60);
  }

  function applyEnhancements() {
    ensureNavigation();
    ensureLegend();
    if (!dashboard || !eventsPayload) return;

    const ticker = selectedTicker();
    const stock = dashboard.stocks?.[ticker];
    if (!stock) return;
    renderSeparatedEvents(ticker);

    if (!window.echarts) return;
    const chartEl = document.getElementById('market-chart');
    const chart = chartEl ? echarts.getInstanceByDom(chartEl) : null;
    if (!chart) return;

    const candles = sliceCandles(stock.candles || []);
    if (!candles.length) return;

    const dates = candles.map((d) => d.date);
    const startDate = dates[0];
    const endDate = dates[dates.length - 1];
    const ma200 = candles.map((d) => Number.isFinite(Number(d.ma200)) ? Number(d.ma200) : null);

    const current = chart.getOption();
    const series = current.series || [];
    const priceSeries = series.find((item) => item.name === 'Pris') || series[0] || {};
    const markPoint = Array.isArray(priceSeries.markPoint) ? priceSeries.markPoint[0] : priceSeries.markPoint;
    const signalPoints = markerEnabled('signals') ? (stock.signals || [])
      .filter((signal) => signal.status === 'executed' && signal.execution_date >= startDate && signal.execution_date <= endDate)
      .map((signal) => {
        const candle = candles.find((row) => row.date === signal.execution_date);
        if (!candle) return null;
        const buy = signal.side === 'BUY';
        return {
          name: buy ? 'Köp' : 'Sälj',
          coord: [signal.execution_date, Number(buy ? candle.low : candle.high)],
          symbolOffset: [0, buy ? 16 : -16],
          symbol: 'triangle', symbolRotate: buy ? 0 : 180, symbolSize: 18,
          itemStyle: { color: buy ? '#1f8f67' : '#c74747', borderColor: '#fff', borderWidth: 1 },
          label: { show: false },
          signalTooltip: `<strong>${buy ? 'Köp' : 'Sälj'}</strong><br>${esc(signal.execution_date)} · ${esc(signal.execution_price)}`
        };
      }).filter(Boolean) : [];

    const visibleEvents = (eventsPayload.events || []).filter((event) => {
      const day = eventDay(event);
      return event.ticker === ticker && day >= startDate && day <= endDate;
    });

    // Flera källor kan beskriva samma rapport på samma publiceringsdag.
    // Visa en E-markör och prioritera en namngiven icke-Yahoo-källa.
    const reportByDay = new Map();
    visibleEvents.forEach((event) => {
      if (eventMarker(event).code !== 'E') return;
      const day = eventDay(event);
      const previous = reportByDay.get(day);
      const preferCurrent = !previous || reportSourcePriority(event) > reportSourcePriority(previous);
      if (preferCurrent) reportByDay.set(day, event);
    });
    const deduplicatedEvents = visibleEvents.filter((event) => {
      const marker = eventMarker(event);
      const group = marker.code === 'E' ? 'report' : marker.code === 'D' ? 'dividend' : 'news';
      return markerEnabled(group) && (marker.code !== 'E' || reportByDay.get(eventDay(event)) === event);
    });

    // One fixed row for every event type, independent of the enabled controls.
    const eventPoints = deduplicatedEvents.map((event) => {
      const day = eventDay(event);
      const candle = candles.find((d) => d.date === day);
      if (!candle) return null;
      const marker = eventMarker(event);
      const source = event.source ? ` · ${event.source}` : '';
      const title = marker.code === 'E' ? reportDisplayTitle(event) : String(event.title || marker.label);
      return {
        id: `${day}|${marker.code}`,
        name: `${marker.code} · ${title}`,
        value: [day, 1],
        symbol: 'circle',
        symbolSize: 18,
        itemStyle: {
          color: marker.color,
          borderColor: event.locking ? '#c88722' : '#ffffff',
          borderWidth: event.locking ? 2.5 : 1.5
        },
        label: { show: true, formatter: marker.code, color: '#ffffff', fontSize: 10, fontWeight: 900 },
        eventTooltip: marker.code === 'E'
          ? `<strong>${esc(title)}</strong><br>EPS TTM: ${esc(epsText(event.eps_ttm))}${event.eps_currency ? ` ${esc(event.eps_currency)}` : ''}`
          : `<strong>${marker.code} · ${marker.label}</strong><br>${esc(day)}${esc(source)}<br>${esc(title)}`
      };
    }).filter(Boolean);

    // Multiple same-type events on one day share a marker, with all details
    // preserved in its tooltip rather than stacking into the price chart.
    const groupedPoints = new Map();
    eventPoints.forEach((point) => {
      const key = point.id;
      const previous = groupedPoints.get(key);
      if (!previous) groupedPoints.set(key, point);
      else {
        previous.eventTooltip += `<br><br>${point.eventTooltip}`;
        if (point.itemStyle.borderWidth > previous.itemStyle.borderWidth) previous.itemStyle = point.itemStyle;
      }
    });

    const updatedSeries = series.filter((item) => !['MA200', 'Händelser'].includes(item.name)).map((item) => ({ ...item }));
    const priceIndex = Math.max(0, updatedSeries.findIndex((item) => item.name === 'Pris'));
    updatedSeries[priceIndex] = {
      ...updatedSeries[priceIndex],
      markPoint: {
        ...(markPoint || {}),
        data: signalPoints,
        tooltip: {
          show: true,
          trigger: 'item',
          formatter(params) {
            return params.data?.signalTooltip || params.data?.eventTooltip || params.name || '';
          }
        }
      }
    };

    updatedSeries.splice(priceIndex + 1, 0, {
      name: 'MA200',
      type: 'line',
      data: ma200,
      symbol: 'none',
      smooth: false,
      connectNulls: false,
      lineStyle: { width: 1.8, color: '#626d78' },
      emphasis: { disabled: true },
      z: 4
    });

    updatedSeries.push({
      id: 'chart-events', name: 'Händelser', type: 'scatter', xAxisIndex: 2, yAxisIndex: 2,
      animation: false,
      data: [...groupedPoints.values()],
      symbol: 'circle', symbolSize: 18,
      itemStyle: { opacity: 1 },
      tooltip: { show: true, trigger: 'item', formatter: (params) => params.data?.eventTooltip || params.name || '' },
      z: 5
    });

    chart.setOption({ series: updatedSeries }, { replaceMerge: ['series'] });
  }

  // The base chart may finish loading after DOMContentLoaded or after a slow
  // stock request. Apply the same markers synchronously after every render.
  document.addEventListener('market-chart-rendered', (event) => {
    const { ticker, stock, eventsPayload: payload } = event.detail;
    dashboard = { stocks: { [ticker]: stock } };
    eventsPayload = payload;
    applyEnhancements();
  });

  function init() {
    ensureNavigation();
    ensureLegend();
    document.addEventListener('click', (event) => {
      const ticker = selectedTicker();
      if (event.target.closest('#news-toggle')) {
        const expanded = event.target.closest('#news-toggle').getAttribute('aria-expanded') === 'true';
        expanded ? expandedNews.add(ticker) : expandedNews.delete(ticker);
        renderSeparatedEvents(ticker);
        return;
      }
      if (event.target.closest('#dividend-toggle')) {
        expandedDividends.has(ticker) ? expandedDividends.delete(ticker) : expandedDividends.add(ticker);
        renderSeparatedEvents(ticker);
      }
    });
    document.querySelectorAll('[data-marker]').forEach((input) => input.addEventListener('change', applyEnhancements));
    window.addEventListener('popstate', scheduleRefresh);
    window.addEventListener('resize', scheduleRefresh);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
