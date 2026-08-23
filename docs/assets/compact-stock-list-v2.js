(() => {
  'use strict';

  const STYLE_ID = 'compact-stock-list-v2-style';
  const SCORE_CLASSES = ['stock-score-buy', 'stock-score-sell', 'stock-score-mid'];

  function parseScore(value) {
    if (!value) return null;
    const normalized = String(value).replace(/\s/g, '').replace(',', '.');
    const score = Number(normalized);
    return Number.isFinite(score) ? score : null;
  }

  function scoreClass(score) {
    if (score !== null && score < 5) return 'stock-score-buy';
    if (score !== null && score > 95) return 'stock-score-sell';
    return 'stock-score-mid';
  }

  function installStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .stock-list {
        gap: 3px !important;
      }

      .stock-list .stock-button {
        border-radius: 8px !important;
        padding: 5px 8px !important;
        min-height: 30px;
        transition: filter .12s ease, border-color .12s ease !important;
      }

      .stock-list .stock-button.stock-score-buy {
        background: rgba(31, 143, 103, 0.20) !important;
        border-color: rgba(31, 143, 103, 0.38) !important;
      }

      .stock-list .stock-button.stock-score-sell {
        background: rgba(199, 71, 71, 0.20) !important;
        border-color: rgba(199, 71, 71, 0.38) !important;
      }

      .stock-list .stock-button.stock-score-mid {
        background: rgba(104, 118, 132, 0.10) !important;
        border-color: rgba(104, 118, 132, 0.20) !important;
      }

      .stock-list .stock-button:hover {
        transform: none !important;
        box-shadow: none !important;
        filter: brightness(0.96);
      }

      .stock-list .stock-button.active {
        border-color: var(--brand-2) !important;
        box-shadow: inset 3px 0 0 var(--brand-2) !important;
      }

      .stock-list .row-top {
        display: flex !important;
        align-items: center;
        justify-content: space-between;
        gap: 8px !important;
      }

      .stock-list .stock-name-small,
      .stock-list .stock-process-dot {
        display: none !important;
      }

      .stock-list strong {
        font-size: 12px !important;
        line-height: 1.1;
      }

      .stock-list .mini-score {
        font-size: 11px !important;
        line-height: 1.1;
        color: var(--text) !important;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
      }
    `;
    document.head.appendChild(style);
  }

  function compactButton(button) {
    if (!(button instanceof HTMLElement)) return;

    const row = button.querySelector('.row-top');
    const scoreElement = button.querySelector('.mini-score');
    if (!row || !scoreElement) return;

    const score = parseScore(scoreElement.textContent);
    button.classList.remove(...SCORE_CLASSES);
    button.classList.add(scoreClass(score));

    row.querySelectorAll('.stock-process-dot').forEach((dot) => dot.remove());

    const ticker = row.querySelector('strong')?.textContent?.trim() || '';
    const stockName = button.querySelector('.stock-name-small')?.textContent?.trim() || '';
    const scoreLabel = score === null ? 'saknas' : scoreElement.textContent.trim();
    button.setAttribute('aria-label', `${ticker}, värdering ${scoreLabel}${stockName ? `, ${stockName}` : ''}`);
  }

  function compactList() {
    const list = document.getElementById('stock-list');
    if (!list) return;
    list.querySelectorAll('.stock-button').forEach(compactButton);
  }

  function init() {
    installStyles();

    const list = document.getElementById('stock-list');
    if (!list) return;

    compactList();
    const observer = new MutationObserver(compactList);
    observer.observe(list, { childList: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
