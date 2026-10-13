# Morgonnotiser – teknisk driftsättning

## Status
Webbgränssnittet på `docs/alerts.html` är byggt, men registrering är **avstängd** tills en säker separat backend finns. Använd inte ett publikt GitHub-repo eller statisk JSON för personuppgifter.

## Rekommenderad driftsättning
1. Driftsätt en backend med databas (t.ex. Supabase Edge Functions + PostgreSQL) och e-postleverantör med verifierad avsändardomän (t.ex. Resend). Implementera Web Push med VAPID och service worker från samma ursprung/scope som webbplatsen. GitHub Pages får inte lagra hemliga nycklar.
2. API: `POST /subscribe` med {email,channels,topics,strategy,tickers,consent}; e-postbekräftelse via slumpmässig engångslänk; säker hanteringslänk för ändrade preferenser; ett klick för `unsubscribe`; register/unregister för push endpoint. Token i databasen ska hashas. Skydda mot enumeration, CSRF, massregistrering och missbruk. CORS: bara webbplatsens riktiga ursprung.
3. Lagra kontakt-/samtyckestidpunkt, verifieringsstatus, prenumerationspreferenser, push-prenumerationer och leveransjournaler; rensa avslutade prenumerationer. Informera om personuppgiftsbehandling.
4. Lägg in publik API-basadress i `docs/assets/alerts.js`, **aldrig** privat API-nyckel. Aktivera först efter verifierat end-to-end-test av bekräftelsemejl och avprenumeration.
5. Schemalägg morgonjobbet i Europe/Stockholm (DST-medvetet), mål 07.15–07.30 svensk tid. GitHub Actions schemakörningar kan fördröjas; exakta leveranstider kan inte garanteras. Jobbet ska verifiera att föregående handelsdags data finns och är validerad innan signalerna skickas. Skicka annars inget vilseledande mejl.
6. Bygg en enskild sammanfattning per mottagare och kanal. Deduplicera på mottagare + signalidentitet + handelsdag + strategi + kanal. Kommande rapport och nära signal ska framgå som separata *indikativa* bevakningar, aldrig som bekräftad handel.
7. Testa mail confirm, unsubscribe (utan inloggning), preference edits, ingen utskick efter unsubscribe, rate limiting, felaktiga data, DST, retries och iOS home-screen push.

## Varför inget automatiskt utskick ingår i denna PR
Den statiska sajten kan inte sköta prenumerationer, avprenumerationer, autentisering eller hemliga API-nycklar säkert. Dessa kräver backend och tjänstekonfiguration som ännu inte finns verifierade i denna miljö. Därför förhindrar gränssnittet anmälan tills driften är färdig, i stället för att erbjuda ett trasigt formulär.
