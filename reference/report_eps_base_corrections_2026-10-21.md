# Korrigerade TTM-baser från 7 oktober 2026

Sex tidigare Yahoo-baserade Q3-härledningar räknas om från tidigare verifierad manuell TradingView TTM. Rapporternas diluted kvartalskomponenter, periodslut, valuta och publiceringsdatum behålls.

| Aktie | Rapportdatum | Tidigare TTM | Manuell TV-bas | Kvartal 2026 | Kvartal 2025 | Ny TTM SEK |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| INDU-A.ST | 2026-10-07 | 124.6100 | 145.5363 | -3.8300 | 17.1000 | 124.6063 |
| ERIC-B.ST | 2026-10-15 | 5.8200 | 7.3818 | 1.7700 | 3.3300 | 5.8218 |
| AZA.ST | 2026-10-16 | 18.4400 | 17.8906 | 4.8800 | 4.3500 | 18.4206 |
| INVE-A.ST | 2026-10-16 | 70.0600 | 85.6700 | 3.8900 | 19.5200 | 70.0400 |
| TEL2-B.ST | 2026-10-20 | 14.6700 | 14.5075 | 2.0200 | 1.8500 | 14.6775 |
| LIME.ST | 2026-10-20 | 9.2200 | 8.9540 | 2.1400 | 1.9000 | 9.1940 |

Beräkning: manuell föregående TV TTM + aktuell diluted kvartals-EPS − motsvarande diluted kvartals-EPS föregående år. De nya värdena är härledningar, inte nya direkt verifierade Q3-TTM-värden från TradingView. Källval, bas och komponenter finns per kanonisk rapport och i auditloggen.

## Pausad verifiering av aktuella TV-värden

Användaren vill först verifiera metric, period och valuta för Avanza 18,4233, Investor A 70,0381, Platzer B 6,8437 och Ericsson 5,8170. Kontroll och registrering av dessa aktuella TV-uppgifter är pausad och sparad på Att göra-listan. De uppgifterna används därför inte i denna korrigering. Tidigare verifierade Q2-baser får fortsatt användas. Platzer ligger oförändrat på 6,8500, direkt avläst ur rapporten.

## ABB

ABB ändras inte. Senast verifierad diluted kvartals-EPS 0,65/0,66 USD gav 2,7500 USD enligt den tidigare USD-härledningen. Valutamotorn konverterar hela USD-värdet till SEK. Det tidigare manuella Q2-värdet 26,4067 SEK finns kvar. Granskningen har inte visat ett nytt belagt räknefel i den publicerade USD-beräkningen; ingen blandning av SEK-bas och USD-komponenter görs.

## Omräkning och verifiering

Endast sex kanoniska Q3-poster ändras; samtliga andra rapporter, även ABB, Nordea, Platzer, DYVOX, Handelsbanken och tidigare Q2-värden, är exakt oförändrade. Äldre auditinmatningar bevaras.

Poänghistoriken räknas om med befintlig värderingsmotor och samma gränser som --recalculate-score-from. Endast de sex aktierna från sina respektive rapportdatum får nya frysta rader. Övriga ticker-/datumrader och alla poäng före respektive rapportdatum har jämförts exakt och är oförändrade. Inga nya priser hämtas.

| Aktie | Omräknade rader | Ändrade poängvärden |
| --- | ---: | ---: |
| INDU-A.ST | 10 | 10 |
| ERIC-B.ST | 4 | 0 |
| AZA.ST | 3 | 1 |
| INVE-A.ST | 3 | 1 |
| TEL2-B.ST | 1 | 1 |
| LIME.ST | 1 | 1 |

27 riktade tester för manuell EPS, prioritet, valuta, fryst poänghistorik och rapportmedveten omräkning passerade. Befintligt EPS-workflow bygger och validerar webbdata, backtest och handelssignaler efter merge.
