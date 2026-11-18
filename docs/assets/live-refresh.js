/* Silent published-data polling. Never reload the page or alter user controls. */
(() => {
  'use strict';
  let checking = false;
  async function check() {
    if (document.hidden || checking) return;
    checking = true;
    try {
      const response = await fetch('./data/stocks.json', {cache:'no-store'});
      if (!response.ok) return;
      const payload = await response.json();
      const version = payload.generated_at;
      if (!version) return;
      // Consumers compare against their applied version. Repeat the notification
      // until they can load a complete snapshot, including on the first check.
      window.dispatchEvent(new CustomEvent('stock-data-version', {detail:{version}}));
    } catch (error) {
      console.warn('Kunde inte kontrollera ny publicering', error);
    } finally { checking = false; }
  }
  window.addEventListener('pageshow', check);
  document.addEventListener('visibilitychange', () => {if (!document.hidden) check();});
  window.addEventListener('focus', check);
  check();
  setInterval(check, 60000);
})();
