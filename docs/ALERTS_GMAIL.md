# Gmail-utskick för Stock Value Alerts

## Status
Gmail SMTP är förberett för ett **manuellt test** via GitHub Actions.
Inga prenumerationsmejl skickas automatiskt. Registreringsformuläret är
fortfarande avstängt tills en säker backend har driftsatts.

## Testa
1. Skapa repository secrets `GMAIL_ADDRESS` och `GMAIL_APP_PASSWORD`.
2. Öppna Actions → Test Gmail alert delivery → Run workflow på `main`.
3. Testet skickar endast till avsändaradressen själv. Kontrollera inkorgen
   och körningens status. Inga hemligheter skrivs ut.

## Nästa steg
- Skapa säker prenumerations-API med verifiering och avprenumeration.
- Lägg in `SUPABASE_URL` och `SUPABASE_SERVICE_ROLE_KEY` som GitHub
  Actions secrets för serverjobbet. Service role får aldrig hamna i
  GitHub Pages eller klient-JavaScript.
- Läs enbart aktiva och verifierade prenumerationer, respektera ämnen,
  strategier och tickerfilter, och begränsa antalet aktiva till fyra.
- Bygg dagligt digest från verifierad signaldata och logga utskick för att
  undvika dubbletter. Säkerställ avprenumeration före varje sändning.
- Använd Europe/Stockholm och hantera sommartid. Schemalagda GitHub
  Actions kan bli försenade.

Gmail-applösenordet lagras enbart i GitHub Actions secrets. Google kan
begränsa eller blockera automatiserad SMTP-trafik.
