# Rapportkomplettering 30 oktober 2026

Utgångspunkt: main 5d799b34068ef5b24c8f2089b751e2bfff6c0ddb. Universum: 119 tickers. Samtliga förfallna kalenderhändelser och rapporter i senaste 20 handelsdagarnas webbexport kontrollerades mot kanoniska rapporter och manuella kontroller. Inventeringen innehåller 92 poster: 86 redan kompletta, fyra undantagna från senaste EPS-chatten (Boliden, Nolato B, Sweco A/B), en ny registrering och en valutakontroll. Dagens externa rapportkalendrar stämmer med två nya rapporter i vårt universum: Loomis och AstraZeneca. Övriga bolag i dessa dagslistor ingår inte i universumet. EQT:s redogörelse utan EPS är ett tidigare dokumenterat undantag.

| Aktie | Publicering CET | Föregående manuell TTM | Diluted Q3 2026 | Diluted Q3 2025 | Ny TTM |
|---|---|---:|---:|---:|---:|
| Loomis | 30 oktober 07:30 | 27,5825 SEK | 10,26 SEK | 7,77 SEK | 30,0725 SEK |
| AstraZeneca | 30 oktober 08:00 | 64,3345 SEK | 2,00 USD | 1,62 USD | Ej registrerad: valutakonflikt |

## Loomis

Officiell rapport, s. 1 och 10: https://mb.cision.com/Main/51/4417527/4346980.pdf . Publicering: https://news.cision.com/loomis-ab/r/loomis-interim-report-january---september-2026,c4417527 . Rapporten anger diluted 10,26 (7,77), till skillnad från basic 10,31 (7,80). Verifierade kvartalskomponenter sparas som manualDilutedEPS. Jämförelseperiodens historiska publiceringsdatum gissas inte. Den tidigare härledda Yahoo-komponenten 7,79 bevaras men den officiella manuella 7,77 får prioritet.

Befintlig regel används: 27,5825 + 10,26 − 7,77 = 30,0725 SEK. Detta är en härledning från tidigare manuell TradingView-bas, inte en ny TradingView-avläsning. Ingen valutaomräkning.

Rimlighetskontroll: rapportens direkt redovisade diluted R12 är 30,03 SEK. Antagandet att en kvartalsbrygga exakt motsvarar direkt R12 kan vara fel vid ändrat vägt aktieantal och avrundning. Skillnaden här är 0,0425 SEK (cirka 0,14 procent); befintlig metod behålls och skillnaden dokumenteras.

## AstraZeneca

Officiell rapport, s. 26: https://www.astrazeneca.com/content/dam/az/PDF/2026/9mq3/9M-and-Q3-2026-results-announcement.pdf . Tabellen anger diluted EPS per ordinarie aktie 2,00 (1,62) USD. Basic 2,02 (1,64) och Core 2,79 används inte. Publicering 07:00 GMT/08:00 CET verifierad via https://www.astrazeneca.com/investor-relations/9m-and-q3-2026-results-event.html .

De två verifierade kvartalskomponenterna sparas i USD och kontrollen markeras currency_verification_pending. Den tidigare manuella TradingView-basen 64,3345 SEK lämnas oförändrad. Funktionen derive_manual_eps_ttm_safe stoppar blandningen av SEK och USD. Ingen godtycklig valutakurs eller nytt TTM-värde registreras; varningen för saknad ny EPS ska kvarstå. TradingViews publika resultaträkning visar inte ett verifierbart aktuellt Q3-TTM i den hämtade versionen. En ny verifierad diluted TTM i SEK krävs för att slutföra denna post inom den befintliga manuella metoden.

## Tidigare poster och verifiering

Samtliga 101 tidigare manuella registreringar, 2 128 kvartalsposter och 3 835 rapportposter jämfördes som hela rader mot utgångsläget och bevarades. En manuell rapportregistrering, fyra kvartalskomponenter och två granskningsposter tillkommer. ABB/Eastnines äldre valutauppföljning och historiska datumluckor kvarstår separat.

Rapport- och inmatningsgränssnittets 17 JavaScript-tester passerade. Den första Python-körningen gav 386 godkända tester och ett tidigare inaktuellt schematest: main hade ändrat Avanza från 18:30 till 17:30 utan att uppdatera förväntningen. Testets förväntade tid rättas till det befintliga schemat; ingen schemaläggning ändras här.

Webbdata byggs med ordinarie pipeline --skip-fetch --skip-dividends, följt av limit_dashboard_window, validate_outputs och report_data_status. Senaste tillgängliga slutkurser är 29 oktober. Rapportdagens slutliga poäng och signaler kan därför skapas först när slutkurser för 30 oktober finns; ingen framtida kurs eller signal fabriceras. GitHub Actions och Pages verifieras efter merge.

Kalenderkontroller: https://borssidor.se/rapportkalender och https://www.borskollen.se/nyheter/27/fran-rapportkalendern-har-ar-bolagen-som-rapporterar-idag-1793335500 .
