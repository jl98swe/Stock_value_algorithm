# Kompletterande rapportkontroll 27 oktober 2026

Utgångspunkt main 0c3cc98b38a98119a650df3c2cae1f3121c9ce68. Rapportstatusens sex luckor granskas; tidigare genomförda uppdateringar upprepas inte.

## Verifierat underlag, SEK

| Ticker | Rapportdatum svensk tid | Tidigare manuell TV TTM | Diluted Q3 | Diluted jämförelsekvartal | Härledd TTM |
|---|---|---:|---:|---:|---:|
| ALLEI.ST | 2026-10-26 11:30 CET | 3,6416 | 0,82 | 0,34 | 4,1216 |
| ASSA-B.ST | 2026-10-27 08:00 CET | 14,7582 | 4,24 | 3,74 | 15,2582 |
| HANZA.ST | 2026-10-27 07:30 CET | 6,2697 | 1,96 | 1,69 | 6,5397 |
| SOBI.ST | 2026-10-27 08:00 CET | 3,85 | 6,69 | -8,32 | 18,86 |
| VBG-B.ST | 2026-10-27 11:39 CET | 16,4133 | 4,16 | 3,87 | 16,7033 |

Befintlig regel: föregående verifierad TTM + kvartalets ojusterade diluted EPS − jämförelsekvartalets diluted EPS. Dessa är härledda TTM, inte nya TradingView-observationer eller direkt redovisade R12-tal. Rapporterna avrundar kvartalskomponenterna; precisionen är därför begränsad trots fyra decimaler i basen. Befintliga manuella värden för tidigare perioder behålls. Ingen ny valutaomräkning görs.

Källor:

- Alleima, s. 1 och 13: https://www.alleima.com/siteassets/documents/ir/2026-q3/alleima-q3-2026.pdf . Publicering 26 oktober 11:30: https://allaaktier.se/alleima/nyheter/alleima-interim-report-q3-2026/1318 . Officiell comparator 0,34 prioriteras före tidigare Yahoo-rekonstruktion 0,35.
- Assa Abloy, s. 12: https://mb.cision.com/Main/7333/4415570/4340384.pdf . Ojusterad diluted comparator är 3,74; rubrikens 3,73 exkluderar jämförelsestörande poster och används inte. Publicering 08:00 framgår av bolagets regulatoriska meddelande: https://www.prnewswire.com/news-releases/assa-abloy-quarterly-report-q3-2026-302920410.html .
- Hanza: https://hanza.com/investor/pressreleases/hanza-interim-report-january-september-2026/ . Regulatorisk publicering 07:30: https://view.news.eu.nasdaq.com/view?id=b007feb6ffb0ce021002dbd3304c08e0f&lang=en&src=listed . Justerad EPS 1,90 används inte.
- Sobi, s. 1: https://www.sobi.com/sites/sobi/files/pr/202610269994-1.pdf . Publicering: https://www.sobi.com/en/press-releases/sobi-q3-2026-report-underpinning-strong-growth-momentum-2492475 . Justerad diluted 6,89 används inte.
- VBG, s. 2: https://storage.mfn.se/b6a02146-a068-4392-aca1-fef8796f23da/vbg-group-q3-2026.pdf . Faktisk publicering 11:39, inte kalenderns uppskattade 09:05: https://mfn.se/a/vbg-group/delarsrapport-9-man-januari-september-2026 .

## Redan korrekt registrerat

- COOR.ST: 2,78 SEK, användarverifierad TradingView diluted TTM, manuell prioritet, rapportdatum 22 oktober. Ingen ny registrering eller dubblett.
- HPOL-B.ST: kanonisk Yahoo trailingDilutedEPS 5,25 SEK har redan effective_date och published_at 23 oktober. Datumbevis i report_date_rechecks.csv gäller YAHOO-2026-09-30. Bolaget bekräftar dagen: https://investors.hexpol.com/en/report/hexpol-ab-publ-interim-report-january-september-2026 . Yahoo-observationens felaktiga report_date 22 oktober och observed_date 26 oktober behålls som rå historik, inte som publiceringsbevis. Ingen ändring av värdet och ingen ny kvartalsbrygga. Bolagets rapport etiketterar inte uttryckligen R12 som diluted; providerdefinitionen är trailingDilutedEPS.

## Kvarstående verifieringslucka

- CTT.ST publicerade 27 oktober 08:00 CET. Rapporten anger kvartals-EPS 1,38 (1,15) och R12 EPS 3,15 SEK, men inte uttryckligen diluted. Definitionen hänvisar till genomsnittligt antal aktier. Varken kvartalsbrygga eller R12 registreras som verifierad diluted utan säkrare underlag. Senaste korrekta manuella värde behålls och varningen ska kvarstå. Källa: https://storage.mfn.se/7c2ba79d-136a-418c-b396-ba0b2a484bbe/ctt-systems-ab-interim-report-q3-2026.pdf och https://www.accessnewswire.com/newsroom/en/industrial-and-manufacturing/ctt-systems-ab-publ.-interim-report-third-quarter-2026-1242405 .

## Valutaproblem – manuell hantering

| Ticker | Problem | Valutor | Tidigare omräkning | Källa |
|---|---|---|---|---|
| ABB.ST | Rapporthärledd diluted TTM behöver jämföras med nytt användarverifierat TradingView-värde i SEK. | USD → SEK | 2,75 USD lagras och omräknas av befintlig värderingslogik. Inget nytt värde registreras. | https://www.eqs-news.com/news/category/abb-ltd-q3-2026-results/50d2285d-3931-4dd6-87c9-175ebf9be15a |
| EAST.ST | Rapporterad diluted R12 i EUR behöver jämföras med TradingView i SEK. | EUR → SEK | 0,31 EUR lagras och omräknas av befintlig värderingslogik. Inget nytt värde registreras. | https://mb.cision.com/Main/13001/4413938/4334001.pdf |

Nordea, Betsson, Autoliv, Evolution och Hexagon har redan lösts med användarverifierade SEK-värden. Pausade verifieringar för Avanza, Investor A, Platzer B och Ericsson förblir pausade. EQT:s redogörelse utan EPS är ett dokumenterat undantag.
