# Fundamentaldata

`reports.csv` är den kanoniska point-in-time-källan för EPS TTM. Endast verifierade rader i den filen får påverka P/E, värderingsscore eller signaler.

## Kanoniskt schema

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `period_end` | Rapporteringsperiodens slutdatum |
| `report_period` | Stabil periodetikett, t.ex. `2026-Q2` eller automatiskt `YAHOO-YYYY-MM-DD` för nya Yahoo-perioder |
| `published_at` | När rapporten blev offentlig, med tidszon när exakt tid finns |
| `effective_date` | Datum då denna EPS TTM börjar användas av algoritmen |
| `eps_ttm` | EPS TTM i bolagets rapportvaluta |
| `source` | Datakälla och metric |
| `verified` | `true` när posten får användas |
| `verified_at` | Tidpunkt för verifiering/import |
| `notes` | Audit trail och eventuell fallback-status |

## Fast EPS-definition

Projektets gemensamma EPS-definition bakåt och framåt är Yahoo Finance **`trailingDilutedEPS`** från fundamentals-timeseries.

Denna metric används eftersom Yahoo samtidigt anger:

- EPS TTM efter utspädning,
- periodslut (`asOfDate`),
- EPS-valuta (`currencyCode`).

Det gör att historiska och framtida värden kan jämföras på samma grund innan projektets separata FX-konvertering. Vi blandar inte längre framtida `trailingEps` från quoteSummary med en annan historisk EPS-definition.

**Ingen ytterligare betald EPS-data behövs framåt.** Den dagliga uppdateringen hämtar nya `trailingDilutedEPS`-perioder gratis från Yahoo och synkar dem till `reports.csv` när period, rapportdatum och valuta är konsistenta.

## Same-day-regel för EPS

`period_end` och `effective_date` är två helt olika saker. Algoritmen använder aldrig en rapport före dess rapportdatum.

Projektets fasta regel är att ny EPS TTM gäller **samma svenska kalenderdag som rapporten publiceras**. Exempel: ett Q2 som slutar 30 juni men publiceras 17 juli får börja påverka P/E och värderingsscore med stängningskursen den 17 juli. Vi flyttar alltså inte EPS till nästa handelsdag beroende på exakt publiceringstid.

För historik där bara `report_date` finns sätts därför `effective_date = report_date`. Vid manuell verifiering härleder `src.add_report` automatiskt `effective_date` från `published_at` i tidszonen `Europe/Stockholm` och accepterar inte ett avvikande explicit datum.

Detta är en medveten modellregel. Den kan i undantagsfall innebära att en rapport som faktiskt publicerades efter börsstängning ändå räknas från samma dags stängning.

## Daglig Yahoo EPS

`src.earnings` hämtar den senaste Yahoo `trailingDilutedEPS` direkt från fundamentals-timeseries. Varje snapshot innehåller:

```text
ticker
period_end
report_date
observed_date
eps_ttm
eps_currency
source
```

Snapshot-värden lagras i:

```text
data/earnings/earnings_initial.csv
data/earnings/earnings_updates.csv
```

En ny rad sparas när Yahoo visar en ny period, ett nytt värde eller en annan EPS-valuta. En ny period sparas alltså även om EPS råkar vara oförändrad.

`src.sync_yahoo_eps_reports` flyttar kompletta nya Yahoo-perioder till `reports.csv`. Före automatisk synk kontrolleras bland annat att Yahoo EPS-valutan är samma som bolagets lagrade rapportvaluta. Manuella rapportposter skrivs aldrig över av den automatiska synken.

Om Yahoo ännu inte har publicerat en ny `trailingDilutedEPS` efter en rapport behålls den senaste tidigare diluted-serien; systemet gissar inte och faller inte tillbaka till en annan EPS-definition.

## Valuta

EPS lagras i bolagets ursprungliga rapportvaluta. Aktiens handelsvaluta och rapportvaluta finns i `data/metadata/stocks_yahoo.csv`.

Om valutorna skiljer sig konverteras EPS till aktiens handelsvaluta **innan** P/E beräknas. Valutahistoriken ligger i `data/fx/` och hämtas från Yahoo. Exempelvis används `USDSEK=X` för USD -> SEK och `EURSEK=X` för EUR -> SEK.

För att undvika look-ahead används den senaste fullt avslutade FX-dagskursen före aktiedagen. Den rapporterade siffran bevaras som `EPS_TTM_RAW`; den valutajusterade serien används som `EPS_TTM` i värderingen. Om ett nödvändigt valutapar saknas får systemet inte behandla två olika valutor som om de vore samma.

## Historisk EPS och jämförbarhet

Det ursprungliga historiska underlaget ligger kvar som referens i `data/fundamentals/eps_ttm_history.csv`. Det används inte okritiskt som slutlig EPS-definition.

Historikflödet är:

1. `src.enrich_historical_eps` mappar ticker och rapportdatum.
2. `src.audit_yahoo_trailing_timeseries` hämtar Yahoo historisk `trailingDilutedEPS` i flera tidsfönster.
3. `src.align_historical_eps_to_yahoo` ersätter historiska rader med Yahoo `trailingDilutedEPS` där Yahoo har exakt användbar periodhistorik.
4. Rader där Yahoo saknar historisk punkt behålls som explicit taggad fallback, aldrig som om de vore Yahoo-data.
5. `src.import_enriched_eps` importerar den alignade serien till `reports.csv` med `effective_date = report_date`.

Den nuvarande första historikbatchen innehåller 490 rapportperioder för 49 tickers. Yahoo kan direkt ge `trailingDilutedEPS` för merparten av dessa perioder; kvarvarande luckor är tydligt märkta som fallback i `data/derived/eps_alignment_audit.csv`. Detta gör övergången till framtida Yahoo-data spårbar i stället för att blanda olika EPS-definitioner utan markering.

## Produktionsprincip

Framåt är Yahoo `trailingDilutedEPS` normalflödet. Manuell bolagsrapport används endast som undantagsväg om Yahoo saknar eller ger inkonsistent data. Ingen betald datatjänst ingår i den framtida EPS-pipelinen.

Den dagliga Action-körningen uppdaterar först marknadsdata och FX, hämtar sedan Yahoo EPS, synkar eventuellt ny EPS till `reports.csv` och bygger därefter om dashboarden så att dagens värdering använder den senaste godkända EPS-perioden.
