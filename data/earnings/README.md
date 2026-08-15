# Earnings / EPS TTM

Den här mappen följer samma upplägg som pris- och utdelningsdata:

- `earnings_initial.csv` är den frysta basen.
- `earnings_updates.csv` skapas av den dagliga körningen och innehåller endast senare EPS TTM-värden som faktiskt har ändrats.

## Schema

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `observed_date` | Första dag den dagliga pipelinen observerade detta EPS TTM-värde |
| `eps_ttm` | Direkt Yahoo `trailingEps` |
| `source` | Källa för värdet |

Kvartals-EPS summeras inte i detta flöde.

Första lyckade körningen bootstrappar `earnings_initial.csv` med den då aktuella EPS TTM-snapshoten. Därefter lämnas initialfilen orörd och endast ändrade värden läggs till i `earnings_updates.csv`.

`observed_date` är inte samma sak som rapportens publiceringstid. Den kan användas som audit trail för när systemet först såg ett nytt värde, men den ersätter inte den verifierade `published_at` / `effective_date` som används för historisk point-in-time-värdering i `data/fundamentals/reports.csv`.
