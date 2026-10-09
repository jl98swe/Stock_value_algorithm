(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(target, toggle, events, expanded, ticker, prettyDate) {
    const openDetails = new Set(Array.from(target.querySelectorAll('details[open]'), el => el.dataset.newsKey));
    const visible = expanded ? events : events.slice(0, 1);
    target.innerHTML = visible.length ? visible.map(event => {
      const key = `${ticker}|${event.event_id || `${event.published_at}|${event.title}`}`;
      const meta = [prettyDate(event.published_at), event.source, event.is_regulatory ? 'Regulatorisk' : 'Bolagsnyhet'].filter(Boolean).map(esc).join(' · ');
      return `<article class="news-item">
        <h3>${esc(event.title)}</h3>
        <details class="news-details" data-news-key="${esc(key)}"${openDetails.has(key) ? ' open' : ''}>
          <summary><span class="news-more-label">Visa mer</span><span class="news-less-label">Visa mindre</span></summary>
          <div class="news-details-content">
            <div class="news-meta">${meta}</div>
            <span class="news-badge ${event.locking ? 'locking' : ''}">${event.locking ? 'Spärrar' : event.review_status === 'reviewed' ? 'Granskad' : 'Ogranskad'}</span>
            <p class="news-summary">${esc(event.summary || '')}</p>
            <a href="./review.html?ticker=${encodeURIComponent(ticker)}&amp;event=${encodeURIComponent(event.event_id || '')}">Granska nyheten</a>
          </div>
        </details>
      </article>`;
    }).join('') : '<div class="empty-state">Inga bolagsnyheter för aktien.</div>';
    toggle.hidden = events.length <= 1;
    toggle.textContent = expanded ? 'Visa färre nyheter' : 'Visa alla nyheter';
    toggle.setAttribute('aria-expanded', String(expanded && events.length > 1));
  }
  if (typeof module !== 'undefined') module.exports = {render};
  if (typeof window !== 'undefined') window.companyNews = {render};
})();
