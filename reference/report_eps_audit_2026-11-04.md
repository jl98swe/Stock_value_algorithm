# Rapportkomplettering 4 november 2026

Utgångspunkt: main 6b69657027c54546ebf2576bd393e78eb4616103. Universum: 119 aktier. Inventeringen jämför senaste 20 handelsdagarnas rapporthändelser med kanoniska rapporter och samtliga förfallna kalenderhändelser. REJL B och AstraZeneca undantas från ny EPS-komplettering eftersom de behandlades i senaste chatten. Befintliga manuella värden bevaras. Dagens sex kalenderhändelser stämmer med Börskollens dagslista inom vårt universum: https://www.borskollen.se/nyheter/27/rapportdagen-4-november-bolagen-som-slapper-rapport-idag . Övriga bolag i listan ingår inte i universumet.

| Aktie | Publicering CET | Diluted Q3 2026 | Diluted Q3 2025 | Tidigare TTM SEK | Ny TTM SEK | Status |
|---|---|---:|---:|---:|---:|---|
| Cloetta | 4 november 07:30 | 0,86 SEK | 0,66 SEK | 2,9822 | 3,1822 | Registrerad |
| SinterCast | 4 november 08:25 | 1,74 SEK | 0,62 SEK | 2,7122 | 3,8322 | Registrerad |
| Cibus | 4 november 07:30 | 0,35 EUR | 0,23 EUR | 11,4241 | – | Valutaverifiering återstår |
| Kambi | 4 november 07:45 | 0,126 EUR | 0,036 EUR | 3,2318 | – | Valutaverifiering återstår |
| Medicover B | 4 november 07:45 | 0,169 EUR | 0,129 EUR | 6,1103 | – | Valutaverifiering återstår |
| Lundin Mining | Efter nordamerikansk börsstängning | – | – | 16,7034 | – | Ännu ej publicerad vid kontrollen |

## Registrerade värden

Cloetta: officiellt pressmeddelande https://news.cision.com/se/cloetta-ab/r/cloetta-ab-s-delarsrapport-juli--september-2026--stark-organisk-volymtillvaxt-och-lonsamhetsmalet-pa,c4419641 . Diluted 0,86 (0,66) används, inte basic 0,87. Befintlig regel: 2,9822 + 0,86 − 0,66 = 3,1822 SEK.

SinterCast: officiell koncernrapport s. 16 https://storage.mfn.se/95acdedc-174e-4994-8ef6-cfb613b4f368/interim-report-3q-2026-se-3-november-2026.pdf . Diluted koncern-EPS 1,74 (0,62), inte moderbolagets 1,58. Publicering 08:25 verifierad via https://mfn.se/a/sintercast/sintercast-delarsrapport-q3-2026 . Rapportfilens namn innehåller 3 november men offentliggörandet skedde 4 november. Befintlig regel: 2,7122 + 1,74 − 0,62 = 3,8322 SEK.

Rimlighetskontroll: kvartalsbryggan antar jämförbara perioder och EPS-definitioner. Den behöver inte exakt motsvara ett direkt redovisat R12 vid ändrat aktieantal eller avrundning. SinterCasts avrundade helårs-/niomånadersbrygga ger 3,49 + 3,29 − 2,95 = 3,83 SEK, nära 3,8322. Metoden och den tidigare manuella basen ändras inte.

## Verifierade komponenter, väntande TTM

Cibus: rapport s. 22 https://cdn.bequoted.com/media/1/abc66dbc-7b11-483a-abe2-0590b4fd1cf9/Cibus-Interim-report-Jan-Sep-2026_ENG.pdf . EPS före och efter utspädning 0,35 (0,23) EUR, efter hybridräntejustering. Jämförelsetalet 0,23 får manuell prioritet över sparade Yahoo 0,22; Yahoo-raden bevaras.

Kambi: rapport s. 1 och 15 https://storage.mfn.se/0bf62f1d-d58d-4015-b32f-cf072d186f00/kambi-group-plc-q3-2026-report.pdf . Fully diluted 0,126 (0,036) EUR, inte pressmeddelandets basic 0,128. Jämförelsetalet 0,036 får prioritet över avrundade Yahoo 0,03; Yahoo-raden bevaras. Publicering: https://www.kambi.com/investors/news-pr/kambi-group-plc-q3-report-2026/ .

Medicover: https://mfn.se/a/medicover/interim-report-july-september-2026 . Hela koncernens diluted 0,169 (0,129) EUR sparas. Kvarvarande verksamhet 0,162 (0,127) används inte som hela koncernens EPS. Direkt R12 är 0,599 EUR för hela koncernen och 0,598 EUR för kvarvarande verksamhet.

Alla tio officiella kvartalskomponenter sparas som manualDilutedEPS. För Cibus, Kambi och Medicover stoppar befintlig derive_manual_eps_ttm_safe blandningen av EUR-komponenter och tidigare manuell SEK-TTM. TradingViews publika resultaträkningar gav inte verifierbara aktuella Q3-värden. Behåll tidigare kanoniska värden och varningar. Det som återstår är verifierad aktuell diluted TTM i SEK; ingen provisorisk omräkning eller metodändring görs.

Lundin Mining: https://www.lundinmining.com/news/lundin-mining-provides-third-quarter-2026-results-conference-call-and-webcast-details anger publicering efter nordamerikansk stängning 4 november. Ny EPS kan ännu inte verifieras. Kalenderdatum lämnas oförändrat, och befintlig datumstyrd varning får kvarstå.

EQT:s tidigare dokumenterade redogörelse utan EPS kvarstår som undantag. ABB, Eastnine, AZN, REJL och övriga tidigare manuella värden ändras inte.

## Beräkningar och verifiering

Ordinarie pipeline körs med --skip-fetch --skip-dividends, följt av limit_dashboard_window, validate_outputs och report_data_status. Senaste sparade slutkurser vid start är 3 november: dagens slutliga rapportdagspoäng och slutliga signaler kan först skapas när dagens slutkurser finns. Historik, strategier och webbexport räknas om enligt befintliga regler, inklusive automatisk invalidation av tidigare beräknade poäng när EPS-underlaget ändras.
