# Rapportkomplettering 28 oktober 2026

Utgångspunkt: main `fac2f5fa6dc9fc7ef30a67a0c02b29080b22b298`.

Inventeringen omfattar webbexportens senaste 20 handelsdagar samt samtliga förfallna rapporthändelser i rapportstatusen per 28 oktober, svensk tid. CSV-filen `recent_report_eps_audit_2026-10-28.csv` redovisar 86 rapportposter: 77 redan kompletta, sex från senaste chatten som undantas och tre nya kompletteringar. Alleima, Assa Abloy, CTT, Hanza, Sobi och VBG lämnas oförändrade. Rapportstatusens enda nya EPS-luckor är Epiroc A/B och Peab B. EQT:s Q3-redogörelse är ett dokumenterat undantag utan EPS.

| Aktie | Rapportdatum | Föregående manuell TV TTM, SEK | Diluted Q3, SEK | Diluted Q3 föregående år, SEK | Ny härledd TTM, SEK |
|---|---|---:|---:|---:|---:|
| Epiroc A | 2026-10-28 11:30 CET | 7,3082 | 2,00 | 1,62 | 7,6882 |
| Epiroc B | 2026-10-28 11:30 CET | 7,3082 | 2,00 | 1,62 | 7,6882 |
| Peab B | 2026-10-28 08:00 CET | 7,3157 | 3,45 | 2,89 | 7,8757 |

Registreringen använder befintlig regel: föregående prioriterade TTM + diluted kvartals-EPS − diluted jämförelsekvartal. Det är inga nya TradingView-observationer. Officiella jämförelsekvartal sparas separat som manualDilutedEPS; tidigare Yahoo-observationer behålls. Historiska publiceringsdatum för jämförelsekvartalen anges inte utan ny verifiering. Aktuella rapporter gäller samma svenska datum som publiceringen. Alla komponenter och tidigare manuella baser är i SEK; ingen valutaomräkning görs.

## Källor och rimlighetskontroll

- Epiroc, rapport s. 3 och 16: https://www.epirocgroup.com/content/dam/epiroc/corporate/documents/quarterly-results-presentations-/2026-q3/english/Epiroc%20Interim%20Report%20Q3%202026.pdf . Diluted EPS verifieras uttryckligen, separat från basic EPS. Publicering 11:30: https://www.mfn.se/cis/a/epiroc/epiroc-interim-report-q3-2026-5a3bbdfa . Kalendern överensstämmer.
- Peab, rapport s. 2 och 24: https://mb.cision.com/Main/424/4416131/4341946.pdf . IFRS EPS efter utspädning används. Pressmeddelandets segment-EPS 3,67 och IFRS basic 3,48 används inte. Officiell publicering 08:00: https://news.cision.com/se/peab/r/peab-delarsrapport-peab-vaxer-med-starkt-lonsamhet,c4416131 . Kalendern överensstämmer.

Antagandet att kvartalsbryggan motsvarar direkt beräknad R12 är inte exakt när aktieantalet ändras. Peabs officiella diluted IFRS R12 är 7,83 SEK, medan projektets befintliga regel från manuell TV-bas ger 7,8757 SEK (skillnad 0,0457). Avrundade kvartalstal och skiftande vägt aktieantal kan ge avvikelser. Befintlig metod behålls; värdet utges inte för att vara direkt rapporterad R12 eller ny TradingView-avläsning.

Samtliga 3 828 tidigare kanoniska rapportposter jämfördes fält för fält mot utgångsläget och är oförändrade. Tre rapportposter tillkommer. Tidigare manuella värden, Hexpols datumkorrigering till 23 oktober och pausade verifieringar bevaras. ABB/EAST:s tidigare dokumenterade valutaverifiering kvarstår; inga nya SEK-värden uppskattas. Äldre historiska datumluckor hanteras separat från aktuella EPS-luckor.

## Genomförd validering

387 Python-tester och 17 relevanta JavaScript-tester passerar. Full omräkning med `src.pipeline --skip-fetch --skip-dividends`, begränsning av webbperioden och `src.validate_outputs` godkänner 119 aktier och 307 103 prisrader. Rapportstatus per 28 oktober har inga saknade förväntade EPS; EQT kvarstår som publicerad redogörelse utan EPS.

Alla 197 540 frysta poänghistorikrader är exakt oförändrade mot utgångsläget. Senaste färdiga stängningsdag är 27 oktober. De tre aktiernas split-exporter ändrar endast aktuell EPS/P-E och rapportmetadata; historiska poäng, historiska signaler och affärer är oförändrade. Rapportdagens slutliga score_after är tom tills stängningsdata för 28 oktober finns. Befintliga signal- och backtestregler har körts utan att skapa framtida stängningskurser. Aktuell P/E ändras från 34,4818 till 32,7775 för Epiroc A, 29,4737 till 28,0170 för Epiroc B och 13,2181 till 12,2783 för Peab B.
