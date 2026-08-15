# FX-data för EPS-värdering

Den här mappen innehåller valutakurser som används när ett bolags rapportvaluta skiljer sig från aktiens handelsvaluta.

## Filer

- `fx_initial.csv` är den frysta grundhistoriken.
- `fx_updates.csv` skapas och uppdateras löpande efter bootstrap.

Schema:

```text
date,base_currency,quote_currency,rate,yahoo_ticker
```

`rate` betyder antal enheter av `quote_currency` per 1 enhet `base_currency`. Exempel: för `USD/SEK` är 9.50 lika med 1 USD = 9.50 SEK.

## Användning i värderingen

Rapporterad EPS sparas i bolagets ursprungliga rapportvaluta. När `report_currency != price_currency` konverteras EPS först till aktiens handelsvaluta och därefter beräknas P/E.

För att undvika look-ahead använder en aktiedag den senaste fullt avslutade FX-dagskursen **före** aktiedagen. En FX-close daterad 2026-07-16 börjar alltså användas för aktievärdering från 2026-07-17.

Om nödvändig valutakurs saknas lämnas den valutajusterade EPS-serien tom. Systemet ska aldrig dividera en SEK-aktiekurs med exempelvis en USD-EPS som om valutorna vore samma.

Nödvändiga valutapar härleds automatiskt från `data/metadata/stocks_yahoo.csv`. Yahoo-symbolen för ett direkt valutapar byggs som exempelvis `USDSEK=X` eller `EURSEK=X`.
