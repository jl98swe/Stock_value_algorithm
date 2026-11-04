# Granskning av samtliga aktier efter felet i rapportomräkningen

Granskad version: `ec7ffa92150a31375f7c68f50720924bbba5c949`.
Omfattning: 119 av 119 aktier, 46 commits på main från införandet
`0b1c8effddb9c61685923b099b19e444aa26ef87` den 31 oktober till den granskade
versionen den 4 november 2026. Första jämförelsen använder föräldern till
införandecommitten. Ingen källkod, rapport-EPS eller handelsdata ändras av denna
granskning; endast granskningsfiler sparas.

## Efterföljande återställning 4 november 2026

Samtliga tio EPS-fall är nu återställda och kontrollerade mot respektive
publicerad referens före felet. Senare dagar som saknade en referens räknades
om med endast de rapporter som var publicerade den dagen. De verifierade
manuella rapportregistreringarna är bevarade byte för byte.

De fyra kalenderköpen och AstraZenecas kalenderberoende äldre affärer har
rättats med arkiverad observationstid. För nya kalenderdatum används den
första sparade observationen även när rapporten senare blir historisk.
En migrationslista bevarar redan publicerade äldre simuleringar för övriga
aktier; den gör inget påstående om när deras kalenderinformation först var känd.
En uppdaterad kalender får inte ge tillåtelse till köp före observationen.
Äldre simuleringar bevaras, med en uttrycklig rättelse för AstraZenecas
rapport 30 oktober enligt kalenderobservationen 15 september.

Statusen i tabellen och 119-radersfilen är uppdaterad efter återställningen.
Den ursprungliga granskningsmetoden och fynden nedan behålls som kontrollspår.

## Resultat

Tio aktier fick publicerade poäng före respektive rapportdag ändrade genom
omräkning från periodslut i stället för publicering. För fem av dessa ändrades
även utförda modellaffärer. Vid granskningen var fem aktier återställda och fem ytterligare återstod.
Efterföljande återställning ovan omfattar samtliga tio.

| Aktie | Första felaktiga dataexport (commit) | Poäng ändrade före rapportdagen | Ändrade modellaffärer | Status |
|---|---|---:|---|---|
| ABB | d617015c, 31 oktober | 14 datum | Nej | Återställd |
| Eastnine | d617015c, 31 oktober | 10 datum | Nej | Återställd |
| AstraZeneca | 33b58c59, 3 november | 22 datum | Ja | Återställd |
| Rejlers B | 33b58c59, 3 november | 16 datum | Nej | Återställd |
| Fenix Outdoor B | 1c30e9b9, 3 november | 23 tidigare publicerade datum | Ja | Återställd |
| Cloetta | e74ec88c, 4 november | 25 datum | Ja | Återställd |
| SinterCast | e74ec88c, 4 november | 25 datum | Ja | Återställd |
| Cibus | e3533f5a, 4 november | 20 datum | Nej | Återställd |
| Kambi | e3533f5a, 4 november | 17 datum | Ja | Återställd |
| Medicover B | e3533f5a, 4 november | 25 datum | Nej | Återställd |

För ABB och Eastnine var de nya manuella TradingView-värdena avsiktliga.
Felet är att de också ändrade poäng FÖRE rapportdagarna 20 respektive 22 oktober.
De användarverifierade EPS-värdena ska inte tas bort.

Fenix Outdoors nya Yahoo-post har effective_date 5 november. Den ska inte
påverka publicerade poäng före det datumet. Antalet 23 ovan avser ändringar av
redan publicerade datum vid importen; senare tillagda handelsdagar behöver också
kontrolleras vid rättelsen. Även nya poäng efter importen kan ha räknats med
rapporten innan dess effective_date. Detta antal får därför inte användas som
ett fullständigt mått på alla felaktigt beräknade Fenix-poäng.

### Konkreta affärsändringar i de nyupptäckta fallen

* AstraZeneca: ett nytt Standard-köp den 5 oktober (signal 2 oktober, kurs
  1 578 SEK) dök upp vid omräkningen den 3 november. Köpet fanns inte i den
  tidigare publicerade Standard-historiken.
* Fenix Outdoor B: Standard-försäljningen flyttades från 28 oktober
  (signal 27 oktober, kurs 319,50 SEK) till 2 oktober (signal 1 oktober,
  kurs 282 SEK). Även stop loss och två positioner påverkades.
* ABB, Eastnine och Rejlers: ändrade poäng, men inga ändrade utförda affärer
  i de fem strategierna vid dessa EPS-omräkningar.

### Separata kalenderberoende omräkningar

I Rapportundvikande tillkom följande historiska köp vid exporten `33b58c59`
den 3 november, utan ändrade poäng. Nya framtida rapportdatum användes för
äldre dagar där strategin tidigare saknade nästa rapportdatum och blockerade köp.
Detta är en annan mekanism än EPS-felet, och ska inte räknas in bland de tio
EPS-drabbade aktierna.

| Aktie | Historiskt köp som tillkom | Ny kalenderuppgift observerad |
|---|---|---|
| Alleima | 28 oktober | 1 november |
| Epiroc A | 30 oktober | 1 november |
| Nordea | 19 oktober | 31 oktober |
| SEB A | 26 oktober | 31 oktober |

Kalenderuppgifterna för 2027 finns dokumenterade i
`data/earnings/report_calendar_history.csv`. Strategins
`report_date_basis=final_report_dates` innebär att en ny kalender kan ändra en
historisk simulering. Det är inte samma sak som att köpsignalerna var synliga vid
köptillfällena. Denna del behöver hanteras separat om signalhistoriken ska visa
beslut som faktiskt var möjliga med den då tillgängliga kalenderinformationen.
Även AstraZeneca hade kalenderberoende förändringar inom Rapportundvikande;
aktien räknas redan bland de tio EPS-drabbade.

109 av 119 aktier har ingen upptäckt retroaktiv poängändring av detta EPS-fel i
perioden. Fyra av dessa 109 har kalenderförändringarna ovan. För övriga 105
hittades varken EPS-omräkningen eller dessa kalenderberoende retroaktiva köp.
Detta är en avgränsad historikgranskning, inte en kontroll av alla tänkbara fel i
algoritmen eller av perioder före införandet den 31 oktober.

## Metod och kontrollspår

1. Alla 46 commits på main jämfördes med föregående main-version. Samtliga
   publicerade rader i `valuation_score_history.csv.gz` jämfördes på ticker och
   datum. Tolerans för numeriska skillnader: 1e-9 poäng. Borttagna och nytillagda
   historiska datum kontrollerades också. Normalt tillagda senare handelsdagar
   klassificerades separat.
2. De 15 skilda versionerna av `docs/data/dashboard.json` jämfördes oberoende av
   den frysta CSV-filen. Exakt samma tio aktier hade ändrade historiska poäng.
   Null-poäng jämfördes separat från numeriska värden.
3. Utförda köp/sälj kontrollerades i alla fem strategier via den aggregerade
   affärshistoriken, inklusive ingångar i fortfarande öppna positioner.
   Skillnader i datum, riktning och kurser skildes från ordinarie nya affärer.
4. Standard-strategins exporterade signaler jämfördes dessutom mellan
   webbversionerna. Normala övergångar från väntande till utförd signal när
   öppningsdata blev tillgängliga är inte retroaktiva poängfel.
5. Kalenderförändringarna spårades till observationerna 31 oktober/1 november
   och nästa rapportdatum i respektive akties översikt. Små skillnader från
   avrundade öppningskurser till Yahoo-flyttal för Attendo, Balder B,
   Castellum och Lundin Mining ändrade inte affärernas datum eller riktning och
   räknas inte som nya eller flyttade affärer.
6. Aktuell fryst historik jämfördes åter med respektive version omedelbart före
   den felaktiga omräkningen, begränsat till datum före rapportdagen. Vid granskningen matchade de fem tidigare återställda aktierna
   referensen medan de fem nyupptäckta inte gjorde det. Efter återställningen
   matchar samtliga tio sina respektive referenser.

ABB/Eastnines första felaktiga version publicerades via GitHub Pages
31 oktober kl. 10.54.46 svensk tid (run `41190541980`). Detta korrigerar den
ofullständiga tidigare tidsbilden att problemet först syntes den 4 november.
Git-commit-tiderna i CSV-filen är inte i sig tidpunkter då användarens webbläsare
läste in datan.

## Filer

* `history_audit_all_stocks_2026-11-04.csv`: en rad per aktie, samtliga 119,
  med klassificering och aktuell återställningsstatus.
* `history_audit_score_changes_2026-11-04.csv`: 325 ändrade poängrader mellan
  granskade versioner, inklusive återställningarna den 4 november.
  Legitima ändringar från rapportdagen kan också ingå; kolumnen ticker/datum
  måste jämföras med rapportdagen innan en rad klassificeras som fel.
