(() => {
  'use strict';

  const fmt = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const pctFmt = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const $ = (id) => document.getElementById(id);

  function number(value) {
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

  function stockMeta(stocksPayload, ticker) {
    return (stocksPayload.stocks || []).find((item) => item.ticker === ticker) || {
      ticker,
      name: ticker,
      currency: 'SEK'
    };
  }

  function textIncludes(row, needle) {
    return !needle || `${row.ticker} ${row.name}`.toLocaleLowerCase('sv-SE').includes(needle);
  }

  function setSummary(entries) {
    entries.forEach(([id, value]) => {
      const el = $(id);
      if (el) el.textContent = String(value);
    });
  }

  function renderPositions(dashboard, stocksPayload, needle) {
    const rows = Object.entries(dashboard.stocks || {})
      .map(([ticker, data]) => {
        const meta = stockMeta(stocksPayload, ticker);
        return {
          ticker,
          name: meta.name || ticker,
          currency: meta.currency || 'SEK',
          data
        };
      })
      .filter((row) => Number(row.data.position?.lots || 0) > 0)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => {
        const aAction = a.data.next_action?.type && a.data.next_action.type !== 'NONE' ? 1 : 0;
        const bAction = b.data.next_action?.type && b.data.next_action.type !== 'NONE' ? 1 : 0;
        return bAction - aAction || a.ticker.localeCompare(b.ticker, 'sv');
      });

    const allPositions = Object.values(dashboard.stocks || {})
      .filter((data) => Number(data.position?.lots || 0) > 0);
    const locked = allPositions.filter((data) => Boolean(data.latest?.fundamental_lock)).length;
    const pending = allPositions.filter((data) => {
      const type = data.next_action?.type;
      return type === 'BUY' || type === 'SELL';
    }).length;

    setSummary([
      ['summary-count', rows.length],
      ['summary-total', allPositions.length],
      ['summary-pending', pending],
      ['summary-locked', locked]
    ]);

    $('overview-body').innerHTML = rows.length ? rows.map((row) => {
      const p = row.data.position || {};
      const latest = row.data.latest || {};
      const action = row.data.next_action || {};
      const unrealized = number(p.unrealized_pct);
      const unrealizedClass = unrealized === null ? '' : unrealized >= 0 ? 'positive' : 'negative';
      return `<tr>
        <td><a class="stock-link" href="./index.html?ticker=${encodeURIComponent(row.ticker)}"><strong>${row.ticker}</strong><span>${row.name}</span></a></td>
        <td>${p.lots || 0} / ${p.max_lots || 2}</td>
        <td>${money(p.avg_entry, row.currency)}</td>
        <td>${money(latest.close, row.currency)}</td>
        <td class="${unrealizedClass}">${pct(p.unrealized_pct)}</td>
        <td>${score(latest.score)}</td>
        <td>${latest.fundamental_lock ? '<span class="status-chip warning">Spärr</span>' : '<span class="status-chip ok">Fri</span>'}</td>
        <td>${action.type && action.type !== 'NONE' ? `<span class="status-chip action">${action.label}</span>` : '–'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="empty-cell">Inga aktiva positioner matchar filtret.</td></tr>';
  }

  function candidateForStock(ticker, data, meta, rules) {
    const latest = data.latest || {};
    const position = data.position || {};
    const action = data.next_action || {};
    const value = number(latest.score);
    if (value === null) return null;

    const buyThreshold = number(rules.buy_score) ?? 0;
    const sellThreshold = number(rules.sell_score) ?? 100;
    const lots = Number(position.lots || 0);
    const maxLots = Number(position.max_lots || 2);
    const actual = action.type === 'BUY' || action.type === 'SELL';
    const locked = Boolean(latest.fundamental_lock);

    if (actual) {
      return {
        ticker,
        name: meta.name || ticker,
        score: value,
        side: action.type,
        distance: 0,
        actual: true,
        locked,
        lots,
        maxLots,
        armed: true,
        action
      };
    }

    const options = [];
    if (lots < maxLots && position.buy_armed !== false) {
      options.push({ side: 'BUY', distance: Math.abs(value - buyThreshold), armed: true });
    }
    if (lots > 0 && position.sell_armed !== false) {
      options.push({ side: 'SELL', distance: Math.abs(sellThreshold - value), armed: true });
    }
    if (!options.length) return null;

    options.sort((a, b) => a.distance - b.distance || (a.side === 'BUY' ? -1 : 1));
    const nearest = options[0];
    return {
      ticker,
      name: meta.name || ticker,
      score: value,
      side: nearest.side,
      distance: nearest.distance,
      actual: false,
      locked,
      lots,
      maxLots,
      armed: nearest.armed,
      action
    };
  }

  function renderSignals(dashboard, stocksPayload, needle) {
    const rules = dashboard.meta?.rules || {};
    const rawWindow = $('signal-window')?.value || '5';
    const maxDistance = rawWindow === 'all' ? Infinity : Math.max(0, Number(rawWindow));

    const allCandidates = Object.entries(dashboard.stocks || {})
      .map(([ticker, data]) => candidateForStock(ticker, data, stockMeta(stocksPayload, ticker), rules))
      .filter(Boolean);

    const visible = allCandidates
      .filter((row) => row.actual || row.distance <= maxDistance)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => {
        return Number(b.actual) - Number(a.actual)
          || Number(a.locked) - Number(b.locked)
          || a.distance - b.distance
          || a.ticker.localeCompare(b.ticker, 'sv');
      });

    const actualCount = allCandidates.filter((row) => row.actual).length;
    const buyCount = visible.filter((row) => row.side === 'BUY').length;
    const sellCount = visible.filter((row) => row.side === 'SELL').length;
    const lockedCount = visible.filter((row) => row.locked).length;

    setSummary([
      ['summary-count', visible.length],
      ['summary-actual', actualCount],
      ['summary-buy', buyCount],
      ['summary-sell', sellCount],
      ['summary-locked', lockedCount]
    ]);

    $('overview-body').innerHTML = visible.length ? visible.map((row) => {
      const boundaryText = row.side === 'BUY'
        ? `Köpgräns ${fmt.format(number(rules.buy_score) ?? 0)}`
        : `Säljgräns ${fmt.format(number(rules.sell_score) ?? 100)}`;
      const proximity = row.actual ? '<strong>Signal nu</strong>' : `${fmt.format(row.distance)} p från gräns`;
      const note = row.actual
        ? (row.action.detail || row.action.label || 'Exekverbar signal')
        : row.locked
          ? `${boundaryText} · spärrad tills fundamentaldata är verifierad`
          : `${boundaryText} · bevaka nästa stängning`;
      return `<tr>
        <td><a class="stock-link" href="./index.html?ticker=${encodeURIComponent(row.ticker)}"><strong>${row.ticker}</strong><span>${row.name}</span></a></td>
        <td><span class="status-chip ${row.side === 'BUY' ? 'buy' : 'sell'}">${row.side === 'BUY' ? 'Köp' : 'Sälj'}</span></td>
        <td>${score(row.score)}</td>
        <td>${proximity}</td>
        <td>${row.lots} / ${row.maxLots}</td>
        <td>${row.armed ? 'Ja' : 'Nej'}</td>
        <td>${row.locked ? '<span class="status-chip warning">Spärrad</span>' : '<span class="status-chip ok">Fri</span>'}</td>
        <td>${note}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="empty-cell">Inga aktier matchar signalfiltret just nu.</td></tr>';
  }

  async function init() {
    try {
      const [stocksPayload, dashboard] = await Promise.all([
        fetch('./data/stocks.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`stocks.json: HTTP ${r.status}`);
          return r.json();
        }),
        fetch('./data/dashboard.json', { cache: 'no-store' }).then((r) => {
          if (!r.ok) throw new Error(`dashboard.json: HTTP ${r.status}`);
          return r.json();
        })
      ]);

      const page = document.body.dataset.overview;
      const render = () => {
        const needle = ($('overview-search')?.value || '').trim().toLocaleLowerCase('sv-SE');
        if (page === 'positions') renderPositions(dashboard, stocksPayload, needle);
        else renderSignals(dashboard, stocksPayload, needle);
      };

      const generated = dashboard.meta?.generated_at || stocksPayload.generated_at;
      $('last-updated').textContent = generated ? new Date(generated).toLocaleString('sv-SE') : 'Okänt';
      $('overview-search')?.addEventListener('input', render);
      $('signal-window')?.addEventListener('change', render);
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
