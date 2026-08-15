# Earnings / EPS TTM

Den här mappen följer samma upplägg som pris- och utdelningsdata:

- `earnings_initial.csv` är den frysta basen.
- `earnings_updates.csv` skapas av den dagliga körningen och innehåller endast senare EPS TTM-värden som faktiskt har ändrats.

## Schema

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `report_date` | Senaste redan inträffade rapportdatum som Yahoo `get_earnings_dates()` kopplar till bolaget när EPS-värdet sparas |
| `observed_date` | Första dag den dagliga pipelinen observerade detta EPS TTM-värde |
| `eps_ttm` | Direkt Yahoo `trailingEps` |
| `source` | Källa för EPS och rapportdatum |

Kvartals-EPS summeras inte i detta flöde.

Första lyckade körningen bootstrappar `earnings_initial.csv` med den då aktuella EPS TTM-snapshoten och senaste historiska rapportdatumet från Yahoo. Därefter lämnas initialfilen orörd. När `trailingEps` ändras sparas det nya värdet i `earnings_updates.csv` tillsammans med det senaste redan inträffade rapportdatumet.

Rapportdatum hämtas bara för EPS-rader som faktiskt ska sparas. Efter bootstrap innebär det normalt bara några få extra Yahoo-anrop kring rapportperioder i stället för att hämta rapportkalender för hela aktieuniversumet varje dag.

`report_date` är betydligt bättre än `observed_date` för att koppla ett EPS-skifte till en rapport, men det är fortfarande Yahoo-metadata. Exakt `published_at` och den handelsmässiga `effective_date` som används i historisk point-in-time-värdering verifieras separat i `data/fundamentals/reports.csv`.
