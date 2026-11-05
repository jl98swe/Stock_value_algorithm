# LUMI: verifierad publicering och historisk rättelse

Granskningen omfattar samtliga 33 rapportposter i modellen, 2018 Q3–2026 Q3.
Källor, officiella datum, publiceringstider med UTC-offset och första svenska
handelsdag finns i `lumi_publication_audit_2026-11-05.csv`.

20 poster saknade tidigare giltighetsdatum. Av de 13 daterade posterna ändras
sju giltighetsdatum; sex var redan korrekta. Samtliga kontrollerade publiceringar
skedde efter stängningen för det officiella rapportdatumet. Rapporten 2024 Q1
publicerades på den svenska helgdagen 1 maj. Rapporter efter svensk midnatt
behåller bolagets officiella rapportdatum. Börskalendern XSTO avgör giltigheten.

Källkontrollen identifierade undantag som inte får lösas genom antaganden:

- 2019 års rapportarkiv länkar fel för Q3, till 2020 års Q3-rapport. Ursprungligt
  bolagsmeddelande i PDF och Lundin Groups officiella spegling bekräftar
  23 oktober 2019 kl. 19:30 Eastern.
- 2023 Q3 och 2024 Q1 använder beteckningen Pacific Standard Time under
  sommartid. CNW:s officiella distribution bekräftar 18:00 respektive 17:30
  Eastern. Distributionstid används för den faktiska tidsstämpeln.
- 2026 Q2 anger endast ”4:00 Vancouver Time”. CNW:s distribution bekräftar
  19:00 Eastern, dvs. 6 augusti kl. 01:00 i Sverige. Tiden tolkas inte som 04:00.
- 2026 Q3 anger 4 november kl. 15:30 Vancouver, dvs. 23:30 UTC och 5 november
  kl. 00:30 i Sverige. Officiellt rapportdatum förblir 4 november; EPS gäller 5 november.

Verifierad publiceringstid har högre prioritet än kalender, datumcache och
automatiska datumkontroller. EPS-belopp och manuella datakällors prioritet ändras
inte. En explicit historisk rättelse upphäver LUMI:s tidigare frysta poäng från
24 oktober 2018. LUMI använder därefter EPS från giltighetsdatum i både ordinarie
och preliminära beräkningar, även för TradingView-värden. Övriga aktiers
beräkningsläge ändras inte.

Den historiska effekten kan vara större än en dags förskjutning: äldre saknade
rapporter blir tillgängliga, och LUMI:s tidigare periodslutsbaserade
beräkningshistorik ersätts med rapportinformation som faktiskt var tillgänglig.
Tidigare TradingView-kalibrering ger därför ingen garanti för oförändrade poäng.

Körningen `lumi_publication_correction.yml` sparar kompletta jämförelser i
`lumi_publication_2026-11-05_score_changes.csv`,
`lumi_publication_2026-11-05_signal_changes.json` och
`lumi_publication_2026-11-05_impact.json`. Den stoppar publicering om EPS-belopp,
kurser eller någon annan akties poäng, signaler eller affärer ändras.

## Samtliga granskade rapporter

Officiellt datum avser bolagets rapportdatum. Tid anges med verifierad UTC-offset.

| Period | Rapportdatum | Publicering | Första tillåtna svenska handelsdag | Tidigare giltighetsdatum |
|---|---|---|---|---|
| 2018-Q3 | 2018-10-24 | 2018-10-24T18:30:00-04:00 | 2018-10-25 | Saknades |
| 2018-Q4 | 2019-02-14 | 2019-02-14T17:45:00-05:00 | 2019-02-15 | Saknades |
| 2019-Q1 | 2019-04-24 | 2019-04-24T18:45:00-04:00 | 2019-04-25 | Saknades |
| 2019-Q2 | 2019-07-24 | 2019-07-24T20:00:00-04:00 | 2019-07-25 | Saknades |
| 2019-Q3 | 2019-10-23 | 2019-10-23T19:30:00-04:00 | 2019-10-24 | Saknades |
| 2019-Q4 | 2020-02-20 | 2020-02-20T17:00:00-05:00 | 2020-02-21 | Saknades |
| 2020-Q1 | 2020-04-29 | 2020-04-29T18:00:00-04:00 | 2020-04-30 | Saknades |
| 2020-Q2 | 2020-07-29 | 2020-07-29T18:00:00-04:00 | 2020-07-30 | Saknades |
| 2020-Q3 | 2020-10-28 | 2020-10-28T18:30:00-04:00 | 2020-10-29 | Saknades |
| 2020-Q4 | 2021-02-18 | 2021-02-18T19:45:00-05:00 | 2021-02-19 | Saknades |
| 2021-Q1 | 2021-04-28 | 2021-04-28T17:00:00-04:00 | 2021-04-29 | Saknades |
| 2021-Q2 | 2021-07-28 | 2021-07-28T19:45:00-04:00 | 2021-07-29 | Saknades |
| 2021-Q3 | 2021-10-27 | 2021-10-27T18:30:00-04:00 | 2021-10-28 | Saknades |
| 2021-Q4 | 2022-02-17 | 2022-02-17T17:30:00-05:00 | 2022-02-18 | Saknades |
| 2022-Q1 | 2022-04-27 | 2022-04-27T18:15:00-04:00 | 2022-04-28 | Saknades |
| 2022-Q2 | 2022-07-27 | 2022-07-27T17:30:00-04:00 | 2022-07-28 | Saknades |
| 2022-Q3 | 2022-10-25 | 2022-10-25T20:00:00-04:00 | 2022-10-26 | Saknades |
| 2022-Q4 | 2023-02-22 | 2023-02-22T19:15:00-05:00 | 2023-02-23 | Saknades |
| 2023-Q1 | 2023-05-03 | 2023-05-03T18:00:00-04:00 | 2023-05-04 | Saknades |
| 2023-Q2 | 2023-08-02 | 2023-08-02T17:30:00-04:00 | 2023-08-03 | Saknades |
| 2023-Q3 | 2023-11-01 | 2023-11-01T18:00:00-04:00 | 2023-11-02 | 2023-11-01 |
| 2023-Q4 | 2024-02-21 | 2024-02-21T15:30:00-08:00 | 2024-02-22 | 2024-02-22 |
| 2024-Q1 | 2024-05-01 | 2024-05-01T17:30:00-04:00 | 2024-05-02 | 2024-05-01 |
| 2024-Q2 | 2024-07-30 | 2024-07-30T14:30:00-07:00 | 2024-07-31 | 2024-07-30 |
| 2024-Q3 | 2024-11-06 | 2024-11-06T14:30:00-08:00 | 2024-11-07 | 2024-11-06 |
| 2024-Q4 | 2025-02-19 | 2025-02-19T18:35:00-08:00 | 2025-02-20 | 2025-02-20 |
| 2025-Q1 | 2025-05-07 | 2025-05-07T15:35:00-07:00 | 2025-05-08 | 2025-05-08 |
| 2025-Q2 | 2025-08-06 | 2025-08-06T17:30:00-07:00 | 2025-08-07 | 2025-08-06 |
| 2025-Q3 | 2025-11-05 | 2025-11-05T15:35:00-08:00 | 2025-11-06 | 2025-11-06 |
| 2025-Q4 | 2026-02-19 | 2026-02-19T15:30:00-08:00 | 2026-02-20 | 2026-02-20 |
| 2026-Q1 | 2026-05-06 | 2026-05-06T14:30:00-07:00 | 2026-05-07 | 2026-05-06 |
| 2026-Q2 | 2026-08-05 | 2026-08-05T19:00:00-04:00 | 2026-08-06 | 2026-08-06 |
| 2026-Q3 | 2026-11-04 | 2026-11-04T15:30:00-08:00 | 2026-11-05 | 2026-11-04 |

## Verifierad effekt mot tidigare publicering

Jämförelsereferens: `7da8622533db5704d12eb37e169ab2ef689bb32d`.

- 1 838 poängposter ändras eller tillkommer; 1 237 av dem saknades tidigare.
- 601 befintliga poäng ändras. Första berörda poängdatum är 2018-12-28 och sista 2026-11-04. Webbplatsens ordinarie visningsfönster börjar 2019-09-02.
- 81 signalposter skiljer sig i den exporterade jämförelsen. Standardstrategins fulla signalhistorik berör 78 olika signaldatum; jämförelsen inkluderar även ändrade aktuella signalposter för övriga strategier. Alla fem strategiers fullständiga affärer före/efter finns i impact-filen.
- Den 4 november 2026 ändras värderingspoängen från 0,7940 till 4,5648. Stängningsvärderingen använder fortfarande EPS TTM 16,7034 SEK. Ny EPS TTM 17,997205200195314 SEK gäller från 5 november.
- Övriga 118 aktiers poäng, signaler, avslut och öppna positioner är oförändrade. Samtliga kurser och EPS-belopp är oförändrade.

| Strategi | Avslut före | Avslut efter | Öppna positioner före → efter |
|---|---:|---:|---:|
| Standard | 4 | 11 | 1 → 1 |
| Stop loss 10 % | 7 | 23 | 1 → 1 |
| Två positioner | 6 | 17 | 2 → 2 |
| MA200 | 4 | 9 | 0 → 0 |
| Rapportundvikande | 8 | 20 | 0 → 0 |

Standardstrategins avkastning för hela tillgängliga perioden ändras från 86,12 till 84,47 procent; max drawdown från −33,69 till −68,60 procent. Andelen vinstaffärer ändras från 75,00 till 54,55 procent. Köp och behåll är oförändrad, 402,67 procent. Jämförelsen omfattar även utökad historiktäckning och övergången från periodslutsdata till tillgänglig rapportinformation; den isolerar inte enbart en dags förskjutning.

## Tester och publicering

- 473 Python-tester godkända i full körning.
- 17 JavaScript-tester godkända, inklusive hovring, tangentbord och mobiltryck för informationsikonen.
- 12 publiceringstester godkända separat. Modellfilen initieras uttryckligen så att testet är oberoende av körordning.
- Datavalidering: 119 aktier, 307 811 prisrader, 100 modellträd; FX, EPS och webbexport konsistenta.
- Historikskydd och separat jämförelse av övriga aktier godkända.

Kod: [PR #128](https://github.com/jl98swe/Stock_value_algorithm/pull/128), [huvudcommit](https://github.com/jl98swe/Stock_value_algorithm/commit/6c2dac80be33594eb5d67a2847faeaea7d9a6f9c), [exportvalidering](https://github.com/jl98swe/Stock_value_algorithm/commit/8c5051d281f9b5e7f5413c4c2e6ade3044ab488e), [självständigt test](https://github.com/jl98swe/Stock_value_algorithm/commit/44cbe8aaa0901846dff57de31474f748e0cd264a).

[Omräkning och publicering](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42092633408). Omräkningen slutfördes och publicerades; se verifieringen nedan.

Den befintliga preliminära kursen 200,60 SEK den 5 november kl. 17:16:55 behålls. Endast LUMI:s preliminära poäng räknades om från 0,4507 till 0,2887 med samma EPS och den korrigerade historiken; övriga cacheposter är oförändrade. [Cachecommit](https://github.com/jl98swe/Stock_value_algorithm/commit/1fcb0f3a2dfbe1e0ca3853d167ae9dd9dbdcbeec).

Omräkning och samtliga publiceringskontroller godkändes i körning 42092633408, försök 2. Data sparades i commit [5fefdd78](https://github.com/jl98swe/Stock_value_algorithm/commit/5fefdd78381055c99f3cb69a79cb2bfa486c0351).

GitHub Pages-publicering [42095170486](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42095170486) lyckades. Den publika aktiesidan har kontrollerats: rapportdatum 4 november, giltighetsdatum 5 november och informationsikonens exakta text. Rapportsidan visar officiellt 4 november och EPS TTM 16,7034 → 17,9972 SEK. Poäng efter rapporten visas ännu som streck eftersom den senaste publicerade stängningskursen är 4 november.

Senaste fullständiga CI:s smoke-jobb i körning [42094033472](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42094033472) är godkänt. LUMI-körningens 51 Python-tester och 17 JavaScript-tester är också godkända. Den första körningen hittade ett test som förutsatte en redan skapad modellfil; det rättades innan försök 2 publicerade data.

## Ändrade filer

Källkod: `src/fundamentals.py`, `src/report_date_revisions.py`, `src/report_publications.py`, `src/lumi_publication_audit.py`, `src/pipeline.py`, `src/reporting.py`, `src/strategy_backtests.py`, `src/validate_outputs.py`.

Webbgränssnitt: `docs/assets/app.js`, `docs/assets/reports.js`, `docs/assets/eps-provenance.js`, `docs/index.html`, `docs/reports.html`. Tester: `tests/test_report_publications.py`, `tests/test_eps_provenance_ui.cjs`.

Indata och kontrollhistorik: `data/fundamentals/report_publications.csv`, `data/fundamentals/reports.csv`, `data/fundamentals/eps_report_date_cache.csv`, `data/manual/history_corrections.json`, `data/derived/report_score_dates.csv`, `data/derived/report_date_score_revisions.csv`, `data/derived/valuation_score_history.csv.gz`. Befintliga `report_date_overrides.csv` och `report_date_rechecks.csv` behövde inte ändras.

Publicerade data: `docs/data/backtests/LUMI.ST.json`, `docs/data/backtests/all.json`, `docs/data/dashboard.json`, `docs/data/dashboard/index.json`, samtliga 119 separata dashboard-filer med nya rapportmetadata, `docs/data/events.json`, `docs/data/manual_reports.json`, `docs/data/reports.json`, `docs/data/signal_prices.json`, `docs/data/stocks.json`, `docs/data/strategy_overviews.json`. Endast LUMI:s historiska poäng och affärer ändrades. `intraday-cache:intraday.json` fick enbart korrigerad LUMI-värdering.

Workflows: `.github/workflows/lumi_publication_correction.yml`, `.github/workflows/history_recovery_queue.yml`. De automatiska extrakörningar som utlöstes av denna kodändring stoppades med exakt run-ID och commitkontroll, utan att stoppa schemalagda eller manuellt begärda körningar.

Granskningsfiler: denna rapport, `reference/lumi_publication_audit_2026-11-05.csv`, `reference/lumi_publication_2026-11-05_impact.json`, `reference/lumi_publication_2026-11-05_score_changes.csv`, `reference/lumi_publication_2026-11-05_signal_changes.json`. [Fullständig filjämförelse](https://github.com/jl98swe/Stock_value_algorithm/compare/7da8622533db5704d12eb37e169ab2ef689bb32d...5fefdd78381055c99f3cb69a79cb2bfa486c0351).
