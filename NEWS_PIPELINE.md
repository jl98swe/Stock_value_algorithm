# Bolagsnyheter från MFN

Nyhetsflödet är frikopplat från EPS- och marknadspipelinen. Det hämtar bolagens egna pressmeddelanden från MFN, filtrerar bort sådant som redan representeras som rapport (`E`) eller utdelning (`D`) och publicerar bara högkonfidensrelevanta poster som `N` i `docs/data/events.json`.

Produktionsingången är `src.news_curated`. `src.news` innehåller själva MFN-hämtningen och lagringen, medan `src.news_curated` lägger på den striktare lågbruspolicyn innan samma pipeline körs.

## Historik

Historikimporten har `2024-01-01` som standardstart:

```bash
python -m src.news_curated --history --start 2024-01-01
```

En enskild ticker kan testas med exempelvis:

```bash
python -m src.news_curated --history --start 2024-01-01 --ticker ERIC-B.ST
```

GitHub Actions-workflowen **Historisk MFN-nyhetsimport** erbjuder samma parametrar manuellt. `data/news/status.json` visar vilka MFN-källor som kunde lösas och om historiken kunde verifieras tillbaka till startåret.

## Daglig uppdatering

```bash
python -m src.news_curated
```

Workflowen **Daglig bolagsnyhetsuppdatering** kör 18:05 Europe/Stockholm på handelsdagar, efter ordinarie marknadsuppdatering. Den ersätter endast `news`-händelser i `docs/data/events.json`; befintliga rapport- och utdelningshändelser lämnas orörda.

## Relevansregler

Varje pressmeddelande hamnar i en av tre grupper:

- `keep`: visas automatiskt som `N`. Exempel är vinstvarningar, ändrad guidance, förvärv/avyttringar, emissioner eller finansieringsproblem, större regulatoriska/juridiska händelser, omstruktureringar, uttryckligt större order/avtal samt byten i de allra största ledningsrollerna.
- `review`: osäker relevans. Posten sparas i `data/news/review_queue.json` men visas inte automatiskt i dashboarden.
- `drop`: sparas inte som nyhet. Hit hör rapporter, vanliga utdelningsmeddelanden och rutin-/administrationsposter.

### Ledning

Automatiskt `N` för ledningsförändringar är medvetet snävt. VD/CEO, CFO/finansdirektör och styrelseordförande räknas som huvudroller. Generella förändringar i koncernledningen samt chefer för affärsområden, divisioner, regioner, marknadsområden och liknande filtreras bort.

Reglerna tittar i första hand på rubriken för ledningsbyten. En generisk koncernledningsnyhet ska alltså inte bli `N` bara för att artikeltexten råkar nämna VD:n.

### Återköp och aktieadministration

Aktieåterköp filtreras bort helt från `N`, även om de inte är veckovisa. Även tekniska meddelanden om överlåtelsebemyndiganden, överlåtelse av egna aktier och motsvarande treasury-share-administration filtreras bort.

### Kontor

Öppnande, flytt eller byte av kontor/huvudkontor visas inte som `N`.

### Rapporter

Rapportreglerna körs före övriga materialitetsregler så att en rapport med exempelvis ny guidance fortfarande representeras som `E`, inte dupliceras som `N`. Filtret omfattar även engelska rubriker av typen `Company reports fourth quarter and full-year results`.

Vanliga utdelningar representeras endast som `D`. En faktisk förändring av utdelningspolicy, indragen eller inställd utdelning kan däremot vara materiell och få en separat `N`-händelse.

Övrigt rutinbrus som stämmokallelser, valberedning, flaggning, ledande befattningshavares transaktioner samt kalender-/konferensinformation filtreras också bort.

## Lagring

- `data/raw/news/<ticker>.json`: endast publicerade `keep`-poster, med kompakt metadata och kort sammanfattning.
- `data/news/review_queue.json`: osäkra poster för senare bedömning.
- `data/news/mfn_sources.csv`: cache över ticker -> verifierad MFN-bolagssida.
- `data/news/status.json`: täckning och statistik från senaste körningen.
- `docs/data/events.json`: befintliga E/D plus de publicerade N-händelserna.

Hela artikeltexter lagras inte.

## Källmatchning

Koden försöker verifiera bolagsnamnet på MFN innan en ticker kopplas till en bolagssida. Om automatisk matchning misslyckas markeras tickern som `source_unresolved` i `data/news/status.json` i stället för att data från ett osäkert bolag publiceras. Sådana matchningar kan därefter granskas och vid behov korrigeras i `data/news/mfn_sources.csv`.
