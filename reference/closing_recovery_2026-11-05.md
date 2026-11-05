# Återhämtning av stängningskurser 4 november 2026

## Omfattning och underlag

- Universumet innehåller 119 aktier. VIVA.ST avnoterades 22 september och ska inte få nya kurser. 118 aktier var noterade 4 november.
- Samtliga 118 aktier saknade publicerad dagsrad för 4 november. Kontroll av varje XSTO-session efter respektive frysta prisbas hittade inga andra luckor.
- Återställningen använder Yahoos ursprungliga underlag från [körning 41922121248](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/41922121248), artifact 13366708837.
- SHA256 för Yahoo-arkivet: `4fa6f2eabb0ee299aa4e34e4fc5312acf55d0fa71d4fdfbf1d05eb03bffe26b7`.
- Avanzas underlag från [körning 41921993467](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/41921993467), artifact 13367986120, innehåller samma 118 aktier.
- SHA256 för Avanza-arkivet: `8748a37a412fce1bc6469d036b0ee0abdf4dc6ff510cbcadda955d6e8e37bac9`.
- Alla slutkurser överensstämmer mellan källorna inom 0,001 kr. Största skillnaden är cirka 0,0000244 kr. Dagshögsta skiljer för ALLEI (Yahoo 93,85; Avanza 93,90) och EQT (Yahoo 321,60; Avanza 321,70). Yahoo behåller prioritet.
- Den avslutande Yahoo-hämtningen den 5 november uppdaterade dessa två dagshögsta till 93,90 respektive 321,70, vilket också överensstämmer med Avanzas underlag. Slutkurserna ändrades inte.

## Varför publiceringen uteblev

Båda källorna hämtade kompletta kurser. Avanzas publicering stoppades av historikskyddet på en förändring i LUMI:s rapportundvikande strategi. Befintliga rapport- och kalenderfixar på main behålls.

Yahoos senare körning stoppades när AXFO:s redan publicerade öppningsaffär fick priset 280,1000061 i stället för 280,10. Den tidigare öppningsobservationen var decimal, medan Yahoos dagsrad lagrade samma pris med float32-precision. Historikskyddet jämförde utförandena och stoppade publiceringen. Det var alltså inte en total frånvaro av kursdata hos leverantörerna.

Den äldre generella Yahoo-återhämtningen kunde dessutom ersätta redan publicerade kursrader i sin sjudagars överlappning. Den vägen används inte längre i dagskursflödet, och den generella hämtningen bevarar nu befintliga rader.

## Skydd och graf

- Luckor fylls med validerade OHLC-rader. Befintliga historiska rader och fryst prisbas bevaras.
- Källan som redan hämtats appliceras före återhämtning, så Avanza förblir reservkälla om Yahoo saknas.
- Historisk status bedöms vid publiceringen, även om ett snapshot varit försenat i kön.
- Publiceringen stoppas om någon förväntad avslutad handelssession fortfarande saknas.
- En publicerad öppningsaffär får behålla sitt exakta pris endast när både originalobservationen och den publicerade affären bekräftar priset, och dagskursen bara skiljer genom float32-representation. Rå OHLC och poäng ändras inte av detta. Historikskyddet är oförändrat.
- THULE:s cache innehöll 80,9451 men gick ut vid midnatt. Därefter återstod en separat öppningsmarkering utan poäng. Grafen förklarar nu denna skillnad och undertrycker inaktuella öppningsmarkeringar.
- En giltig preliminär poäng kopplas till senaste faktiska poäng även när ett mellanliggande datum saknar poäng.

## Verifierat modellresultat

THULE den 4 november: slutkurs 210,20 kr, värderingspoäng 80,9451, EPS TTM 11,5471 SEK. Tidigare publicerad dag var 3 november: 204,60 kr och 64,9129.

Alla tidigare kursrader, inklusive OHLC och MA200, är exakt oförändrade. AXFO:s utförandepris är fortfarande exakt 280,10 kr. Återställningen tillför eller tar inte bort köp- eller säljsignaler i någon av de fem strategierna.

## Tester

[Slutlig PR-kontroll 42050739286](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42050739286) passerade 460 Python-tester, JavaScript-tester, webbläsartest i desktop och mobil, komplett modellbyggnad och exportvalidering. Webbläsartestet kontrollerar giltig preliminär poäng, verklig OHLC, cacheutgång och övergång till publicerad slutkurs.

Valideringen godkände 119 historiska aktier och 307 811 prisrader, inklusive oförändrat historikskydd. [PR #127](https://github.com/jl98swe/Stock_value_algorithm/pull/127) mergades som [11fddc3867aa](https://github.com/jl98swe/Stock_value_algorithm/commit/11fddc3867aa32c8b0f6a54b9defe4046c09725a).

## Publicering och kontroll på webbplatsen

[Dagskurskörningen 42052781855](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42052781855) slutfördes med kompletta kurser och godkänt historikskydd. Omräknade data sparades i [e86dbab58654](https://github.com/jl98swe/Stock_value_algorithm/commit/e86dbab58654552d18a47633127fbbb91d4815cb).

Samtliga 119 publika aktiefiler verifierades mot huvudexporten och det senaste kanoniska OHLC-underlaget: 118 aktier med slutkurs och poäng för 4 november, samt VIVA med korrekt sista handelsdag 22 september. Tidigare publicerade poäng och affärer jämfördes också mot den ursprungliga publicerade versionen och är bevarade. Inga köp- eller säljsignaler till och med 4 november har tillkommit eller tagits bort i någon av de fem strategierna.

[Intradagsuppdateringen 42052781803](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42052781803) och [cacheuppdateringen 42056252764](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42056252764) slutfördes. Cacheuppdateringen räknade om preliminära poäng för 118 av 118 aktier med 4 november som grunddatum.

Vid kontrollen den 5 november visade THULE:s cache kursen 218,80 kr (avslut 15:56) och preliminär poäng 100 för 5 november. Detta är en annan dag än den återställda slutliga poängen 80,9451 för 4 november. Båda värdena visas korrekt i den publicerade grafen.

Ett extra webbläsartest efter publiceringen visade att det syntetiska testets aktiefil och strategiöversikt använde olika datum när repots verkliga data hade avancerat. Testunderlaget korrigerades i [0164b85fffdd](https://github.com/jl98swe/Stock_value_algorithm/commit/0164b85fffdd19313edc62c3c439d419fb9b8384); omkörningens mobil- och desktoptest passerade. Produktbeteendet ändrades inte av denna testfix.

Den avslutande [CI-körningen 42058822952](https://github.com/jl98swe/Stock_value_algorithm/actions/runs/42058822952) passerade därefter samtliga steg, inklusive det korrigerade mobil- och desktoptestet, 460 Python-tester, full modellbyggnad och historikskydd. Även det efterföljande publiceringssteget för Max drawdown slutfördes.

Den publicerade exporten med öppningsobservationer för 5 november sparades i [be3805947ecc](https://github.com/jl98swe/Stock_value_algorithm/commit/be3805947eccec88e0df3822e08e8ca6e2903e2a). Den slutliga grafen kontrollerades även i det levande webbgränssnittet. Inga återstående kursluckor efter den frysta prisbasen hittades vid kontrollen före stängning den 5 november.
