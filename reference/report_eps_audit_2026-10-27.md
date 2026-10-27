# Slutkontroll av rapportkomplettering 27 oktober 2026

Samtliga 119 bevakade tickers har inventerats mot rapportkalender, tidigare rapportkontroller och kanoniska rapporter. Aktuella MFN-flöden granskade för 112 tickers; sju utan konfigurerat flöde kontrollerade via officiella rapporter/kalendrar (Balder, Lundin Mining, MTG, Nordea, SCA, SEB och Handelsbanken). Scandics nya inbjudan räknas inte som publicerad rapport. Sex nya rapporter identifierades efter föregående rapportkontroll.

Under arbetet publicerade en annan körning fem av kompletteringarna via PR 105 och 106. Dessa redan registrerade manuella rapportvärden bevaras. Utgångspunkt för denna slutliga komplettering är main 9b23ae8c8f1fabe1cf30c9315801a7ea44c1fd00. Endast CTT läggs till; ingen dublett skapas för de övriga fem.

| Aktie | Rapportdatum | Tidigare TTM SEK | Registrerad ny TTM SEK | Underlag |
| --- | --- | ---: | ---: | --- |
| ALLEI.ST | 26 oktober | 3,6416 | 4,1216 | Föregående manuell TV-bas + 0,82 - 0,34 |
| ASSA-B.ST | 27 oktober | 14,7582 | 15,2582 | Föregående manuell TV-bas + 4,24 - 3,74 |
| CTT.ST | 27 oktober | 4,5574 | 3,1500 | Direkt rapporterad R12, ingen utspädning |
| HANZA.ST | 27 oktober | 6,2697 | 6,5397 | Redan registrerad kvartalsbrygga + 1,96 - 1,69 |
| SOBI.ST | 27 oktober | 3,8500 | 18,8600 | Föregående manuell TV-bas + 6,69 - (-8,32) |
| VBG-B.ST | 27 oktober | 16,4133 | 16,7033 | Redan registrerad kvartalsbrygga + 4,16 - 3,87 |

Samtliga värden är SEK; ingen ny valutaomräkning. Hanza och VBG:s nya manuella härledningar skrivs inte över med avrundade direkt-R12-tal. Se också report_eps_followup_2026-10-27.md för den tidigare körningens källor och validering.

## CTT: kompletterande definitionsbevis

[CTT:s svenska Q3-rapport, s. 1](https://storage.mfn.se/dc7175ef-3f53-4295-a86e-4b7b7ce34dc3/ctt-systems-ab-delarsrapport-q3-2026.pdf) redovisar direkt rullande EPS 3,15 SEK, kvartalet 1,38 och jämförelsekvartalet 1,15. Rapporten publicerades den 27 oktober 08:00 CET och visar oförändrat aktieantal samt inga relevanta kapitalhändelser.

Den tidigare körningen lämnade posten oregistrerad eftersom Q3 inte uttryckligen skriver diluted. [Årsredovisning 2025, not 8 och principen för aktierelaterade ersättningar](https://storage.mfn.se/6c9c61a7-6107-4fa7-803b-06e02b6a55dd/sv-ctt-ar-2025-final.pdf) bekräftar att utestående teckningsoptioner saknas, att någon utspädning inte beräknas och att inga relevanta optionsprogram finns. Q3 anger samma principer som senaste årsredovisning, oförändrat antal aktier 12 529 443 och inga relevanta nya kapitalhändelser. Sammantaget stödjer detta bedömningen att rapporterad EPS även motsvarar EPS efter utspädning. Slutsatsen är en bedömning utifrån två officiella rapporter, inte en uttrycklig diluted-etikett på Q3-tabellen.

Direkt R12 3,15 används i stället för en brygga från äldre manuell Q2-TTM 4,5574. Den äldre manuella posten ändras inte historiskt. Två verifierade kvartalskomponenter läggs till utan att ta bort Yahoo-observationerna; jämförelsekvartalets publiceringsdatum gissas inte. Den tidigare verification_pending-kontrollen bevaras som historik och en ny registered-kontroll tillkommer.

## Rimlighetskontroll

Kvartalsregeln antar att äldre TTM och kvartalskomponenterna är jämförbara. Avrundning och ändrat genomsnittligt aktieantal kan ge skillnader mot direkt R12. Hanza redovisar 6,53, medan redan registrerad härledning ger 6,5397; VBG redovisar 16,71 jämfört med registrerade 16,7033. För Sobi ger alternativ helårs-/niomånadersbrygga 18,96 jämfört med befintlig kvartalsregels 18,86. Inga av dessa härledningar märks som nya direkt verifierade TradingView-observationer och de befintliga manuella värdena skrivs inte över.

## Tidigare luckor och valuta

Hexpol är redan komplett med Yahoo trailingDilutedEPS 5,25 SEK, giltig från 23 oktober. EQT:s redogörelse utan EPS kvarstår som dokumenterat undantag. Tidigare valutauppföljning av ABB (USD till SEK) och Eastnine (EUR till SEK) kvarstår. Alla användarverifierade SEK-värden samt pausade verifieringar lämnas orörda.

## Verifiering

Tidigare körning rapporterar 380 godkända Python-tester, omräknade webbdata och verifierad Pages-publicering för de fem redan registrerade rapporterna. Denna komplettering testas på nytt med befintlig GitHub Actions CI: samtliga kärntester, frontendtester, full pipeline utan ny kurshämtning, historikbegränsning och utdata-/valutavalidering. Manuella EPS-registreringar inkluderas i CI:s sökvägsfilter så även dataändringar får dessa kontroller.

Efter merge kör befintlig publiceringspipeline om webbdata och saknad-EPS-status. Slutlig status och publicering verifieras separat; lokal fullkörning räknas inte som godkänd eftersom körmiljön tappade körningsfilerna.


## Slutförd datavalidering

PR 108 är mergad till main som 96213e49de01445591194fef6dc3a33226c355be. CI 40537688595 passerade: 387 Python-tester, frontendtester, full pipeline, historikbegränsning och utdata-/valutavalidering för 119 aktier och 306 985 prisrader. Publiceringspipeline 40538509898 sparade omräknade webbdata i abf9a5b476d337a055c83b65ec1a635d111860d4.

Den exporterade rapportstatusen har missing_data=[]; EQT kvarstår enbart som published_without_eps. Alla sex nya rapporters före-/eftervärden är verifierade i reports.json. CTT:s dashboard ändrar endast latest (EPS och P/E) och report; poäng, signaler, positioner och alla strategier är exakt oförändrade jämfört med föregående main. Hela den frysta poänghistorikens Git-blob är oförändrad mot 9b23ae8. Senaste tillgängliga stängningskurs är fortfarande 26 oktober, så rapporten från 27 oktober skapar inga påhittade slutkurser eller historiska signaler.
