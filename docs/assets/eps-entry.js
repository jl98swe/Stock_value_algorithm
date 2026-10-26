/* Temporary transport for the static site. Credentials live only in this closure.
   Replace createClient with an authenticated backend when sign-in is available. */
(function (root) {
  'use strict';
  const API = 'https://api.github.com/repos/jl98swe/Stock_value_algorithm';
  const WORKFLOW = 'web_eps_submission.yml';
  const PENDING = 'sva.pending-eps.v1';

  function validDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  }
  function validate(input, today) {
    const item = {...input};
    for (const key of ['ticker', 'report_period', 'period_end', 'published_at', 'metric', 'currency', 'source', 'notes']) item[key] = String(item[key] ?? '').trim();
    item.currency = item.currency.toUpperCase();
    const raw = String(item.value ?? '').trim().replace(',', '.');
    if (!raw || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw) || !Number.isFinite(Number(raw))) throw Error('Ange ett giltigt EPS-värde. Även noll och negativa värden kan anges.');
    item.value = Number(raw);
    if (!/^[A-Z0-9.-]{1,30}$/.test(item.ticker)) throw Error('Välj en aktie i aktielistan.');
    if (!/^\d{4}-Q[1-4]$/.test(item.report_period)) throw Error('Ange rapportperiod som ÅÅÅÅ-Q1 till Q4.');
    if (!validDate(item.period_end) || !validDate(item.published_at) || item.period_end > item.published_at || item.published_at > today) throw Error('Kontrollera periodslut och rapportdatum. Rapportdatum får inte ligga i framtiden.');
    if (!['eps_ttm', 'quarterly_eps'].includes(item.metric)) throw Error('Välj EPS TTM eller kvartals-EPS.');
    if (!/^[A-Z]{3}$/.test(item.currency)) throw Error('Ange valuta med tre bokstäver, exempelvis SEK.');
    if (!item.source || item.source.length > 250 || item.notes.length > 2000) throw Error('Ange källa (högst 250 tecken) och håll noteringen under 2000 tecken.');
    return item;
  }

  function createClient(fetcher) {
    let key = '';
    async function request(path, options = {}) {
      const response = await fetcher(API + path, {
        ...options, cache: 'no-store', redirect: 'error', credentials: 'omit',
        headers: {Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...(key ? {Authorization: `Bearer ${key}`} : {}), ...options.headers}
      });
      if (response.status === 404 && options.optional) return null;
      if (!response.ok) {
        if ([401, 403].includes(response.status)) throw Error('Kontrollera nyckelns behörighet och giltighetstid. Behörigheten ska vara Actions: Read and write.');
        if (response.status === 422) throw Error('Inmatningen kunde inte skickas. Kontrollera fälten och försök med samma registrering.');
        throw Error(`Sparandet kunde inte kontrolleras (HTTP ${response.status}).`);
      }
      return response.status === 204 ? null : response.json();
    }
    return {
      async connect(value) {
        if (!/^github_pat_[A-Za-z0-9_]+$/.test(value)) throw Error('Ange en fine-grained GitHub-nyckel.');
        key = value;
        try { await request(`/actions/workflows/${WORKFLOW}`); }
        catch (error) { key = ''; throw error; }
      },
      disconnect() { key = ''; },
      dispatch(item) { return request(`/actions/workflows/${WORKFLOW}/dispatches`, {method: 'POST', body: JSON.stringify({ref: 'main', inputs: {request_id: item.request_id, submission: JSON.stringify(item)}})}); },
      async run(id) {
        const data = await request(`/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&branch=main&per_page=100`);
        return data.workflow_runs.find(run => run.display_title === `Webb-EPS ${id}`) || null;
      },
      async receipt(id) {
        // Public files need no credential or Contents permission. Reading raw
        // receipts also avoids consuming the unauthenticated REST API quota.
        if (!/^[a-f0-9]{32}$/.test(id)) throw Error('Ogiltigt registrerings-id.');
        const response = await fetcher(`https://raw.githubusercontent.com/jl98swe/Stock_value_algorithm/main/docs/data/manual_requests/${id}.json?t=${Date.now()}`, {cache:'no-store', redirect:'error', credentials:'omit'});
        if (response.status === 404) return null;
        if (!response.ok) throw Error('Publiceringskvittot kunde inte kontrolleras.');
        return response.json();
      }
    };
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = {validate, createClient}; return; }

  root.addEventListener('DOMContentLoaded', () => {
    const $ = id => document.getElementById(id);
    const form = $('eps-entry-form');
    if (!form) return;
    const client = createClient(root.fetch.bind(root));
    let connected = false, busy = false, pending = null, timer = null, failed = false;
    const status = $('eps-save-status');
    const message = text => { status.textContent = text; };
    function remember(item) {
      pending = item;
      try { if (item) localStorage.setItem(PENDING, JSON.stringify(item)); else localStorage.removeItem(PENDING); } catch { /* Memory-only recovery still works if browser storage is disabled. */ }
    }
    function buttons() {
      $('eps-save').disabled = busy || !!pending;
      $('eps-resume').hidden = !pending;
      $('eps-resume').disabled = busy;
      $('eps-edit').hidden = !pending || !failed;
      $('eps-edit').disabled = busy;
      $('eps-disconnect').hidden = !connected;
      $('eps-key-form').hidden = connected;
      $('eps-access-status').textContent = connected ? 'Ansluten.' : 'Inte ansluten.';
    }
    async function published(item, receipt) {
      const response = await fetch(`./data/manual_requests/${item.request_id}.json?t=${Date.now()}`, {cache: 'no-store'});
      if (!response.ok) return false;
      const live = await response.json();
      if (live.request_id !== item.request_id || live.status !== receipt.status) return false;
      const value = receipt.result_eps_ttm;
      message(receipt.status === 'applied'
        ? `Sparat och publicerat för ${item.ticker}. EPS TTM: ${new Intl.NumberFormat('sv-SE', {maximumFractionDigits: 4}).format(value)} ${receipt.currency}. Poäng, historik och signaler är omräknade.`
        : `Sparat för ${item.ticker}. EPS TTM och poäng har inte uppdaterats för denna registrering. ${receipt.reason}`);
      remember(null);
      // Refresh the existing history and active value without leaving this page.
      document.dispatchEvent(new CustomEvent('eps-saved'));
      return true;
    }
    async function monitor() {
      clearTimeout(timer);
      if (!pending || busy) return;
      busy = true; buttons();
      const item = pending;
      try {
        const receipt = await client.receipt(item.request_id);
        if (receipt) {
          message('Värdet är sparat och beräkningen klar. Väntar på publicering…');
          if (await published(item, receipt)) return;
          if (connected) {
            const run = await client.run(item.request_id);
            if (run?.status === 'completed' && run.conclusion !== 'success') {
              message('Värdet är sparat men publiceringen misslyckades. Välj Kontrollera / återuppta för att försöka publicera samma registrering igen.');
              return;
            }
          }
        } else if (connected) {
          const run = await client.run(item.request_id);
          if (run?.status === 'completed' && run.conclusion !== 'success') {
            failed = true;
            message('Sparandet misslyckades. Inga data från denna körning har publicerats. Välj Redigera inmatningen för att korrigera uppgifter eller återuppta samma registrering.');
            return;
          }
          message(run?.status === 'in_progress' ? 'Sparar och räknar om poäng, historik och signaler…' : 'Registreringen väntar på bearbetning…');
        } else {
          message('En inmatning väntar. Anslut nyckeln för att kontrollera den.');
          return;
        }
        timer = setTimeout(monitor, 15000);
      } catch {
        message('Kunde inte kontrollera status. Inmatningen finns kvar. Välj Kontrollera / återuppta.');
      } finally { busy = false; buttons(); }
    }
    $('eps-key-form').addEventListener('submit', async event => {
      event.preventDefault();
      const value = $('eps-access-key').value.trim();
      $('eps-access-key').value = '';
      try {
        await client.connect(value); connected = true; buttons();
        message('Ansluten. Du kan nu spara värden.');
        if (pending) await monitor();
      } catch (error) { message(error.message); }
    });
    $('eps-disconnect').addEventListener('click', () => { client.disconnect(); connected = false; buttons(); });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || pending) return;
      if (!connected) { message('Anslut din GitHub-nyckel för att spara.'); $('eps-access').open = true; $('eps-access-key').focus(); return; }
      let item;
      try {
        // Another tab may already be processing a submission.
        if (localStorage.getItem(PENDING)) { remember(JSON.parse(localStorage.getItem(PENDING))); buttons(); await monitor(); return; }
      } catch { /* Storage can be disabled by browser policy. */ }
      try {
        item = validate({ticker: $('eps-ticker').value, report_period: $('eps-period').value, period_end: $('eps-period-end').value, published_at: $('eps-published').value, metric: $('eps-metric').value, value: $('eps-value').value, currency: $('eps-currency').value, source: $('eps-source').value, notes: $('eps-note').value}, new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Stockholm'}).format(new Date()));
        item.request_id = crypto.randomUUID().replaceAll('-', '');
      } catch (error) { message(error.message); return; }
      remember(item); failed = false; busy = true; buttons();
      message('Skickar registreringen…');
      try { await client.dispatch(item); }
      catch { message('Kunde inte bekräfta mottagandet. Välj Kontrollera / återuppta innan du lägger in ett nytt värde.'); busy = false; buttons(); return; }
      busy = false; await monitor();
    });
    $('eps-resume').addEventListener('click', async () => {
      if (!pending || busy) return;
      if (!connected) { message('Anslut nyckeln för att kontrollera inmatningen.'); return; }
      busy = true; buttons();
      try {
        const receipt = await client.receipt(pending.request_id);
        const run = await client.run(pending.request_id);
        if ((!receipt && !run) || (run?.status === 'completed' && run.conclusion !== 'success')) await client.dispatch(pending);
        busy = false; await monitor();
      } catch (error) { message(error.message); }
      finally { busy = false; buttons(); }
    });
    $('eps-edit').addEventListener('click', () => {
      if (!pending || busy || !failed) return;
      const mapping = {ticker:'ticker', report_period:'period', period_end:'period-end', published_at:'published', metric:'metric', value:'value', currency:'currency', source:'source', notes:'note'};
      // The stock selector is authoritative; do not silently edit a different stock.
      if ($('review-stock').value !== pending.ticker) { message(`Välj ${pending.ticker} i aktielistan innan du redigerar registreringen.`); return; }
      for (const [key, suffix] of Object.entries(mapping)) $('eps-' + suffix).value = pending[key];
      remember(null); failed = false; buttons();
      $('eps-metric').dispatchEvent(new Event('change'));
      message('Inmatningen kan nu korrigeras och sparas på nytt.');
    });
    // Only public report fields and an id are retained, never the access key.
    try {
      const stored = JSON.parse(localStorage.getItem(PENDING));
      if (stored && /^[a-f0-9]{32}$/.test(stored.request_id)) pending = stored;
    } catch { /* No unfinished request. */ }
    buttons();
    if (pending) monitor();
    root.addEventListener('pagehide', () => { client.disconnect(); connected = false; clearTimeout(timer); buttons(); });
  });
})(typeof window === 'undefined' ? globalThis : window);
