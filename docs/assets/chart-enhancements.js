(() => {
  'use strict';

  let dashboard = null;
  let eventsPayload = null;
  let refreshTimer = null;

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

  function eventDay(event) {
    return String(event.event_date || event.ex_date || event.published_at || '').slice(0, 10);
  }

  function selectedTicker() {
    return new URLSearchParams(window.location.search).get('ticker') || Object.keys(dashboard?.stocks || {})[0] || null;
  }

  function selectedRange() {
    const active = document.querySelector('[data-range].active');
    return active?.dataset.range || '125';
  }

  function sliceCandles(candles) {
    const range = selectedRange();
    if (range === 'all') return candles;
    return candles.slice(-Math.max(1, Number(range)));
  }

  function scheduleRefresh() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(applyEnhancements, 60);
  }

  function applyEnhancements() {
    ensureLegend();
    if (!dashboard || !eventsPayload || !window.echarts) return;

    const chartEl = document.getElementById('market-chart');
    const chart = chartEl ? echarts.getInstanceByDom(chartEl) : null;
    if (!chart) return;

    const ticker = selectedTicker();
    const stock = dashboard.stocks?.[ticker];
    if (!stock) return;

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
    const existingPoints = markPoint?.data || [];
    const signalPoints = existingPoints.filter((point) => /^(BUY|SELL)\b/.test(String(point.name || '')));

    const visibleEvents = (eventsPayload.events || []).filter((event) => {
      const day = eventDay(event);
      return event.ticker === ticker && day >= startDate && day <= endDate;
    });

    const countByDay = new Map();
    const eventPoints = visibleEvents.map((event) => {
      const day = eventDay(event);
      const candle = candles.find((d) => d.date === day);
      if (!candle) return null;
      const marker = eventMarker(event);
      const stackIndex = countByDay.get(day) || 0;
      countByDay.set(day, stackIndex + 1);
      const source = event.source ? ` · ${event.source}` : '';
      return {
        name: `${marker.code} · ${event.title}`,
        coord: [day, candle.high * 1.03],
        symbol: 'circle',
        symbolSize: 22,
        symbolOffset: [0, -stackIndex * 24],
        itemStyle: {
          color: marker.color,
          borderColor: event.locking ? '#c88722' : '#ffffff',
          borderWidth: event.locking ? 2.5 : 1.5
        },
        label: { show: true, formatter: marker.code, color: '#ffffff', fontSize: 10, fontWeight: 900 },
        eventTooltip: `<strong>${marker.code} · ${marker.label}</strong><br>${day}${source}<br>${event.title}`
      };
    }).filter(Boolean);

    const updatedSeries = series.filter((item) => item.name !== 'MA200').map((item) => ({ ...item }));
    const priceIndex = Math.max(0, updatedSeries.findIndex((item) => item.name === 'Pris'));
    updatedSeries[priceIndex] = {
      ...updatedSeries[priceIndex],
      markPoint: {
        ...(markPoint || {}),
        data: [...signalPoints, ...eventPoints],
        tooltip: {
          show: true,
          trigger: 'item',
          formatter(params) {
            return params.data?.eventTooltip || params.name || '';
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

    chart.setOption({ series: updatedSeries }, { replaceMerge: ['series'] });
  }

  async function init() {
    ensureLegend();
    try {
      [dashboard, eventsPayload] = await Promise.all([
        fetch('./data/dashboard.json', { cache: 'no-store' }).then((r) => r.json()),
        fetch('./data/events.json', { cache: 'no-store' }).then((r) => r.json())
      ]);
      scheduleRefresh();
      document.addEventListener('click', (event) => {
        if (event.target.closest('[data-range]') || event.target.closest('.stock-button')) scheduleRefresh();
      });
      window.addEventListener('popstate', scheduleRefresh);
      window.addEventListener('resize', scheduleRefresh);
    } catch (error) {
      console.warn('Kunde inte aktivera MA200/E/D/N-förbättringar:', error);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
