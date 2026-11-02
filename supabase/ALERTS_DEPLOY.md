# E-postbevakningar – Supabase Edge Function

Funktionen finns i `supabase/functions/alerts/index.ts`. Den har tre anrop:
- `POST /functions/v1/alerts/subscribe` – skapar väntande prenumeration och mejlar en bekräftelselänk.
- `GET /functions/v1/alerts/confirm?token=...` – aktiverar efter bekräftelse.
- `GET /functions/v1/alerts/unsubscribe?token=...` – avslutar prenumeration med giltig avregistreringstoken.

## Driftsättning (inte automatiskt verifierad)
1. Distribuera funktionen `alerts` i Supabase. `verify_jwt = false` behövs eftersom besökare inte loggar in. Funktionen använder servernyckel och databasens RLS.
2. Lägg till följande hemligheter i Supabase Edge Functions: `RESEND_API_KEY` och `ALERT_FROM_EMAIL` (verifierad avsändaradress). `SUPABASE_URL` och `SUPABASE_SERVICE_ROLE_KEY` tillhandahålls normalt av Supabase.
3. Kontrollera att avsändardomänen är verifierad hos Resend. Gmail-applösenord kan inte användas i denna Edge Function.
4. Genomför end-to-end-test av registrering, mejl, bekräftelse och avregistrering. Först därefter ska `API_BASE` i `docs/assets/alerts.js` aktiveras.
5. Aktuell implementation stöder enbart e-postkanalen. Push och morgonutskick är inte driftsatta. Försök med push ska nekas, inte registreras tyst.

## Säkerhet och begränsningar
- API:t svarar generiskt för befintliga aktiva adresser. Bekräftelsetoken lagras enbart som SHA-256-hash.
- Enkel begränsning: samma väntande adress kan inte begära nytt mejl oftare än var 15:e minut.
- **Återstår före publik lansering:** IP-baserad rate limiting och bot-skydd, atomisk tokenkonsumtion med transaktion/RPC, komplett avregistreringslänk i varje utskick, samt ett separat jobb för morgonsammanfattningar.
- Bekräftelseflödet är därför en första implementation, inte färdig produktion.
