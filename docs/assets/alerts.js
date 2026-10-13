"use strict";
(() => {
  // Production API is configured ONLY after the secure subscription backend is deployed.
  // Never put a provider API key or private VAPID key in this public file.
  const API_BASE = "";
  const form = document.getElementById("alerts-form");
  const status = document.getElementById("alerts-feedback");
  const unavailable = document.getElementById("alerts-unavailable");
  const button = document.getElementById("alerts-submit");
  const enabled = /^https:\/\/[^/]+$/.test(API_BASE);
  if (!enabled) { unavailable.hidden = false; form.hidden = true; return; }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("alert-email").value.trim();
    const channels = [...form.querySelectorAll('input[name="channel"]:checked')].map(el => el.value);
    const topics = [...form.querySelectorAll('input[name="topic"]:checked')].map(el => el.value);
    const tickers = document.getElementById("alert-tickers").value.split(",").map(x => x.trim().toUpperCase()).filter(Boolean);
    if (!channels.length || !topics.length) { status.textContent = "Välj minst en kanal och en bevakning."; return; }
    if (tickers.length > 100 || tickers.some(t => !/^[A-Z0-9.-]{1,24}$/.test(t))) { status.textContent = "Kontrollera tickerlistan."; return; }
    button.disabled = true; status.textContent = "Registrerar…";
    try {
      const response = await fetch(API_BASE + "/subscribe", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email,channels,topics,strategy:document.getElementById("alert-strategy").value,tickers,consent:true})});
      if (!response.ok) throw new Error("request");
      status.textContent = "Om adressen kan registreras skickas ett bekräftelsemejl. Kontrollera även skräpposten.";
      form.reset();
    } catch { status.textContent = "Det gick inte att registrera bevakningen. Försök igen senare."; }
    finally { button.disabled = false; }
  });
})();