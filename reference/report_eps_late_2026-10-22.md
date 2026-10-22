# Senare rapporter 22 oktober 2026

Utgångspunkt: aktuell main b5afaa00175258811a27642dc641e16ed8e05a96 (samma fyra källfiler som 79adf6e8435aed3c090c29481085a7496684242c), inklusive de 21 rapporter som kompletterades på morgonen. Betsson lämnas orörd enligt användarens instruktion. Tidigare pausade TradingView-verifieringar förblir pausade.

| Aktie | Periodslut | Publicerad svensk tid | Diluted kvartals-EPS | Jämförelsekvartal 2025 | Ny diluted EPS TTM | Metod |
| --- | --- | --- | ---: | ---: | ---: | --- |
| ATCO-A.ST | 2026-09-30 | 2026-10-22 12:00 | 1,58 SEK | 1,37 SEK | 5,6690 SEK | Tidigare manuell TradingView 5,4590 + 1,58 - 1,37 |
| ATCO-B.ST | 2026-09-30 | 2026-10-22 12:00 | 1,58 SEK | 1,37 SEK | 5,6690 SEK | Samma finansiella EPS för A- och B-aktier |
| EAST.ST | 2026-09-30 | 2026-10-22 14:00 | 0,14 EUR | 0,10 EUR | 0,3100 EUR | Direkt rapporterad diluted R12 oktober 2025-september 2026 |
| SAGA-A.ST | 2026-09-30 | 2026-10-22 15:30 | 6,51 SEK | 2,46 SEK | 19,1200 SEK | Direkt rapporterad diluted R12 för A/B-aktier |

Alla nya rapporter får effective_date 2026-10-22 enligt befintlig regel. Tidigare korrekt manuellt registrerade värden och morgonens kompletteringar bevaras.

## Officiella källor och kontroller

- Atlas Copco: [Rapport för tredje kvartalet 2026](https://mb.cision.com/Main/90/4413756/4333138.pdf), s. 1 och 9. Både aktuell och föregående års kvartals-EPS har kontrollerats som efter utspädning. TTM härleds med den befintliga regeln från prioriterad manuell TradingView-bas 5,4590 SEK, inte Yahoo. [Publicering 12:00](https://mfn.se/cis/a/atlas-copco/atlas-copco-rapport-for-tredje-kvartalet-2026-de75adf0).
- Eastnine: [Delårsrapport januari-september 2026](https://mb.cision.com/Main/13001/4413938/4334001.pdf), s. 23, kolumn 2025/2026 okt-sep, raden resultat per aktie efter utspädning. R12 0,31 EUR ska inte blandas ihop med nio månader 0,27 EUR, helår 2025 0,43 EUR eller förvaltningsresultat per aktie. Hela R12-värdet lagras i EUR och räknas om till SEK av befintlig valutamotor. Tidigare manuell SEK-bas 2,9634 används inte i en formel med EUR-komponenter. [Publicering 14:00](https://mfn.se/cis/a/eastnine/eastnine-ab-publ-eastnine-delarsrapport-januari-september-2026-321ca564).
- Sagax: [Delårsrapport januari-september 2026](https://storage.mfn.se/041dfdba-286b-44a2-93ed-213892967e2f/delarsrapport-q3-2026.pdf), s. 23, kolumn rullande tolv månader, raden resultat per A- och B-aktie efter utspädning. R12 19,12 SEK avser nettoresultat efter D-aktiernas utdelning. Det är inte nio månader 13,99 SEK eller förvaltningsresultat R12 12,92 SEK. [Publicering 15:30](https://mfn.se/a/sagax/delarsrapport-januari-september-2026).

Rapporttabellerna har kontrollerats både som extraherad text och visuellt. De uppdaterade publiceringstiderna för Atlas Copco och Sagax skiljer sig från morgonens kalenderprognoser; faktisk publicering används som bevis, datumet är oförändrat.

## Antagande och begränsning

Atlas Copcos befintliga kvartalsregel förutsätter jämförbara diluted EPS-komponenter. Avrundning och ändrade aktieantal kan ge en annan TTM än direkt leverantörsrapporterad TTM. 5,6690 är därför en härledning från tidigare verifierad TV-bas, inte ett nytt direkt verifierat TV-värde. Inga nya beräkningsregler införs.

## Validering

28 riktade Python-tester för manuell EPS, prioritering, valuta, rapportstatus och fryst poänghistorik samt 6 JavaScript-tester för rapporttabeller och varningar passerade. Samtliga 3788 tidigare rapportposter bevaras exakt, inklusive dagens ordinarie uppdatering. Fyra rapportposter, åtta kvartalskomponenter, fyra registreringsposter och fyra kontrollposter har lagts till; Betsson är orörd. Pipeline och publicering kontrolleras före avslut. Befintligt EPS-workflow bygger och validerar webbdata efter merge.
