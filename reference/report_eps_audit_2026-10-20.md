# Rapport-EPS: kontroll 2026-10-20

Inventering av rapportstatus och sparade rapportkalendrar för universumets 119 aktier, med nya bolagsrapporter verifierade under morgonen. Avanza, Investor A och Platzer B undantas enligt användarens avgränsning till föregående genomgång. Inga ytterligare äldre förfallna EPS-luckor hittades i rapportstatusen. Kalendern är ett kontrollunderlag, inte ett oberoende bevis för att alla bolag publicerat enligt plan.

| Aktie | Ny rapport | Utspädd kvartals-EPS | Ny EPS TTM | Underlag |
| --- | --- | --- | --- | --- |
| ABB | Q3, publicerad 20 oktober 06:50:01 CEST | 0,65 USD | 2,75 USD | Föregående Yahoo diluted TTM 2,76 + 0,65 - verifierad jämförelseperiod 0,66. |
| Tele2 B | Q3, publicerad 20 oktober 07:00 CEST | 2,02 SEK | 14,67 SEK | 14,50 + 2,02 - verifierad jämförelseperiod 1,85. |
| Scandi Standard | Q3, publicerad 20 oktober 07:30 CEST | 1,97 SEK | 6,79 SEK | Direkt rapporterad utspädd R12, inte justerad EPS 7,01. |

Källor och noteringar finns per post i data/manual/report_data_checks.csv och data/manual/report_submissions.csv. Jämförelsekvartalen har kompletterats i quarterly_eps.csv. Periodslut är 2026-09-30; effective_date är 2026-10-20. ABB lagras i rapportvalutan USD och konverteras av befintlig valutamotor till noteringsvalutan SEK. Tvådecimaliga rapportvärden har inte fyra decimalers källprecision och kan skilja sig från TradingView.

Tidigare kanonisk Q2 EPS TTM: ABB 26,4067 SEK (manuellt TradingView-värde), Tele2 14,5075 SEK, Scandi Standard 6,6108 SEK. Dessa rapporter bevaras exakt. Nya rapporter ersätter inte historiska manuella värden.

Validering: 42 riktade tester passerade; pipeline och validate_outputs godkända för 119 aktier och 306 395 prisrader. Hela frysta poänghistoriken samt samtliga befintliga kanoniska rapporter är exakt oförändrade. Positioner och signaler för alla fem strategier är oförändrade; aktuella EPS/P-E-fält uppdateras. Senaste slutkurs är 19 oktober. Rapportdagens slutliga poäng och signaler inväntar dagens slutkurser.

Varningarna för ABB, Tele2 och Scandi Standard är borta. Kvar i rapportstatus: Lime, vars rapport annonserats till 20 oktober 07:50 men ännu inte kunde verifieras vid källkontrollen. EQT:s Q3-redogörelse saknar EPS enligt rapporteringsupplägget; tidigare EPS behålls och undantaget ligger separat.

Implementerat via PR #73. Befintlig EPS-publicering har byggt och validerat om webbdata på main.
