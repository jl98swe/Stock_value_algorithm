# EPS TTM före och efter rapport, 2026-10-27

Rapporttabellen använde EPS_TTM från värderingsmodellens beräkningsram. För TradingView-kalibrerade aktier används tv_period_end_state, där den nya rapportens EPS placeras på periodslutet. Båda handelsdagarna runt publiceringen innehöll därför redan den nya EPS-nivån. Rapportregistret hade däremot kvar tidigare perioders manuella EPS.

Jämförelsen läser nu senaste tidigare verifierade rapportperiod som gällde före publiceringsdagen, respektive den aktuella rapportposten. Periodreferenser och ursprung exporteras för granskning. Det nya värdet hämtas aldrig från modellramen. Befintliga skydd mot att Yahoo ersätter manuella värden är oförändrade. Saknat historiskt TTM kan endast ersättas med fyra sammanhängande jämförbara kvartal i samma valuta som var observerade före rapporten; annars visas streck. Inga rapportregister, poäng eller signaler har skrivits om.

Varje sida visar sin sparade originalvaluta: exempelvis kan en tidigare manuell SEK-siffra följas av en officiell USD-siffra. Ingen ny valutakonvertering görs för presentationen. EPS-jämförelsen visar därför rapportuppgifter och kan skilja sig från modellens valutajusterade EPS. Modellens poäng/kurser behålls separat.

Kontrollfönster: 2026-09-30–2026-10-27 (20 XSTO-handelsdagar). Samtliga 77 verifierade rapportposter i fönstret finns med. Alla 77 har före- och eftervärden, samtliga från sparade rapportposter; inga kräver kvartalsrekonstruktion. Inget före/efter-par är oförändrat i detta material. Detaljer finns i recent_report_eps_audit_2026-10-27.csv.

Verifierade mot sparade rapportposter:

| Aktie | Före | Efter |
|---|---:|---:|
| Nordea | 15,3227 SEK | 15,6218 SEK |
| Atlas Copco A | 5,4590 SEK | 5,6690 SEK |
| Volvo A | 17,6252 SEK | 19,2052 SEK |

Avgränsning: detta verifierar jämförelsen mot projektets sparade, verifierade uppgifter. Det är ingen ny extern granskning av varje bolags rapport eller tidigare manuell korrigering.

Validering: 378 Python-tester och 46 Node-tester passerade. Regressionstester täcker identisk modell-EPS på båda sidor, olika perioder med samma EPS, noll/negativa värden, saknad historik, separata valutor, komplett/ofullständig kvartalsrekonstruktion, sparning/återläsning och nästa rapport. Rapportexportens övriga priser, poäng och metadata jämfördes med föregående export och är identiska.
