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
| `notes` | Audit trail och eventuell härledning |

## Fast EPS-definition

Projektets gemensamma EPS-definition bakåt och framåt är Yahoo Finance **`trailingDilutedEPS`** från fundamentals-timeseries.

Denna metric används eftersom Yahoo samtidigt anger:

- EPS TTM efter utspädning,
- periodslut (`asOfDate`),
- EPS-valuta (`currencyCode`).

Det gör att historiska och framtida värden kan jämföras på samma grund innan projektets separata FX-konvertering. Vi blandar inte längre framtida `trailingEps` från quoteSummary med en annan historisk EPS-definition.

**Ingen ytterligare betald EPS-data behövs framåt.** Den dagliga uppdateringen hämtar nya `trailingDilutedEPS`-perioder gratis från Yahoo och synkar dem till `reports.csv` när period och valuta är konsistenta.

## Same-day-regel för EPS

`period_end` och `effective_date` är två helt olika saker. Den kanoniska rapporthistoriken, rapportlås och vanliga Yahoo-baserade värderingar använder aldrig en ny period före den dag den kan knytas till en inträffad rapport eller faktiskt har observerats av systemet.

Projektets fasta regel är att ny EPS TTM gäller **samma svenska kalenderdag som rapporten publiceras** när rapportdatumet är känt och rimligt. Exempel: ett Q2 som slutar 30 juni men publiceras 17 juli får börja påverka P/E och värderingsscore med stängningskursen den 17 juli. Vi flyttar alltså inte EPS till nästa handelsdag beroende på exakt publiceringstid.

För historik där `report_date` finns sätts `effective_date = report_date`. Vid manuell verifiering härleder `src.add_report` automatiskt `effective_date` från `published_at` i tidszonen `Europe/Stockholm` och accepterar inte ett avvikande explicit datum.

För en **genuint ny framtida Yahoo-period** där Yahoo saknar ett rimligt rapportdatum används i stället `observed_date`, alltså dagen systemet först såg den nya `trailingDilutedEPS`-perioden. Det är en konservativ reservregel: värdet kan då börja användas senare än den verkliga rapportdagen men aldrig före systemet hade tillgång till det.

## TradingView-läge för värderingsstate

En ticker aktiverar `tv_period_end_state` endast när den har verifierade EPS-rader vars källa börjar med `TradingView /`. Då kopplar värderingsmotorn EPS TTM till `period_end`, med `effective_date` som reserv om periodslut saknas. Detta efterliknar hur TradingView placerar historiska fundamentalvärden utan att ändra rapportdatumet i den kanoniska datan.

TradingView kan leverera EPS i aktiens handelsvaluta även när bolaget rapporterar i en annan valuta. Valutan i varje verifierad rapports audit trail (`report_currency=...`) har därför företräde framför bolagets generella rapportvaluta. Det gör exempelvis att ABB:s manuellt verifierade TradingView-värden i SEK inte konverteras en andra gång från USD, samtidigt som äldre och framtida Yahoo-rader i USD fortfarande valutajusteras.

Detta läge är avsiktligt inte ett traditionellt point-in-time-backtest: när en ny rapport blir känd räknas det interna rullande tillståndet om från periodslutet. Den publicerade grafen skyddas i stället av `data/derived/valuation_score_history.csv.gz`. Befintliga datum återanvänds oförändrade och endast datum efter tickerns senast frysta dag får läggas till. Därmed påverkar ett nytt EPS-värde endast kommande synliga poäng.

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

Det historiska referensunderlaget ligger i `data/fundamentals/eps_ttm_history.csv`. Det används inte som kanonisk EPS när det inte kan göras jämförbart med den framtida Yahoo-definitionen.

Historikflödet är:

1. `src.enrich_historical_eps` mappar ticker och rapportdatum.
2. `src.audit_yahoo_trailing_timeseries` hämtar historisk Yahoo `trailingDilutedEPS` samt diluted kvartalskomponenter i flera tidsfönster.
3. `src.align_historical_eps_to_yahoo` använder direkt Yahoo `trailingDilutedEPS` där den finns. Om en enskild TTM-punkt saknas men Yahoo har tillräckliga diluted-komponenter rekonstrueras samma TTM-definition matematiskt från Yahoo-data.
4. Rader som fortfarande inte kan göras jämförbara behålls endast som **referens-fallback** i `eps_ttm_history_aligned.csv` och `eps_alignment_audit.csv`. De importeras inte till `reports.csv` och påverkar inte P/E, score eller signaler.
5. `src.import_enriched_eps` importerar endast direkt eller Yahoo-rekonstruerad diluted EPS till `reports.csv`, med `effective_date = report_date`.

Etablerade historiska rapportdatum lagras dessutom i `data/fundamentals/eps_report_date_cache.csv`. För en redan känd kombination av `ticker + report_period` återanvänds det etablerade datumet vid framtida körningar; ett nytillkommet Yahoo-event får alltså inte flytta äldre perioder ett kvartal framåt. Prioriteten är: explicit datum i referensfilen, därefter stabil cache och först därefter ny Yahoo-mappning. Verifierade `report_date_overrides.csv` skrivs också tillbaka till cachen. Endast helt nya perioder får därmed få ett nytt automatiskt rapportdatum.

När historikimporten bygger om `reports.csv` ersätts maskin-genererade Yahoo-rader som kolliderar med den etablerade historiken på `ticker + period_end` **eller** återanvänder samma `ticker + report_period` med ett annat periodslut. Manuellt verifierade rader bevaras. Framtida Yahoo-perioder utanför referenshistoriken får i stället egna stabila etiketter av typen `YAHOO-YYYY-MM-DD`.

Täckningen förändras när `eps_ttm_history.csv` utökas eller när Yahoo får mer historik. Därför ska inga fasta rad- eller tickerantal dokumenteras här. Aktuell status finns i de genererade auditfilerna, framför allt:

- `data/derived/eps_alignment_audit.csv` för matchning mellan referenshistorik och Yahoo diluted EPS,
- `data/derived/eps_reference_compatibility_audit.csv` för den strikta kompatibilitetskontrollen,
- `data/derived/eps_reference_gap_audit.csv` för kvarvarande historiska luckor,
- `data/derived/yahoo_history_continuity_audit.csv` för luckor i den direkt hämtade Yahoo-historiken.

Endast rader med `alignment_status = yahoo_trailing_diluted` eller `yahoo_reconstructed_diluted_ttm` får importeras till den kanoniska värderingshistoriken. `fallback_user_history` är enbart referens. Om en sådan referensrad ligger mellan två kanoniska perioder fortsätter den senaste föregående jämförbara diluted EPS att gälla fram till nästa jämförbara uppdatering.

## Produktionsprincip

Framåt är Yahoo `trailingDilutedEPS` normalflödet. Manuell bolagsrapport används endast som undantagsväg om Yahoo saknar eller ger inkonsistent data. Ingen betald datatjänst ingår i den framtida EPS-pipelinen.

Den dagliga Action-körningen uppdaterar först marknadsdata och FX, hämtar sedan Yahoo EPS, synkar eventuellt ny EPS till `reports.csv` och bygger därefter om dashboarden så att dagens värdering använder den senaste godkända EPS-perioden.

`src.validate_outputs` blockerar nu regressioner där Earnings-snapshots blandar in en annan EPS-metric eller där referens-fallback skulle råka hamna i den kanoniska `reports.csv`.
