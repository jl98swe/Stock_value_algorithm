# Rapportkomplettering 10 november 2026

Bas: main 825efee09423081c50fae902ce99cac0f5330d21. Samtliga 119 tickers inventerade mot kanoniska rapporter, aktuell kalender och kalenderhistorik. Föregående genomgång 6 november (Attendo, BTS och Fenix) bevaras. Inaktiv VIVA ingår i inventeringen men räknas inte som förfallen rapport.

| Aktie | Officiell publicering CET | Utspädd kvartals-EPS SEK | Q3 2025 SEK | Tidigare TTM SEK | Ny TTM SEK |
|---|---|---:|---:|---:|---:|
| Genovis, GENO.ST | 10 nov 08:00 | 0,06 | 0,12 | 0,3101 | 0,2501 |
| Scandic, SHOT.ST | 10 nov 07:30 | 3,02 | 2,59 | 3,3747 | 3,8047 |

Befintlig metod: föregående manuellt verifierad TradingView TTM + aktuell diluted kvartals-EPS − samma kvartal föregående år. Alla tidigare kanoniska EPS-värden bevaras. Endast två nya rapportperioder tillkommer. Båda bolagen rapporterar och handlas i SEK; ingen valutakonvertering behövs. Publicering före börsöppning ger effective_date 10 november. Verifierade klockslag lagras separat i report_publications.csv.

## Källor och definitioner

Genovis officiella rapport: https://storage.mfn.se/806642c9-5924-41ca-ae40-17c6b17e5198/genovis-kvartalsrapport-januari-september-2026.pdf . Sida 6, fotnot 5, anger att ingen utspädningseffekt föreligger. Sida 15 visar kvartalets resultat per aktie 0,06 (0,12); fotnoten på sida 16 anger före och efter utspädning. Ojusterad kvartals-EPS används. Justerad niomånaders-EPS 0,20 används inte. Publicering 08:00 CET enligt bolagets regulatoriska meddelande: https://investor.genovis.com/sv/mfn_news/delarsrapport-januari-september-2026/ .

Scandic officiella rapport: https://www.scandichotelsgroup.com/files/Main/13379/4422204/scandic-q3-report-2026-en.pdf . Sida 20, koncernens resultaträkning, anger EPS efter utspädning 3,02 (2,59) SEK inklusive IFRS 16. Rubrikvärdet 3,86 exklusive IFRS 16 används inte. Sparad Yahoo-härledd jämförelse 2,57 ersätts i bryggans prioritering med manuellt verifierad 2,59; rå Yahoo-observation bevaras. Direkt rapporterad avrundad TTM 3,81 stöder bryggans 3,8047. Befintlig manuell Q2-TTM ändras inte. Publicering 07:30 CET enligt bolaget: https://www.scandichotelsgroup.com/media/press-releases/2026/good-growth-strong-results-and-cashflow-next-step-in-growth-journey/ .

## Rimlighetskontroll

Kvartalsbryggan antar jämförbara EPS-definitioner. Avrundning och ändrat vägt aktieantal kan ge en mindre skillnad mot direkt rapporterad TTM; fyra decimaler i modellvärdet innebär inte motsvarande noggrannhet i rapportens kvartalsvärden. För Scandic är skillnaden mot rapporterad TTM 0,0053 SEK. Genovis har nyemission i Q2, men ingen utspädningseffekt enligt rapporten; tidigare manuella värden och projektets etablerade brygga behålls.

## Täckning och validering

Inga förfallna EPS-luckor efter kompletteringen. EQT:s Q3-redogörelse 15 oktober saknar EPS enligt tidigare verifierat undantag; äldre TTM behålls. Full tickerinventering: recent_report_eps_audit_2026-11-10.csv.

57 relevanta Python-tester godkända: manuell inmatning, senaste rapport-EPS, rapportvarningar, publiceringstid, valuta, TradingView-prioritet och datumrättelser. Pipeline och historikgrind verifieras före merge. Vid körning före dagens stängning kan inga nya slutliga poäng eller slutliga stängningssignaler för 10 november skapas utan dagens slutkurs; befintlig preliminärberäkning ska använda nya EPS från rapportdagen.
