# Fundamentaldata

`reports.csv` är den kanoniska point-in-time-källan för EPS TTM. Endast verifierade rader i den filen får påverka P/E, värderingsscore eller signaler.

## Kanoniskt schema

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `period_end` | Rapporteringsperiodens slutdatum |
| `report_period` | Stabil periodetikett, t.ex. `2026-Q2` |
| `published_at` | När rapporten blev offentlig, med tidszon när exakt tid finns |
| `effective_date` | Datum då denna EPS TTM börjar användas av algoritmen |
| `eps_ttm` | Verifierad EPS TTM i bolagets rapportvaluta |
| `source` | Var siffran verifierades |
| `verified` | `true` endast när posten får användas |
| `verified_at` | Tidpunkt för verifiering |
| `notes` | Fri kommentar/audit trail |

## Same-day-regel för EPS

`period_end` och `effective_date` är två helt olika saker. Algoritmen använder aldrig en rapport före dess rapportdatum.

Projektets fasta regel är att ny EPS TTM gäller **samma svenska kalenderdag som rapporten publiceras**. Exempel: ett Q2 som slutar 30 juni men publiceras 17 juli får börja påverka P/E och värderingsscore med stängningskursen den 17 juli. Vi flyttar alltså inte EPS till nästa handelsdag beroende på exakt publiceringstid.

För historik där bara `report_date` finns sätts därför `effective_date = report_date`. Vid manuell verifiering härleder `src.add_report` automatiskt `effective_date` från `published_at` i tidszonen `Europe/Stockholm` och accepterar inte ett avvikande explicit datum.

Detta är en medveten modellregel. Den förenklar point-in-time-hanteringen men kan i undantagsfall innebära att en rapport som faktiskt publicerades efter börsstängning ändå räknas från samma dags stängning.

## Aktuell Yahoo EPS TTM

Den dagliga Action-körningen hämtar direkt Yahoo `trailingEps`. Kvartals-EPS summeras inte.

Aktuella snapshot-värden lagras separat enligt samma mönster som pris och utdelning:

```text
data/earnings/earnings_initial.csv
data/earnings/earnings_updates.csv
```

`earnings_initial.csv` bootstrappar den första lyckade aktuella snapshoten och lämnas därefter orörd. När Yahoo senare visar ett annat EPS TTM-värde sparas det som en ny rad i `earnings_updates.csv` med den dag då systemet först observerade ändringen.

Yahoo-snapshoten är ett kontroll- och uppdateringsunderlag. Historiska och exekverbara värden kommer fortsatt från verifierade poster i `reports.csv`.

## Valuta

EPS lagras i bolagets ursprungliga rapportvaluta. Aktiens handelsvaluta och rapportvaluta finns i `data/metadata/stocks_yahoo.csv`.

Om valutorna skiljer sig konverteras EPS till aktiens handelsvaluta **innan** P/E beräknas. Valutahistoriken ligger i `data/fx/` och hämtas från Yahoo. Exempelvis används `USDSEK=X` för USD -> SEK och `EURSEK=X` för EUR -> SEK.

För att undvika look-ahead används den senaste fullt avslutade FX-dagskursen före aktiedagen. Den rapporterade siffran bevaras samtidigt som `EPS_TTM_RAW`; den valutajusterade serien används som `EPS_TTM` i värderingen. Om ett nödvändigt valutapar saknas får systemet inte behandla två olika valutor som om de vore samma.

## Historisk EPS

Det lokala underlaget lagras först i `data/fundamentals/eps_ttm_history.csv`. `src.enrich_historical_eps` mappar tickers och kompletterar rapportdatum. Verifierade datumöverrides appliceras där Yahoo-historiken är ofullständig. Därefter importerar `src.import_enriched_eps` den berikade serien till `reports.csv` med same-day-regeln.

Det samlade arbetsflödet finns i GitHub Actions-workflowet **Komplettera historisk EPS**. Det kontrollerar även valutahantering, historisk P/E/score/strategi och jämför senaste Yahoo EPS TTM med den senast uppladdade historiska EPS-raden.

## Ny verifierad rapport

Det enklaste produktionsflödet är GitHub Actions-workflowet **Lägg till verifierad EPS TTM**. Du anger rapportens publiceringstid, men inte längre ett separat effective date; systemet använder automatiskt samma svenska datum.

Lokalt kan samma sak göras med:

```powershell
python -m src.add_report `
  --ticker ESSITY-B.ST `
  --report-period 2026-Q2 `
  --period-end 2026-06-30 `
  --published-at 2026-07-17T07:00:00+02:00 `
  --eps-ttm 12.34 `
  --source "Bolagets rapport"
```

Efter verifieringen kan pipelinen direkt beräkna P/E, värderingsscore och strategi för den historik där EPS finns.
