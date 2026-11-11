# Rapportkomplettering 11 november 2026

Bas: main 248f3230219ccb8e97ffefc6bf733cf1321cbeab. Alla 119 tickers inventeras mot kanoniska rapporter, aktuell kalender och kalenderhistorik. Genovis och Scandic från senaste genomgången 10 november exkluderas från ny komplettering; deras värden bevaras.

| Aktie | Publicering CET | Kvartals-EPS SEK | Jämförelse jul-sep 2025 SEK | Tidigare TTM SEK | Ny TTM SEK |
|---|---|---:|---:|---:|---:|
| Embracer, EMBRAC-B.ST | 11 nov 07:00 | 0,70 | -0,11 | -23,6958 | -22,8858 |
| New Wave, NEWA-B.ST | 11 nov 07:00 | 1,77 | 1,25 | 6,0518 | 6,5718 |

Ordinarie metod: föregående manuellt verifierad TradingView TTM + aktuell utspädd kvartals-EPS minus samma kvartal föregående år. Alla befintliga kanoniska rapportposter bevaras. Bara två nya perioder tillkommer. Båda bolagen rapporterar och handlas i SEK; ingen valutaomräkning. Publicering före öppning ger effective_date 11 november. Embracers juli-september är räkenskapsårets Q2 2026/27; modellens periodnyckel följer befintlig kalenderkvartalskonvention 2026-Q3.

## Officiellt underlag

Embracer rapport sida 21: https://storage.mfn.se/948e7aea-0a5b-4730-b16c-18b2f5f6d6f8/embracer-group-interim-report-q2-2026-27.pdf . Utspädd ojusterad EPS 0,70. Total koncern inklusive avvecklad verksamhet för jämförelsekvartalet är -0,11; rubrikens -0,38 gäller kvarvarande verksamhet och ska inte användas mot modellens befintliga totala TTM. Yahoo-värdet -0,10 sparas som råobservation men officiell manuell jämförelse -0,11 prioriteras. Justerad EPS efter full utspädning 1,45 används inte. Publicering 07:00 enligt https://embracer.com/releases/embracer-group-publishes-interim-report-q2-july-september-2026-cash-ebit-increased-to-sek-203-million/ .

New Wave rapport sida 4: https://storage.mfn.se/848730ac-8dec-41ad-819f-d63c7d22ef54/q3-nwg-2026-sv-11-10-lq.pdf . Ojusterad EPS 1,77 (1,25) och direkt avrundad R12 6,57. Den officiella jämförelsen 1,25 prioriteras framför Yahoo-härledd 1,24, som bevaras separat. Årsredovisning 2025 sida 101 visar samma antal aktier före och efter utspädning, 132 687 086: https://www.nwg.se/globalassets/reports/arsredovisningar/en/2025/nwg-annual-report-2025---mars_31_en_lq.pdf . Q3 visar oförändrat antal aktier för alla perioder och inga nya utspädande instrument. Det stöder bedömningen att rapportens EPS även motsvarar diluted. Publicering 07:00 enligt bolagets regulatoriska meddelande https://mfn.se/a/new-wave-group/delarsrapport-for-tredje-kvartalet-2026-new-wave-group-ab.iframe . Svensk rapport används; engelsk pressrelease har ett avvikande nettoresultat i rubriktexten (253 mot 235 MSEK) men samma EPS.

## Rimlighetskontroll och begränsning

Bryggan antar jämförbara EPS-definitioner och bevarar tidigare manuellt verifierad TTM. Ändrat vägt aktieantal, omräknade jämförelser och avrundning kan ge avvikelse mot direkt rapporterad TTM. New Waves härledda 6,5718 avviker endast 0,0018 från rapportens avrundade R12 6,57. Fyra decimaler i modellvärdet betyder inte att kvartalsuppgifterna har samma precision. Embracers historiska avvecklingar motiverar total-koncernjämförelsen; genomgången skriver inte om dess tidigare manuella historik.

## Täckning och validering

Full inventering: recent_report_eps_audit_2026-11-11.csv. EQT:s dokumenterade Q3-redogörelse utan EPS behåller tidigare TTM; VIVA är inaktiv. Rapportstatus efter komplettering ska visa noll saknade EPS, med EQT som uttryckligt undantag.

81 relevanta Python-tester och 22 gränssnittstester godkända. Befintliga kanoniska rapportposter jämförs före/efter; ordinarie pipeline, exportvalidering och historikgrind körs före publicering. Rapportdagen har ännu ingen stängningskurs vid genomgången, så nya slutliga stängningspoäng och signaler för 11 november kräver dagens slutkurs. Preliminära beräkningar ska använda nya EPS från rapportdagen.
