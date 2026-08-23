(() => {
  'use strict';

  const STYLE_ID = 'compact-stock-list-style';
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
      }

      .stock-list .stock-button:hover {
        transform: none !important;
        box-shadow: none !important;
      }

      .stock-list .stock-button.active {
        box-shadow: inset 2px 0 0 var(--brand-2) !important;
      }

      .stock-list .row-top {
        display: grid !important;
        grid-template-columns: 8px minmax(0, 1fr) auto;
        align-items: center;
        gap: 7px !important;
      }

      .stock-list .stock-name-small {
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
        font-variant-numeric: tabular-nums;
      }

      .stock-process-dot {
        display: block;
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #9aa5ad;
      }

      .stock-score-buy .stock-process-dot {
        background: var(--green, #1f8f67);
      }

      .stock-score-sell .stock-process-dot {
        background: var(--red, #c74747);
      }

      .stock-score-mid .stock-process-dot {
        background: #9aa5ad;
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

    let dot = row.querySelector('.stock-process-dot');
    if (!dot) {
      dot = document.createElement('span');
      dot.className = 'stock-process-dot';
      dot.setAttribute('aria-hidden', 'true');
      row.insertBefore(dot, row.firstChild);
    }

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
