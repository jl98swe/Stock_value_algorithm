# Rapportkomplettering 29 oktober 2026

Utgångspunkt: main fc49fb9840ddd4476bebd1e559b59697015eb04f.

Inventeringen omfattar webbexportens senaste 20 handelsdagar och samtliga förfallna rapporthändelser i report_data_status per 29 oktober (svensk tid). 90 poster i recent_report_eps_audit_2026-10-29.csv: 83 kompletta, tre från senaste chatten undantagna (Epiroc A/B och Peab B) och fyra nya kompletteringar. De enda nya förväntade EPS-luckorna är Boliden, Nolato B och Sweco A/B. EQT är sedan tidigare dokumenterat som redogörelse utan EPS. Avnoterade FOI ingår inte i det aktiva universumet.

| Aktie | Publicering CET | Föregående manuell TV TTM SEK | Diluted Q3 SEK | Diluted Q3 föregående år SEK | Ny härledd TTM SEK | Direkt rapporterad diluted R12 SEK |
|---|---|---:|---:|---:|---:|---:|
| Boliden | 2026-10-29 13:00 | 44,6319 | 13,69 | 8,07 | 50,2519 | 50,25 |
| Nolato B | 2026-10-29 07:45 | 2,6580 | 0,64 | 0,80 | 2,4980 | 2,50 |
| Sweco A | 2026-10-29 07:20 | 6,3027 | 1,44 | 1,17 | 6,5727 | 6,57 |
| Sweco B | 2026-10-29 07:20 | 6,3027 | 1,44 | 1,17 | 6,5727 | 6,57 |

## Källor och definitioner

Boliden: https://investors.boliden.com/sites/boliden-ir/files/pr/202610291842-1.pdf s. 16, tabell och fotnot bekräftar att inga potentiella aktier finns och därmed ingen utspädningseffekt. Kvartal 13,69 (8,07), R12 50,25 SEK. Pressmeddelande https://investors.boliden.com/sites/boliden-ir/files/pr/202610291842-2.pdf s. 2 verifierar publicering kl. 13:00 CET.

Nolato: https://storage.mfn.se/f882041f-1f6f-4c47-9101-62c0016c2c6b/nolato-q3-2026-kvartalsrapport.pdf s. 2 anger EPS före och efter utspädning 0,64 (0,80) SEK samt R12 2,50. Publicering kl. 07:45 CET enligt https://www.nolato.com/sv/investerare/investerarinformation/finansiella-rapporter-och-presentationer/2026/strategiska-forvarv-och-stark-organisk-tillvaxt-for-medical-solutions/ .

Sweco: https://mb.cision.com/Main/1356/4416736/4344269.pdf koncernens resultaträkning anger diluted 1,44 (1,17), R12 6,57 SEK. Basic jämförelse 1,18 används inte. Officiellt rapportmeddelande och publicering kl. 07:20 CET: https://news.cision.com/sweco/r/interim-report-january---september-2026-sweco-ab--publ-,c4416736 . Samma koncern-EPS för A/B.

Alla rapportdatum stämmer med befintliga kalendrar. EPS gäller samma svenska publiceringsdag. Samtliga komponenter och manuella baser är i SEK; ingen ny valutaomräkning. Föregående års kvartal sparas som manualDilutedEPS med källa, utan påhittat historiskt publiceringsdatum. Yahoo-observationer behålls.

## Rimlighetskontroll och kvarstående frågor

Projektets befintliga regel behålls: föregående prioriterade TTM + aktuell diluted kvartals-EPS − motsvarande diluted kvartals-EPS föregående år. Dessa värden är härledda från manuella TradingView-baser, inte nya TradingView-avläsningar. Antagandet att kvartalsbryggan är exakt lika med bolagets R12 kan fallera vid avrundning och ändrat vägt aktieantal. Skillnaderna mot direkt R12 är här +0,0019, −0,0020 respektive +0,0027 SEK; ingen metodändring görs.

Tidigare manuella värden och rapporter skyddas genom jämförelse mot utgångsläget. Äldre ABB/EAST-valutaverifiering och historiska datumluckor kvarstår separat. EQT:s Q3-redogörelse saknar EPS enligt dokumenterat undantag.

## Validering

Ordinarie Python-tester avgränsas till tests/ i pytest.ini: skriptet scripts/test_alert_smtp.py är ett manuellt SMTP-verktyg som kräver hemligheter och ska inte exekveras under pytest-insamling. Rapport- och inmatningsgränssnittets 17 JavaScript-tester passerar. Full pipeline körs med --skip-fetch --skip-dividends, följt av limit_dashboard_window och validate_outputs. Rapportdagens slutliga poäng och handelssignaler väntar på stängningskurser för 29 oktober; inga framtida stängningsdata skapas.
