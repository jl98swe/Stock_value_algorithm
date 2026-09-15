(() => {
  'use strict';

  const numberFormat = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 2 });
  const scoreFormat = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const percentFormat = new Intl.NumberFormat('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const dateFormat = new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatNumber(value) {
    const parsed = number(value);
    return parsed === null ? '–' : numberFormat.format(parsed);
  }

  function formatScore(value) {
    const parsed = number(value);
    return parsed === null ? '–' : scoreFormat.format(parsed);
  }

  function formatMoney(value, currency) {
    const parsed = number(value);
    return parsed === null ? '–' : `${numberFormat.format(parsed)} ${escapeHtml(currency || '')}`.trim();
  }

  function formatDate(value) {
    if (!value) return '–';
    return dateFormat.format(new Date(`${value}T00:00:00Z`));
  }

  function formatDateRange(start, end, status) {
    if (!start) return '–';
    const range = end && end !== start ? `${formatDate(start)}–${formatDate(end)}` : formatDate(start);
    return status === 'estimated_range' ? `${range}<span class="date-status-chip">Preliminärt</span>` : range;
  }

  function stockLink(row) {
    return `<a class="report-stock-link" href="./index.html?ticker=${encodeURIComponent(row.ticker)}"><strong>${escapeHtml(row.ticker)}</strong><span>${escapeHtml(row.name || row.ticker)}</span></a>`;
  }

  function daysLabel(value) {
    const days = number(value);
    if (days === null) return '–';
    if (days === 0) return '<strong>I dag</strong>';
    if (days === 1) return '<strong>1 handelsdag</strong>';
    return `<strong>${days} handelsdagar</strong>`;
  }

  function neutralEps(row) {
    if (row.neutral_quarter_eps == null) return '–';
    return `<strong>${formatNumber(row.neutral_quarter_eps)} ${escapeHtml(row.neutral_eps_currency || '')}</strong>`;
  }

  function expectedEps(row) {
    if (row.expected_eps != null && row.estimate_status === 'verified_comparable') {
      return `<strong>${formatNumber(row.expected_eps)} ${escapeHtml(row.expected_eps_currency || '')}</strong>`;
    }
    if (row.unverified_estimate_available) {
      return '<span class="not-comparable">Estimatet är inte jämförbart</span>';
    }
    return '–';
  }

  function renderUpcoming(rows) {
    $('upcoming-count').textContent = String(rows.length);
    $('urgent-count').textContent = String(rows.filter((row) => row.urgent).length);
    $('upcoming-body').innerHTML = rows.length ? rows.map((row) => `
      <tr class="${row.urgent ? 'urgent-report-row' : ''}">
        <td>${stockLink(row)}</td>
        <td>${formatDateRange(row.report_date_start, row.report_date_end, row.date_status)}</td>
        <td><span class="days-chip ${row.urgent ? 'urgent' : ''}">${daysLabel(row.trading_days_to_report)}</span></td>
        <td>${formatMoney(row.current_price, row.price_currency)}</td>
        <td><strong>${formatScore(row.current_score)}</strong></td>
        <td><strong>${formatNumber(row.current_eps_ttm)} ${escapeHtml(row.eps_ttm_currency || '')}</strong></td>
        <td>${neutralEps(row)}</td>
        <td>${expectedEps(row)}</td>
      </tr>`).join('') : '<tr><td colspan="8" class="report-empty">Inga bevakade aktier har ett registrerat rapportdatum inom de kommande tio handelsdagarna.</td></tr>';
  }

  function pair(before, after, currency = '') {
    if (before == null && after == null) return '–';
    const suffix = currency ? ` ${escapeHtml(currency)}` : '';
    return `<span class="value-pair"><span>${formatNumber(before)}${suffix}</span><span aria-hidden="true">→</span><strong>${formatNumber(after)}${suffix}</strong></span>`;
  }

  function scorePair(before, after) {
    if (before == null && after == null) return '–';
    return `<span class="value-pair"><span>${formatScore(before)}</span><span aria-hidden="true">→</span><strong>${formatScore(after)}</strong></span>`;
  }

  function signed(value, suffix = '') {
    const parsed = number(value);
    if (parsed === null) return '–';
    return `${parsed > 0 ? '+' : ''}${suffix === ' %' ? percentFormat.format(parsed) : scoreFormat.format(parsed)}${suffix}`;
  }

  function renderRecent(rows) {
    $('recent-count').textContent = String(rows.length);
    $('recent-body').innerHTML = rows.length ? rows.map((row) => {
      const scoreChange = number(row.score_change);
      const priceChange = number(row.price_change_pct);
      const scoreClass = scoreChange === null ? '' : scoreChange < 0 ? 'score-more-attractive' : scoreChange > 0 ? 'score-more-expensive' : '';
      const priceClass = priceChange === null ? '' : priceChange > 0 ? 'positive' : priceChange < 0 ? 'negative' : '';
      return `<tr>
        <td>${stockLink(row)}</td>
        <td><strong>${formatDate(row.report_date)}</strong>${row.report_date_verified ? '' : '<span class="date-status-chip">Rapportdatum ej verifierat</span>'}<span class="cell-note">${escapeHtml(row.report_period || '')}</span></td>
        <td>${row.reported_quarter_eps == null ? '–' : `<strong>${formatNumber(row.reported_quarter_eps)} ${escapeHtml(row.reported_eps_currency || '')}</strong>`}</td>
        <td>${row.prior_year_quarter_eps == null ? '–' : `${formatNumber(row.prior_year_quarter_eps)} ${escapeHtml(row.prior_year_eps_currency || '')}`}</td>
        <td>${pair(row.eps_ttm_before, row.eps_ttm_after, row.eps_ttm_currency)}</td>
        <td>${scorePair(row.score_before, row.score_after)}<span class="cell-note">${formatDate(row.before_date)} → ${formatDate(row.after_date)}</span></td>
        <td class="${scoreClass}"><strong>${signed(row.score_change)}</strong></td>
        <td>${pair(row.price_before, row.price_after, row.price_currency)}</td>
        <td class="${priceClass}"><strong>${signed(row.price_change_pct, ' %')}</strong></td>
      </tr>`;
    }).join('') : '<tr><td colspan="9" class="report-empty">Inga verifierade rapporter finns under de senaste tjugo handelsdagarna.</td></tr>';
  }

  async function init() {
    try {
      const response = await fetch('./data/reports.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`reports.json: HTTP ${response.status}`);
      const payload = await response.json();
      $('last-updated').textContent = payload.generated_at ? new Date(payload.generated_at).toLocaleString('sv-SE') : 'Okänt';
      $('as-of-date').textContent = formatDate(payload.as_of_date);
      renderUpcoming(payload.upcoming || []);
      renderRecent(payload.recent || []);
      $('loading-state').hidden = true;
      $('reports-content').hidden = false;
    } catch (error) {
      console.error(error);
      $('loading-state').hidden = true;
      $('error-state').hidden = false;
      $('error-message').textContent = error.message;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
