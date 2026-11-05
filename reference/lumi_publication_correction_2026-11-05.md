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
