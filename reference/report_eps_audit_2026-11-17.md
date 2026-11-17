# Rapportkomplettering 17 november 2026

Urvalet är de tre saknade rapporterna i användarens bild: BAHN-B.ST, NIBE-B.ST och ZZ-B.ST. Bas: main be4ef3db180dfb1811de741945a00381f9240739.

| Aktie | Publicering CET | Utspädd Q3 EPS SEK | Q3 2025 SEK | Tidigare TTM SEK | Ny TTM SEK |
|---|---|---:|---:|---:|---:|
| Bahnhof, BAHN-B.ST | 17 nov 07:30 | 0,56 | 0,53 | 1,7206 | 1,7506 |
| NIBE, NIBE-B.ST | 17 nov 08:00 | 0,44 | 0,30 | 1,3140 | 1,4540 |
| Zinzino, ZZ-B.ST | 17 nov 08:00 | 3,05 | 2,35 | 10,9755 | 11,6755 |

Ordinarie metod: föregående manuellt verifierad TradingView TTM + aktuell utspädd kvartals-EPS - samma kvartal föregående år. Tidigare manuella värden bevaras. Officiella jämförelser sparas som manualDilutedEPS med företräde framför Yahoo; befintliga Yahoo-observationer bevaras. Alla tre rapporterar och handlas i SEK; ingen valutaomräkning. Periodslut 2026-09-30, modellperiod 2026-Q3, effective_date 2026-11-17.

## Officiellt underlag

- Bahnhof: https://mb.cision.com/Main/1351/4425144/4374718.pdf sida 17, koncernens resultaträkning: resultat per aktie efter utspädning 0,56 (0,53). Samma värden före utspädning. Publicering 17 november 07:30: https://news.cision.com/se/bahnhof/r/bahnhofs-delarsrapport-q3-2026,c4425144 . Rapportens signeringsdatum 16 november är inte publiceringsdatum. Norges avyttring skedde efter kvartalsslut; inget proforma- eller justerat EPS används.
- NIBE: https://storage.mfn.se/ca4cb3d5-4a41-4b83-b8df-98e13e1f0bf4/nibe-q3-report-2026-se.pdf sida 10: nettovinst per aktie före och efter utspädning 0,44 (0,30). Ojusterad R12 anges som 1,45. Rubrikens justerade R12 1,53 används inte. Publicering 17 november 08:00 enligt bolagets nyhetssida https://www.nibegroup.com/sv/nyheter .
- Zinzino: https://mb.cision.com/Main/10976/4425293/4375283.pdf sida 21 och not 4 sida 33: utspädd EPS 3,05 (2,35). Pressmeddelandets basic EPS 3,10 (2,47) används inte. Publicering 17 november 08:00: https://news.cision.com/se/zinzino/r/zinzino-ab--publ--delarsrapport-q3-2026,c4425293 .

## Rimlighetskontroll och begränsning

Bryggan antar jämförbara kvartalsmått och bevarar tidigare manuellt verifierad TTM. Den är inte identisk med att räkna om hela R12 med senaste vägda aktieantal; ändrat aktieantal och avrundning kan ge avvikelser, särskilt för Zinzino. NIBE:s härledda 1,4540 ligger nära rapportens ojusterade avrundade R12 1,45. Fyra decimaler i modellvärdena innebär inte att kvartalsuppgifterna har samma precision.

Vid morgonens komplettering saknas dagens slutkurs. Slutliga poäng och exekverade signaler före rapportdagen ska därför bevaras; dagens slutliga poäng skapas först med avslutad handelssession enligt ordinarie körning.

## Validering

47 relevanta Python-tester och 14 gränssnittstester godkända. Samtliga tidigare kanoniska rapportposter är oförändrade efter de tre tilläggen. Ordinarie byggning, exportvalidering och historikgrind körs före publicering.
