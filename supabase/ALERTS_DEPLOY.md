# Kostnadsfri Gmail SMTP-arkitektur

- Supabase Edge Function `alerts` tar emot registreringar och lagrar en privat e-postko.
- GitHub Actions `alert-email-queue.yml` laser ett koobjekt och skickar det via Gmail SMTP.
- Ingen Resend, ingen egen doman. Gmail-hemligheterna finns endast i GitHub Actions.

## For att prova
1. Kor `supabase/migrations/20261102_alert_email_queue.sql` och `supabase/migrations/20261102_alert_capacity.sql` i Supabase SQL Editor.
2. Driftsatt `supabase/functions/alerts/index.ts` med `verify_jwt=false`.
3. Kontrollera att Supabase-funktionens service role har INSERT till `alert_email_queue`.
4. Testa registrering mot Edge Function med en egen testadress, utan att aktivera webbformularet.
5. Kor workflow `Send queued alert confirmation email` manuellt pa main efter merge.
6. Bekrafta och testa avprenumeration, dubbletter och obehoriga anrop.

## Inte fardigt
- Publik registrering ar avstangd.
- Bekraftelsemejl skickas inte direkt: GitHub Actions maste startas. Ett schema kan laggas till efter test.
- IP-baserad rate limiting, verifiering av fyra-prenumerantgransen vid parallella anrop, atomisk tokenkonsumtion och hantering av avprenumerationslankar i morgonutskick aterstar.
- Push och morgonutskick ar inte aktiverade.
- GitHub Actions kan forsenas och SMTP kan nekas av Gmail.

## Sakerhet
Ingen privat nyckel i `docs/`. Behall RLS och endast service_role-atkomst.
