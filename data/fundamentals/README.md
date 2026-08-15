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
| `eps_ttm` | Verifierad EPS TTM |
| `source` | Var siffran verifierades |
| `verified` | `true` endast när posten får användas |
| `verified_at` | Tidpunkt för verifiering |
| `notes` | Fri kommentar/audit trail |

## Viktig point-in-time-regel

`period_end` och `effective_date` är två helt olika saker. Algoritmen använder aldrig en rapport innan `effective_date`.

Exempel: ett Q2 som slutar 30 juni men publiceras 17 juli får inte påverka historiska värderingar i juni. Om rapporten publiceras före eller under handelsdagen och ska användas med den dagens stängning sätts `effective_date` till den handelsdagen. Om rapporten blir tillgänglig först efter börsstängning sätts `effective_date` till nästa relevanta handelsdag efter att marknaden fått möjlighet att prisa informationen.

Systemet härleder inte detta automatiskt. Det är avsiktligt för att undvika look-ahead och fel runt helger, halvdagar och publiceringstidpunkter.

## Automatisk Yahoo-kandidat

Den dagliga Action-körningen hämtar `Diluted EPS` från Yahoo-resultaträkningen och sparar en granskningsfil:

```text
data/fundamentals/yahoo_eps_candidates.csv
```

Om fyra kvartal finns härleds även en preliminär EPS TTM som summan av de fyra senaste kvartalens `Diluted EPS`.

Viktigt:

- `Reported EPS` från `earnings_dates` används inte.
- Yahoo-kandidater har alltid `verified=false`.
- kandidater saknar tillförlitlig `published_at` och `effective_date` och får därför aldrig automatiskt flyttas till `reports.csv`.
- granskningssidan läser även `docs/data/fundamental_candidates.json` och kan fylla EPS-formuläret, men publiceringstid och effective date måste fortfarande verifieras mot originalrapporten.

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

Efter verifieringen kan pipelinen direkt beräkna point-in-time P/E, Pine v3.0-score och strategi för den historik där EPS finns.
