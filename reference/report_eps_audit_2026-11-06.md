# Rapportkomplettering 6 november 2026

Bas: main a75690001b0300fc2f0b941d6c60808a8a683549. Samtliga 119 tickers inventerade mot aktuell/historisk kalender, tidigare rapportkontroller och sparade rapporter. EQL, MTG, Lundin Mining och Hufvudstaden från föregående genomgång lämnas oförändrade. HUFV:s senare komplettering bekräftad. Inaktiv VIVA exkluderas från förfallna rapporter.

| Aktie | Rapportdatum CET | Utspädd kvartals-EPS | Jämförelse | Tidigare TTM SEK | Ny TTM SEK |
|---|---|---:|---:|---:|---:|
| Attendo | 6 nov 07:00 | 2,68 SEK | 2,23 SEK | 6,6217 | 7,0717 |
| BTS Group | 6 nov 06:30 | 2,12 SEK | 0,69 SEK | 4,9017 | 6,3317 |
| Fenix Outdoor B | 28 okt 15:00 | 1,64 EUR | 1,50 EUR | 4,1514 (automatisk Q3) | 5,782831382751465 |

Attendo: https://www.inderes.se/en/releases/attendos-third-quarter-report-2026-long-term-focus-on-quality-underpins-yet-another-quarter-of-strong-results . Koncernens resultat efter skatt och utspädning; justerad EPS 2,93 används inte. Befintlig kvartalsbrygga: 6,6217 + 2,68 − 2,23 = 7,0717 SEK. Publiceringstid enligt bolagets inbjudan: https://www.mfn.se/a/attendo/inbjudan-till-presentation-av-attendos-rapport-for-det-tredje-kvartalet-2026.iframe .

BTS: https://www.mfn.se/one/a/bts-group/bts-group-ab-publ-interim-report-january-september-2026-0ed8931f.iframe och https://www.inderes.se/releases/bts-group-ab-publ-delarsrapport-januari-september-2026 . Fotnot 4 anger före och efter utspädning. Ojusterad kvartals-EPS 2,12 används; 2,16 är justerad och väljs bort. Befintlig kvartalsbrygga: 4,9017 + 2,12 − 0,69 = 6,3317 SEK.

Fenix: officiell PDF https://ml-eu.globenewswire.com/Resource/Download/bfe390a5-ea02-49eb-8536-211d267062b7 . S.1 anger publicering 28 oktober 15:00; s.4–5 anger B-aktie efter utspädning 1,64 (1,50) EUR och direkt rapporterat Oct/Sept-TTM 0,52 EUR. Förstasidans 1,65 är före utspädning. Yahoo quarterlyDilutedEPS 1,65 och härledd jämförelse 1,209 är alltså inte tillförlitliga för denna brygga. Direkt rapporterat diluted TTM används i stället för Yahoo 0,379 EUR; det är inte en ändring av tidigare manuella TTM. Befintlig FX-regel: föregående sparade handelsdags EUR/SEK, 27 oktober 11,1208295822144. 0,52 × kursen = 5,782831382751465 SEK. Diskret valutamarkering och uppföljning mot TradingView behålls. Tidigare Q2-TTM 5,69 SEK bevaras.

Kalenderns felaktiga 5 november korrigeras med manuell kalenderpost och rapportdatumoverride för Fenix 2026-Q3, inklusive Yahoo-alias. Råa Yahoo-värden och kalenderobservationer behålls för spårbarhet. Omräkning får börja 28 oktober, aldrig kvartalsslutet. Ny rapportdata för Attendo/BTS gäller 6 november. Slutkurser finns till och med 5 november, så dagens slutliga poäng och slutliga signaler kan inte skapas ännu.

Rimlighetskontroll: kvartalsbryggan antar jämförbara EPS-definitioner. Ändrat genomsnittligt aktieantal och avrundning kan ge en liten skillnad mot rapporterad års-/niomånadersbrygga. BTS:s rapporterade TTM 6,33 stämmer väl med modellens 6,3317. Fenix har direkt rapporterat diluted TTM och kräver därför ingen osäker kvartalsbrygga.

Inga förfallna rapporter med förväntad EPS saknar nya värden efter kompletteringen. EQT:s Q3-redogörelse 15 oktober innehåller ingen EPS; detta dokumenterade undantag behålls och äldre TTM används. Fullständig tickerinventering: recent_report_eps_audit_2026-11-06.csv.

Validering: 477 Python-tester och 14 UI-tester godkända. Ordinarie pipeline --skip-fetch --skip-dividends, limit_dashboard_window, validate_outputs, report_data_status och history_guard körs före publicering. Inga ändringar av handelsregler eller generella historikundantag.

## Fenix: manuell prioritet och rätt rapportförsäljning

Den kanoniska Yahoo-aliasen för samma Q3-period konkurrerade med den nya manuella raden när datumen blev lika. Den genererade aliasen ersätts därför i modellens rapporttabell. Yahoo-originalet 0,379 EUR ligger kvar i earnings-historiken. add_report tar nu bort genererade alias för samma ticker och period när verifierad manuell rapport registreras, så de inte kan vinna senare urval.

Kalenderarkivet innehåller korrekt 28 oktober från Yahoo 15 september och Börskollen 26 september; senare MFN-observationer från 11 oktober pekade felaktigt på 5 november. Den tidigare granskningen noterade att MFN-kopplingen pekade på Enersense. Manuell korrigering och arkiverad kunskap används. Rapportundvikande får därmed en korrekt rapportförsäljning 27 oktober till sparad öppningskurs 299,00 SEK för FOI-B-ST-lot-6, i stället för tidigare poängförsäljning 28 oktober till 319,50 SEK. Historikgrinden utökas med en dokumenterad exakt ersättning av dessa två exekveringar. Den medger ingen ändring av köp, andra positioner, andra strategier eller poäng före 28 oktober, och förbjuder att rättelsen återställs senare.

Verifierad publiceringstid för Fenix sparas även i report_publications.csv, så datumoverride inte tappar tidpunkten och lämnar en onödig EPS-spärr. Arkivdatumet används som bevis för rapportförsäljningen; den äldre simuleringens köphistorik ändras inte genom en ny kalenderkunskapsgräns.

## Slutlig verifiering

Ordinarie pipeline, limit_dashboard_window, validate_outputs, report_data_status och history_guard är godkända lokalt mot a75690001b03. Samtliga 477 Python-tester och 14 relevanta UI-tester är godkända. Endast Fenix har ändrade publicerade poäng: sju handelsdagar 28 oktober–5 november. Senaste poäng 99,7385 → 99,5326; slutkurs 328,50 SEK oförändrad. Övriga 118 aktiers poäng är oförändrade. Attendo/BTS har nya rapportvärden från 6 november men inga nya slutliga poäng före dagens stängningsdata.

Fenix rapportspärr är borttagen från 28 oktober. Rapportundvikande behåller köpet 18 augusti till 339,50 SEK och ersätter exakt försäljningen 28 oktober 319,50 SEK med rapportförsäljning 27 oktober 299,00 SEK. Andra skyddade affärer bevaras. Historikgrindens ersättningsregel verifierar även den gamla exekveringens exakta värden när den ligger på EPS-gränsen och därför inte ingår i det skyddade intervallet.

MFN-källan i data/news/mfn_sources.csv pekade på Enersense International. Den är rättad till https://mfn.se/all/a/fenix-outdoor för framtida kalender- och nyhetshämtningar. LUMI:s separata granskningsskript filtrerar nu manifestet på ticker innan perioder matchas, så andra bolags Q3-publiceringar inte kan användas som LUMI-bevis.
