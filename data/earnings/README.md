# Earnings / EPS

Den här mappen lagrar både Yahoos EPS TTM och separata EPS-komponenter för rapportperioder.

## EPS TTM

- `earnings_initial.csv` är den frysta basen.
- `earnings_updates.csv` skapas av den dagliga körningen och innehåller senare Yahoo `trailingDilutedEPS`-värden som faktiskt har ändrats.

Viktiga kolumner är `ticker`, `period_end`, `report_date`, `observed_date`, `eps_ttm`, `eps_currency` och `source`. Exakt publiceringstid och handelsmässig `effective_date` verifieras separat i `data/fundamentals/reports.csv`.

## EPS för enskilda rapportperioder

`quarterly_eps.csv` sparar de separata EPS-värden som behövs när en ny rapport matas in manuellt.

| Kolumn | Betydelse |
|---|---|
| `ticker` | Yahoo-ticker, t.ex. `ESSITY-B.ST` |
| `period_end` | Rapportperiodens slut |
| `report_date` | Rapportdatum när det finns |
| `observed_date` | Datum då värdet observerades/sparades |
| `metric` | `quarterlyDilutedEPS`, `manualDilutedEPS` eller informationsfältet `reportedEPS` |
| `eps` | EPS för rapportperioden |
| `eps_currency` | Rapportvalutan |
| `source` | Spårbar källa |

Den dagliga körningen hämtar Yahoo `quarterlyDilutedEPS` för hela aktieuniversumet och sparar nya perioder löpande. Historikjobbet backfyller samma mått från Yahoos fundamentals-timeseries.

### Manuell rapportinmatning

För normala kvartalsrapporterande bolag behöver användaren bara mata in **utspädd EPS för den nya rapportperioden**. Systemet härleder en provisorisk EPS TTM enligt:

`ny TTM = föregående Yahoo trailingDilutedEPS + aktuell period-EPS - motsvarande period-EPS föregående år`

Automatisk härledning får bara använda:

1. `manualDilutedEPS` som verifierats manuellt, eller
2. Yahoo `quarterlyDilutedEPS`.

Yahoo `Reported EPS` sparas endast som referens/audit och får **inte** användas i TTM-formeln, eftersom måttdefinitionen kan skilja sig från diluted EPS. Om jämförbar diluted EPS, föregående Yahoo TTM eller korrekt valuta saknas stoppas inmatningen i stället för att ett värde uppskattas.

När Yahoo senare publicerar faktisk `trailingDilutedEPS` för samma period ersätter den den provisoriskt härledda TTM-posten utan att rapportens verifierade `effective_date` flyttas.

### Bolag utan kvartalsvisa finansiella rapporter

Alla bolag har inte en verklig kvartals-EPS. Ett exempel i nuvarande universum är `EQT.ST`, som publicerar finansiella rapporter med EPS halvårsvis och vid bokslut medan Q1/Q3 är operativa kvartalsredogörelser. Systemet ska därför inte skapa en Q1/Q3-EPS-proxy för sådana bolag.
