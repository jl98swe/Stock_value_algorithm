(() => {
  'use strict';

  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  let dashboard = null;
  let eventsPayload = null;
  let refreshTimer = null;

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
    const n = Math.max(1, Number(range));
    return candles.slice(-n);
  }

  function scheduleRefresh() {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(applyEnhancements, 40);
  }

  function applyEnhancements() {
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
    const priceSeries = current.series?.[0] || {};
    const existingPoints = priceSeries.markPoint?.[0]?.data || priceSeries.markPoint?.data || [];
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
        label: {
          show: true,
          formatter: marker.code,
          color: '#ffffff',
          fontSize: 10,
          fontWeight: 900
        },
        eventTooltip: `<strong>${marker.code} · ${marker.label}</strong><br>${day}${source}<br>${event.title}`
      };
    }).filter(Boolean);

    const series = current.series || [];
    const withoutMa = series.filter((item) => item.name !== 'MA200');
    const maSeries = {
      name: 'MA200',
      type: 'line',
      data: ma200,
      symbol: 'none',
      smooth: false,
      connectNulls: false,
      lineStyle: { width: 1.8, color: '#626d78' },
      emphasis: { disabled: true },
      z: 4
    };

    if (withoutMa[0]) {
      withoutMa[0] = {
        ...withoutMa[0],
        markPoint: {
          ...(withoutMa[0].markPoint || {}),
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
    }

    withoutMa.splice(1, 0, maSeries);
    chart.setOption({ series: withoutMa }, { replaceMerge: ['series'] });

    chart.off('showTip', showMaTooltip);
    chart.on('showTip', showMaTooltip);
  }

  function showMaTooltip(params) {
    if (!dashboard || params?.dataIndex == null) return;
    const ticker = selectedTicker();
    const stock = dashboard.stocks?.[ticker];
    if (!stock) return;
    const candles = sliceCandles(stock.candles || []);
    const candle = candles[params.dataIndex];
    const ma = Number(candle?.ma200);
    const el = document.querySelector('.echarts-tooltip');
    if (!el || !Number.isFinite(ma) || el.textContent.includes('MA200')) return;
    el.insertAdjacentHTML('beforeend', `<br>MA200 <strong>${fmt.format(ma)}</strong>`);
  }

  async function init() {
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
    } catch (error) {
      console.warn('Kunde inte aktivera MA200/E/D/N-förbättringar:', error);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
