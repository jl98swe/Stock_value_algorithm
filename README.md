# Stock Value Algorithm

Dagligt uppdaterad värderings- och signalpipeline för svenska aktier. Webbgränssnittet publiceras statiskt från `docs/` via GitHub Pages.

## Daglig körning

GitHub Action `Daglig marknadsuppdatering` kör cirka 17:45 Europe/Stockholm på handelsdagar och gör i ordning:

1. hämtar nya OHLCV-priser från Yahoo Finance,
2. kombinerar den frysta prisbasen med löpande uppdateringar,
3. räknar MA200 per ticker på hela prisserien,
4. uppdaterar utdelningshändelser,
5. applicerar verifierad point-in-time EPS TTM när sådan finns,
6. beräknar Pine v3.0-värderingsscore med den inbäddade 100-träds GBM-modellen,
7. applicerar fundamentala handelsspärrar,
8. simulerar köp/sälj enligt nästa handelsdags öppning,
9. bygger `docs/data/*.json`,
10. validerar resultatet innan data får committas.

Kör lokalt:

```powershell
python -m src.pipeline
python -m src.validate_outputs
```

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

## Fundamentaldata

Kanonisk rapportfil:

```text
data/fundamentals/reports.csv
```

Endast verifierade EPS TTM-rader med explicit `effective_date` används. Den kanoniska rapport- och låslogiken följer alltid detta datum. För tickers med manuellt verifierad TradingView-historik använder värderingsmotorns interna tillstånd i stället `period_end`, så att EPS-serien beter sig som TradingViews historiska fundamentalserie. Hela värderings- och signalhistoriken räknas om vid varje dashboardbygge med aktuella regler och aktuellt verifierat dataunderlag. När historisk EPS kompletteras kan därför även äldre poäng och signaler ändras.

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
- köp vid score 0,
- sälj vid score 100,
- signalen beslutas på stängningskurs och exekveras nästa handelsdags öppning,
- högst två köp per positionscykel,
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
```

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
```

`events.json` använder `E` för rapport, `D` för utdelning och `N` för bolagsnyhet i frontend.
