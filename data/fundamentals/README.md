# Fundamentaldata

`reports.csv` är den kanoniska point-in-time-källan för EPS TTM. Endast verifierade rader i den filen får påverka P/E, värderingsscore eller signaler.

## Kanoniskt schema

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `period_end` | Rapporteringsperiodens slutdatum |
| `report_period` | Stabil periodetikett, t.ex. `2026-Q2` |
| `published_at` | När rapporten blev offentlig, med tidszon |
| `effective_date` | Första handelsdag då denna EPS TTM får användas av algoritmen |
| `eps_ttm` | Verifierad EPS TTM i bolagets rapportvaluta |
| `source` | Var siffran verifierades |
| `verified` | `true` endast när posten får användas |
| `verified_at` | Tidpunkt för verifiering |
| `notes` | Fri kommentar/audit trail |

## Viktig point-in-time-regel

`period_end` och `effective_date` är två helt olika saker. Algoritmen använder aldrig en rapport innan `effective_date`.

Exempel: ett Q2 som slutar 30 juni men publiceras 17 juli får inte påverka historiska värderingar i juni. Om rapporten publiceras före eller under handelsdagen och ska användas med den dagens stängning sätts `effective_date` till den handelsdagen. Om rapporten blir tillgänglig först efter börsstängning sätts `effective_date` till nästa relevanta handelsdag efter att marknaden fått möjlighet att prisa informationen.

Systemet härleder inte detta automatiskt. Det är avsiktligt för att undvika look-ahead och fel runt helger, halvdagar och publiceringstidpunkter.

## Aktuell Yahoo EPS TTM

Den dagliga Action-körningen hämtar nu direkt Yahoo `trailingEps`. Kvartals-EPS summeras inte längre.

Aktuella snapshot-värden lagras separat enligt samma mönster som pris och utdelning:

```text
data/earnings/earnings_initial.csv
data/earnings/earnings_updates.csv
```

`earnings_initial.csv` bootstrappar den första lyckade aktuella snapshoten och lämnas därefter orörd. När Yahoo senare visar ett annat EPS TTM-värde sparas det som en ny rad i `earnings_updates.csv` med den dag då systemet först observerade ändringen.

Denna snapshot är användbar för aktuell kontroll, men `observed_date` är inte automatiskt samma sak som rapportens verkliga publiceringstid. Historisk point-in-time-värdering fortsätter därför att använda verifierade `published_at` och `effective_date` i `reports.csv`.

## Valuta

EPS lagras i bolagets ursprungliga rapportvaluta. Aktiens handelsvaluta och rapportvaluta finns i `data/metadata/stocks_yahoo.csv`.

Om valutorna skiljer sig konverteras EPS till aktiens handelsvaluta **innan** P/E beräknas. Valutahistoriken ligger i `data/fx/` och hämtas från Yahoo. Exempelvis används `USDSEK=X` för USD -> SEK och `EURSEK=X` för EUR -> SEK.

För att undvika look-ahead används den senaste fullt avslutade FX-dagskursen före aktiedagen. Den rapporterade siffran bevaras samtidigt som `EPS_TTM_RAW`; den valutajusterade serien används som `EPS_TTM` i värderingen. Om ett nödvändigt valutapar saknas får systemet inte behandla två olika valutor som om de vore samma.

## Historikimport

Köpt historisk data importeras via:

```powershell
python -m src.import_history --input <fil> --mapping config/history_import_mapping.yml
```

Importen vägrar använda rader som saknar `published_at`, `effective_date`, `eps_ttm` eller verifiering.

## Ny verifierad rapport

Det enklaste produktionsflödet är GitHub Actions-workflowet **Lägg till verifierad EPS TTM**. Det skriver posten till `reports.csv`, bygger om dashboarden och kör valideringen innan commit.

Lokalt kan samma sak göras med:

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

Efter verifieringen kan pipelinen direkt beräkna point-in-time P/E, värderingsscore och strategi för den historik där EPS finns.
