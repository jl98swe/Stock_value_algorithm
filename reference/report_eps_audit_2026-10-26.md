# Rapportkontroll 26 oktober 2026

Utgångspunkt: aktuell `main` `bd9a1772c2b2e71d6e4ac636251be63024c41480` och den publicerade rapportstatusen från 25 oktober. Samtliga 119 bevakade aktier har inventerats mot rapportkalendern, tidigare kontroller och kanoniska rapporter. När kontrollen gjordes hade ingen ny bevakad rapport publicerats efter den 23 oktober. Alleima är schemalagd den 26 oktober men bolaget har meddelat publicering först cirka 11.30 CET; den behandlas därför inte som publicerad i denna körning.

## Uppdatering

| Aktie | Period | Rapportdatum | Tidigare värde | Ny diluted EPS TTM | Valuta | Källa |
| --- | --- | --- | ---: | ---: | --- | --- |
| COOR.ST | 2026-Q3 | 2026-10-22 | 2,80 | 2,78 | SEK | TradingView / EARNINGS_PER_SHARE_DILUTED TTM, användarverifierat 2026-10-26 |

COOR-värdet lagras direkt i SEK utan valutaomräkning och med manuell prioritet. Det ersätter rapportens avrundade R12-värde 2,80 SEK. Den tidigare manuella posten behålls i granskningshistoriken, medan den kanoniska Q3-posten uppdateras till 2,78 SEK och får korrekt effective_date 2026-10-22. En felaktig automatisk datumkontroll som hade satt 2026-10-21 överstyrs med den verifierade publiceringsdagen. Senare manuella korrigeringar ska fortsatt prioriteras framför Yahoo.

## Kvarstående lucka

- **HPOL-B.ST:** [HEXPOL:s officiella Q3-rapport](https://storage.mfn.se/9f928247-64ce-434d-a0e7-a4b1b3b6fefd/hexpol-interim-report-january-september-2026.pdf), s. 11, anger ojusterad EPS R12 5,25 SEK och Q3 1,30 (1,35). Rapporten identifierar inte måttet uttryckligen som efter utspädning. Ett aktierelaterat incitamentsprogram finns beskrivet i rapporten. Värdet registreras därför inte som verifierad diluted EPS TTM. Befintlig TradingView Q2-bas 5,3072 SEK behålls och ingen kvartalsbrygga används.

## Valutaproblem – manuell hantering

| Ticker | Problem | Berörda valutor | Tidigare omräkning | Källa |
| --- | --- | --- | --- | --- |
| ABB.ST | Q3-värdet är härlett från rapportens avrundade USD-komponenter och behöver jämföras med ett nytt TradingView-värde i noteringens presentation. | USD → SEK | 2,75 USD lagras och omräknas till SEK av befintlig värderingslogik. | [ABB Q3 2026, s. 1 och 8](https://www.eqs-news.com/news/category/abb-ltd-q3-2026-results/50d2285d-3931-4dd6-87c9-175ebf9be15a) |
| EAST.ST | Rapporten redovisar direkt diluted R12 i EUR, medan tidigare manuella TradingView-värden var i SEK. Ett nytt TV-värde behövs för kontroll. | EUR → SEK | 0,31 EUR lagras och omräknas till SEK av befintlig värderingslogik. | [Eastnine Q3 2026, s. 23](https://mb.cision.com/Main/13001/4413938/4334001.pdf) |

Tidigare valutafall för Nordea, Betsson, Autoliv, Evolution och Hexagon är lösta genom användarverifierade TradingView-värden i SEK och räknas därför inte som kvarstående valutaproblem. Inga nya valutaomräkningar görs i denna körning.

## Bevarade beslut

Pausade TradingView-verifieringar för Avanza, Investor A, Platzer B och Ericsson förblir pausade. EQT:s undantag för redogörelse utan EPS behålls. Alla tidigare manuella EPS-värden är oförändrade.

## Validering

Samtliga 3 821 tidigare kanoniska rapportperioder bevaras; endast COOR:s befintliga 2026-Q3-post ersätts. En ny manuell granskningspost läggs till och den tidigare rapportbaserade posten behålls som historik. Poänghistoriken har samma 197 304 rader. Endast COOR den 21–23 oktober ändras: den 21 oktober återställs till data före rapporten eftersom rapporten faktiskt publicerades den 22 oktober, och den 22–23 oktober räknas om med 2,78 SEK. Alla andra ticker-/datumrader och all historik före den 21 oktober är exakt oförändrade. Senaste poäng den 23 oktober ändras från 22,1140 till 24,1316; ingen ny handelssignal uppstår.

351 Python-tester och sex relevanta JavaScript-tester för rapporttabeller och EPS-varningar passerar. Pipeline, begränsning av dashboard och full utdata-/valutavalidering är godkända för 119 aktier och 306 867 prisrader. COOR:s varning om saknad EPS är borta. HPOL-B.ST kvarstår som verklig lucka. Alleima visas tekniskt som dagens saknade värde tills rapporten publiceras cirka 11.30; vid denna kontroll hade rapporten ännu inte publicerats.
