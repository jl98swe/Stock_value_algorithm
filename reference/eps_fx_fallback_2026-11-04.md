# Valutaomräknad EPS med diskret källmarkering

Godkänd reservmetod: beräkna hela diluted EPS TTM i rapportvalutan och multiplicera med senaste tillgängliga valutakurs strikt före rapportdagen. Rapportdagens slutkurs får inte användas för en morgonrapport. Kursen och dess datum fryses vid registreringen; ingen daglig omräkning av samma TTM. Saknad, ogiltig eller mer än sju kalenderdagar gammal valutakurs stoppar registrering.

| Aktie | Tidigare TTM SEK | Native brygga EUR | Ny TTM SEK |
|---|---:|---|---:|
| Cibus | 11,4241 | 1,030 + 0,350 − 0,230 = 1,150 | 12,6030228615 |
| Kambi | 3,2318 | 0,413 + 0,126 − 0,036 = 0,503 | 5,5124526081 |
| Medicover B | 6,1103 | 0,559 + 0,169 − 0,129 = 0,599 | 6,5645310383 |

Samtliga använder EUR/SEK 10,9591503143311 från 3 november för rapportdatum 4 november 2026. Föregående native diluted TTM finns i earnings_initial.csv (Q2 2026, Yahoo trailingDilutedEPS). Aktuella och föregående års kvartal är officiellt verifierade manualDilutedEPS från rapportkompletteringen tidigare samma dag. Den gamla manuella SEK-basen används inte i EUR-bryggan och räknas inte tillbaka till EUR.

Källor:

- Cibus rapport s. 22: https://cdn.bequoted.com/media/1/abc66dbc-7b11-483a-abe2-0590b4fd1cf9/Cibus-Interim-report-Jan-Sep-2026_ENG.pdf
- Kambi rapport s. 1 och 15: https://storage.mfn.se/0bf62f1d-d58d-4015-b32f-cf072d186f00/kambi-group-plc-q3-2026-report.pdf
- Medicover, hela koncernen: https://mfn.se/a/medicover/interim-report-july-september-2026
- Valutakurs: sparad Yahoo EURSEK=X, data/fx/fx_updates.csv.

Metodbegränsning: detta är en spårbar uppskattning av SEK-värdet, inte en verifierad TradingView-avläsning. Tidigare små avvikelser för enskilda bolag bevisar inte att kursmetoden exakt motsvarar TradingView generellt. Kambis avrundade helårs-/niomånadersbrygga ger 0,238 + 0,335 − 0,072 = 0,501 EUR, medan etablerad kvartalsbrygga ger 0,503 EUR; ändrat vägt aktieantal och avrundning kan påverka. Medicover-bryggan motsvarar rapporterat diluted R12 för hela koncernen 0,599 EUR; kvarvarande verksamhet 0,598 EUR används inte.

Metadata lagras i den kanoniska rapportposten med eps_fx_fallback_v1, original-TTM, originalvaluta, målsvaluta, kurs och kursdatum. Omräkningarna sparas också i eps_fx_conversions.csv, som bevaras när samma period senare ersätts med verifierat TradingView-värde. Befintliga manuella periodvärden ersätts aldrig av den automatiska reservvägen. Manuella SEK-värden blir inte valutaomräknade på nytt.

Frontend visar en streckad understrykning vid aktuell EPS på aktiesidan, varje berörd före-/eftercell på rapportsidan och Nuvarande EPS samt sparade EPS-värden på Nyheter och data. Aktuella signaler och aktiva positioner får en liten informationsikon när aktuell värdering använder omräknad EPS. Historiska affärsrader markeras inte utifrån dagens datakälla. Förklaringen öppnas med hovring, klick eller tangentbord och stängs med Escape eller klick utanför. Den innehåller originalvärde, valutor, kursdatum och länk till komplettering med TradingView.

Saknad-EPS-varningen försvinner först när en användbar ny kanonisk TTM finns. Omräkningsmarkeringen försvinner från aktuell värdering när TradingView ersätter posten; historiskt omräknade EPS-poster behåller sin källinformation. Ordinarie pipeline bygger om poäng, historik och strategier enligt befintliga regler.
