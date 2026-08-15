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
      .filter((row) => Number(row.data.position?.lots || 0) > 0)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => Number(b.data.position?.unrealized_pct || 0) - Number(a.data.position?.unrealized_pct || 0));

    $('summary-count').textContent = String(rows.length);
    $('overview-body').innerHTML = rows.length ? rows.map((row) => {
      const p = row.data.position || {};
      const latest = row.data.latest || {};
      const action = row.data.next_action || {};
      return `<tr>
        <td><a class="stock-link" href="./index.html?ticker=${encodeURIComponent(row.ticker)}"><strong>${row.ticker}</strong><span>${row.name}</span></a></td>
        <td>${p.lots || 0} / ${p.max_lots || 2}</td>
        <td>${money(p.avg_entry, row.currency)}</td>
        <td>${money(latest.close, row.currency)}</td>
        <td class="${number(p.unrealized_pct) >= 0 ? 'positive' : 'negative'}">${pct(p.unrealized_pct)}</td>
        <td>${score(latest.score)}</td>
        <td>${latest.fundamental_lock ? '<span class="status-chip warning">Spärr</span>' : '<span class="status-chip ok">Öppen</span>'}</td>
        <td>${action.type && action.type !== 'NONE' ? `<span class="status-chip action">${action.label}</span>` : '–'}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="8" class="empty-cell">Inga aktiva positioner matchar filtret.</td></tr>';
  }

  function signalCandidate(ticker, data, meta, rules) {
    const latest = data.latest || {};
    const position = data.position || {};
    const action = data.next_action || {};
    const value = number(latest.score);
    if (value === null) return null;

    const buy = number(rules.buy_score) ?? 0;
    const sell = number(rules.sell_score) ?? 100;
    const hasPosition = Number(position.lots || 0) > 0;
    const actual = action.type === 'BUY' || action.type === 'SELL';
    const buyDistance = Math.max(0, value - buy);
    const sellDistance = Math.max(0, sell - value);

    let side = null;
    let distance = null;
    if (actual) {
      side = action.type;
      distance = 0;
    } else if (buyDistance <= 5) {
      side = 'BUY';
      distance = buyDistance;
    } else if (hasPosition && sellDistance <= 5) {
      side = 'SELL';
      distance = sellDistance;
    } else {
      return null;
    }

    return {
      ticker,
      name: meta.name || ticker,
      score: value,
      side,
      distance,
      actual,
      locked: Boolean(latest.fundamental_lock),
      lots: Number(position.lots || 0),
      armed: side === 'BUY' ? position.buy_armed !== false : position.sell_armed !== false,
      action
    };
  }

  function renderSignals(dashboard, stocksPayload, needle) {
    const rules = dashboard.meta?.rules || {};
    const rows = Object.entries(dashboard.stocks || {})
      .map(([ticker, data]) => signalCandidate(ticker, data, stockMeta(stocksPayload, ticker), rules))
      .filter(Boolean)
      .filter((row) => textIncludes(row, needle))
      .sort((a, b) => Number(b.actual) - Number(a.actual) || a.distance - b.distance || a.score - b.score);

    $('summary-count').textContent = String(rows.length);
    $('overview-body').innerHTML = rows.length ? rows.map((row) => `<tr>
      <td><a class="stock-link" href="./index.html?ticker=${encodeURIComponent(row.ticker)}"><strong>${row.ticker}</strong><span>${row.name}</span></a></td>
      <td><span class="status-chip ${row.side === 'BUY' ? 'buy' : 'sell'}">${row.side === 'BUY' ? 'Köp' : 'Sälj'}</span></td>
      <td>${score(row.score)}</td>
      <td>${row.actual ? '<strong>Signal nu</strong>' : `${fmt.format(row.distance)} p från gräns`}</td>
      <td>${row.lots} / 2</td>
      <td>${row.armed ? 'Ja' : 'Nej'}</td>
      <td>${row.locked ? '<span class="status-chip warning">Spärrad</span>' : '<span class="status-chip ok">Fri</span>'}</td>
      <td>${row.actual ? row.action.detail || row.action.label : 'Bevaka nästa stängning'}</td>
    </tr>`).join('') : '<tr><td colspan="8" class="empty-cell">Inga aktier ligger nära en signalgräns just nu.</td></tr>';
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
