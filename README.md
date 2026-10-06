# Stock Value Algorithm

Dagligt uppdaterad värderings- och signalpipeline för svenska aktier. Webbgränssnittet publiceras statiskt från `docs/` via GitHub Pages.

## Daglig körning

GitHub Action `Daglig marknadsuppdatering` kör cirka 17:30 Europe/Stockholm på handelsdagar och gör i ordning:

1. hämtar nya OHLCV-priser från Yahoo Finance,
2. kombinerar den frysta prisbasen med löpande uppdateringar,
3. räknar MA200 per ticker på hela prisserien,
4. uppdaterar utdelningshändelser,
5. applicerar verifierad point-in-time EPS TTM när sådan finns,
6. beräknar värderingsscore med 100-trädsmodellen för positiv P/E och v3.01:s separata 30-trädsmodell för negativ P/E,
7. applicerar fundamentala handelsspärrar,
8. simulerar köp/sälj enligt nästa handelsdags öppning,
9. bygger `docs/data/*.json`,
10. validerar resultatet innan data får committas.

Kör lokalt:

```powershell
python -m src.pipeline
python -m src.validate_outputs
```

### Säker publicering av data

Alla skrivande GitHub Actions-jobb delar en kö per gren (`stock-data-${{ github.ref }}`).
De körs ett i taget, hämtar grenens senaste innehåll efter väntan och sparar tillbaka
till samma gren. `queue: max` låter flera väntande jobb behållas utan att ersätta
varandra. En samtidig manuell ändring kan fortfarande ge en konflikt; då stoppas
sparningen i stället för att någon version skrivs över.
Automatiska datasparande push-körningar startar bara på `main`; arbetsgrenar
testas via pull request och kan fortfarande få en manuellt startad datakörning.

Nyhetsjobbet schemaläggs 18:05 i `Europe/Stockholm`. Det kontrollerar inte att
GitHub faktiskt startar exakt den minuten, eftersom schemalagda jobb kan försenas.
Datum för nyhetskörningar ska kontrolleras i `data/news/status.json`, inte bara
genom att se att workflowen är grön.

EPS-jobb bygger webbdata efter sista rapportändringen och sparar rapportfliken,
rapportmarkörer och aktiesidornas data tillsammans. Marknads-/EPS-byggen bevarar
publicerade nyheter även om rånyhetscachen saknas; bara nyhetsflödet tar bort
nyheter. Valideringen stoppar publicering om senaste rapporten, rapportmarkörerna,
rapportfliken eller de separata aktiefilerna inte stämmer med samma underlag.
Detta verifierar intern konsistens, inte att Yahoo har publicerat alla bolagsrapporter.

## Prisdata

Fryst historik:

```text
data/prices/prisdata_initial.parquet
```

Löpande uppdateringar:

```text
data/prices/price_updates.csv
```

Schema:

```text
date, open, high, low, close, volume, ticker, ma200
```

`ma200` är ett enkelt 200-handelsdagars medelvärde av ojusterad `close`, räknat på basfil + samtliga senare uppdateringar.

Endast avslutade börsdagar på Nasdaq Stockholm används. Börskalenderns stängning
(även halvdagar och sommar-/vintertid) styr både hämtning och läsning av sparad
prishistorik. En manuell körning mitt på dagen får därför inte använda dagens
pågående dagsstapel för poäng eller signaler.

## Fundamentaldata

Kanonisk rapportfil:

```text
data/fundamentals/reports.csv
```

Endast verifierade EPS TTM-rader med explicit `effective_date` används. Rapport- och låslogiken följer rapportdatumet. För tickers som kalibreras mot TradingView placeras den kända EPS-punkten däremot på `period_end` i värderingsmotorns interna tillstånd. Publicerade poäng lagras separat och är oföränderliga: en ny rapport kan påverka rapportdagen och senare handelsdagar, men skriver aldrig om tidigare visad historik. Signaler räknas från samma frysta poängserie.

Enstaka verifierad rapport kan läggas in med:

```powershell
python -m src.add_report `
  --ticker ESSITY-B.ST `
  --report-period 2026-Q2 `
  --period-end 2026-06-30 `
  --published-at 2026-07-17T07:00:00+02:00 `
  --effective-date 2026-07-17 `
  --eps-ttm 12.34 `
  --source "Bolagets rapport"
```

Köpt historisk point-in-time-data importeras med:

```powershell
python -m src.import_history --input <fil> --mapping config/history_import_mapping.yml
```

Import stöder CSV, XLSX/XLS och JSON. Mappningen justeras när leverantörens faktiska exportformat är känt.

## Värderingsmodell

`src/valuation.py` är Python-porten av Pine v3.0. Den exakta GBM-modellen ligger versionshanterad i sex Base85-delar under `data/model/` och materialiseras/valideras av `src/model_data.py` före användning.

Strategiregler:

- score klipps till 0–100,
- köp när score passerar under 1,
- sälj när score passerar över 99,
- signalen beslutas på stängningskurs och exekveras nästa handelsdags öppning,
- högst en aktiv position per aktie,
- minst fem handelsdagar mellan köp respektive mellan sälj,
- samma gräns måste lämnas och återbesökas innan ny signal,
- ingen blankning.

## Rapporter och nyheter

Manuella eventgranskningar:

```text
data/manual/event_reviews.json
```

Rapportkalender:

```text
data/manual/report_calendar.csv
data/earnings/report_calendar.csv
data/earnings/report_calendar_history.csv
```

Den automatiska kalendern körs separat från marknadsuppdateringen: Börskollen
på lördagar och Yahoo Finance på söndagar. Källorna sparas separat och
Börskollen prioriteras när båda anger samma datum. Bara Börskollen-poster som
matchar strategins tickeruniversum sparas. Den manuella kalendern fortsätter
att styra verifierade rapporthändelser och handelsspärrar. Misslyckas en
kalenderhämtning behålls den senast lyckade observationen.

Från ett registrerat rapportdatum kontrollerar vardagsjobbet Yahoo för ny EPS
TTM och jämförbar kvartals-EPS. Kontrollen fortsätter tills en ny rapportperiod
har registrerats, dock högst i 45 dagar. Därmed görs inte längre EPS-anrop för
hela aktieuniversumet varje dag.

Rapportfliken visar de kommande tio handelsdagarna på Nasdaq Stockholm samt
nyligen rapporterade bolag. En prognos visas bara när måttet är verifierat som
jämförbar kvartalsvis utspädd EPS. Yahoos generiska EPS-estimat märks därför som
ej jämförbart och används inte för att prognostisera EPS TTM eller score.

Ogranskad regulatorisk information kan sätta handelsspärr. Vinstvarningar, omvända vinstvarningar och preliminära resultat ändrar inte EPS automatiskt. Spärren ligger kvar tills riktig rapporterad EPS har verifierats.

## Utdelningar

Fryst historik:

```text
data/dividends/dividends_initial.csv
```

Löpande uppdateringar:

```text
data/dividends/dividend_updates.csv
```

Utdelningar används som `D`-markörer i grafen och ändrar inte värderingsscoren.

## Webbdata

GitHub Pages läser främst:

```text
docs/data/stocks.json
docs/data/dashboard.json
docs/data/events.json
docs/data/reports.json
```

`events.json` använder `E` för rapport, `D` för utdelning och `N` för bolagsnyhet i frontend.

## Negativ vinst (v3.01)

Alla modeller använder diluted EPS TTM från befintliga verifierade rapporter.
Vid P/E < 0 används `data/model/negpe_gbm_model.json`: 30 träd, 390 noder
och sex features i Pine-ordning: klippt GapPct + 50, klippt AvvRaw + 50,
abs(P/E), femdagarsförändring i P/E, 20-dagars standardavvikelse (ddof=0)
och position i 60-dagarsintervallet. Resultatet klipps till 0–100.
Saknade features ger ingen poäng. Positiv P/E
behåller den tidigare 100-trädsmodellen och dess ursprungliga gap/lagg-villkor.
`CanRunGBM` anger om vald modell kan köras; `CanRunPositivePEGBM`,
`CanRunNegPEGBM`, `NegPEScore` och `ValuationModel` finns i beräkningsresultatet.

Den sparade referensen `reference/test_vard_algo_3_01_diluted.pine` använder
diluted EPS TTM. Dess positiva 80-trädsmodell och linjära fallback har **inte**
förts över till webbappen. Den negativa modellens träningsprecision enligt
källfilen är lägre (LOSO MAE 7,11); HUFV/CAST anges som svåra fall. Portningen
är verifierad mot träd-arrayerna, men ingen oberoende kontroll av verkliga
TradingView-värden med diluted EPS har gjorts.

Engångsmigrering av fryst historik:

```bash
python -m src.migrate_negative_pe_scores --workers 4
python -m src.pipeline --skip-fetch --skip-dividends
python -m src.validate_outputs
```

Migreringen använder bara rapporter kända vid respektive effective_date,
med samma rapport-/periodslutsläge som den aktuella aktien. Den ersätter endast
negativa EPS-perioder och kontrollerar att alla övriga frysta poäng är exakt
oförändrade. Äldre negativa poäng utan tillräckliga modellfeatures tas bort.
Signaler och backtest räknas sedan från den uppdaterade frysta serien.
Migreringen ska inte köras automatiskt i den dagliga uppdateringen.


### Metod och alternativa backtest

Fliken Metod jämför Standard, MA200 (endast köp över MA200) och
Rapportundvikande (inga köp inom 10 börsdagar före rapport, försäljning vid
öppningen börsdagen före rapport) med Buy and hold och OMXSGI. De tre
signalstrategierna använder strikt Score < 1 / > 99,
en aktiv position, befintlig cooldown och nettoresultat med utdelning och courtage.
Backtestdata byggs automatiskt av pipeline till `docs/data/backtests/{ticker}.json`.
Rapportinsamlingen ändras inte. Historiken använder slutliga rapportdatum;
saknas publiceringsdatum används effective_date. Saknas nästa rapportdatum
blockeras köp i Rapportundvikande.

Perioderna sedan start och senaste 1/3/5 åren inkluderar endast affärer där
både köp och sälj ligger i perioden. Öppna positioner köpta inom perioden
redovisas separat som preliminära. Avslutade affärers sammansatta resultat
är inte portföljens periodavkastning när äldre positioner utesluts.

Kontroller: `python -m pytest -q`, `node tests/test_method_periods.cjs` och
`node tests/test_method_ui.cjs` (Playwright med Chromium).

Metod visar alla aktier som förval, med lika kapitalandel per aktie.
Resultat från samtidiga affärer multipliceras inte mellan aktier: varje akties
avslutade affärer återinvesteras inom aktien och utvecklingen vägs sedan samman.
Öppna positioner visas separat. `docs/data/backtests/all.json` byggs vid varje
pipeline-körning och kan byggas separat med `python -m src.aggregate_backtests`.
Enskild aktie kan fortfarande väljas, inklusive länkar från Historik.
Metodbeskrivningen är hopfälld med Visa mer/Visa mindre.

Buy and hold köper vid första tillgängliga stängningen inom vald period och
säljer vid den sista, med 0,25 % courtage per sida och kontantutdelningar.
Startkapitalet fördelas lika över aktierna utan löpande ombalansering. En aktie
utan två kurser behåller sin andel i kontanter.

OMXSGI använder Nasdaq OMX Stockholm All-Share Gross Index, inklusive
återinvesterade utdelningar före skatt, utan courtage eller fondavgifter.
`python -m src.index_benchmark` hämtar dagliga observationer från Nasdaq via
FRED (`NASDAQOMXSGI`) till `docs/data/benchmarks/omxsgi.json`; vanliga
prisuppdateringar kör detta automatiskt. XSTO-handelsdagar och endast färdiga
sessioner används. Ett misslyckat anrop behåller senaste giltiga export;
indexets faktiska datumintervall visas på sidan.

Sharpekvoten beräknas från den dagliga kapitalutvecklingen med 0 % riskfri
ränta: medelavkastning / standardavvikelse (stickprov) × sqrt(252). Den
inkluderar dagar i kontanter och använder samma netto-kapitalutveckling som
resultat och största nedgång. Öppna positioner utesluts för signalstrategierna.
För alla aktier beräknas Sharpe på den sammanvägda kapitalutvecklingen, inte
som ett genomsnitt av aktiernas Sharpe. Färre än två dagliga avkastningar eller
ingen variation ger ett streck.

### Rapportdatum: efterkontroll och korrigering

Vardagsjobbet kontrollerar rapportdatum direkt och efter 7 och 14 kalenderdagar,
även när EPS-värdet är oförändrat. Körningen använder första vardagskörningen
som faktiskt startar efter respektive gräns. Misslyckad eller tvetydig hämtning
försöks igen inom 45 dagar; befintligt datum lämnas kvar. En rapport måste ha
rapporterad EPS och ligga nära samma rapporthändelse för att få korrigera datumet.
Yahoo-tidsstämplar tolkas i Europe/Stockholm. Rapporter efter börsstängning,
på helger eller halvdagar använder nästa börssession som effective_date.

Datum som verifierats manuellt i `report_date_overrides.csv` har företräde
framför automatisk datumkontroll. EPS och datum har separata källprioriteringar:
manuell EPS behålls även när ett automatiskt rapportdatum korrigeras.
Manuell kommande kalender prioriteras även vid konflikt mellan närliggande datum.

`report_date_check_state.json` sparar utförda efterkontroller,
`report_date_checks.csv` loggar utfall, `report_date_score_revisions.csv` loggar
ombyggda datum och `report_date_status.json` visar saknade
historiska datum, saknade kommande kalenderdatum och konflikter mellan källor.
Grön körning innebär därför inte att alla rapportdatum är verifierade.
Saknade historiska datum fylls inte med gissningar.

Pipeline jämför rapporterna med `data/derived/report_score_dates.csv` från
senaste slutliga poängbygget. När datum flyttas räknas endast den berörda aktien
om från det tidigare av gammalt och nytt effective_date. Dagar före gränsen
behålls exakt. Även nya tidigare saknade datum och borttagna rapporter upptäcks.
Signaler, rapportmarkörer, aktiefiler och backtest byggs från samma korrigerade
underlag. Förberedande byggen med `--defer-score-history` konsumerar inte ändringen.

Aktiva positioner och Kommande signaler har en strategiväljare överst för
Standard, MA200 och Rapportundvikande. Valet sparas mellan sidorna och kan
delas med `?strategy=ma200` eller `?strategy=report_avoidance`. Pipeline
exporterar oberoende modellpositioner, väntande åtgärder, strategifilter och
exekverade signaler till `docs/data/strategy_overviews.json`. De senaste
signalerna filtreras mot samma tjugo handelsdagar för alla strategier. Köp som
blockeras av MA200 eller rapportfiltret visas inte som kommande köp. Planerade
rapportsälj visas oavsett poäng och reaktivering, med undantag för fundamental
spärr angivet. Aktiva rapportpositioner visar sista planerade säljdatum.

Rapportfiltrets senaste stängning kontrollerar även nästa XSTO-session, så att
ett köp kan planeras utan att någon framtida kurs behöver finnas i underlaget.
Kontroller för översikterna: `node tests/test_overview_strategy.cjs` och
`node tests/test_overview_ui.cjs` (Playwright med Chromium).

Startsidan, Aktiva positioner, Kommande signaler och Metod delar strategivalet Standard/MA200/Rapportundvikande. Valet sparas i webbläsaren och följer med i sidornas navigationslänkar; ett uttryckligt URL-val har företräde. Buy and hold och OMXSGI i Metod ändrar inte det sparade valet av egen strategi. Startsidan visar vald strategis modellposition, nästa åtgärd, samtliga historiska köp/sälj i grafen och historik. Backtestets avslutade affärer redovisas separat från öppna positioner.

Aktievalet sparas också i webbläsaren och följer med via navigationen, inklusive översikter och Rapporter. Startsidan, Metod och Granska nyheter och data använder samma senast valda aktie. Ett uttryckligt ticker-val i URL har företräde. Metods ”Alla aktier” behåller senast valda enskilda aktie för övriga sidor; utan tidigare aktieval öppnas Metod fortfarande med alla aktier.

Kommande signaler bevakar högst 10 poäng från 1/99. Rapportundvikande tar även med öppna positioner när rapporten är högst fem XSTO-börsdagar bort, med försäljningsdatum föregående börsdag. Poängsälj ersätts av den planerade rapportsäljningen i listan, medan utförda signaler förblir oförändrade.

`signal_prices.json` uppdateras av pipelinen: nästa XSTO-stängning simuleras med oförändrad EPS och hela historiken. Närmaste funna övergång över/under 99/1 söks på ett numeriskt rutnät mellan 0,25 och 4 gånger senaste kursen och förfinas på signalsidan av gränsen. Det är en ungefärlig lokal gräns; fler intervall och smala intervall mellan rutnätspunkterna kan finnas. Ingen gräns hittad visas som streck. Gränser vars datum inte matchar strategins senaste kurs visas inte. Handelsregler och nästa öppningskurs gäller fortsatt.
