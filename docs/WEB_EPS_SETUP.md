# Manuell EPS från webbplatsen

`review.html` kan registrera utspädd EPS TTM eller utspädd EPS för ett enskilt kvartal. Den första versionen har ingen kontoinloggning. I stället ansluter administratören en personlig fine-grained GitHub-nyckel på sidan.

## Aktivering

1. Skapa en fine-grained personal access token för endast `jl98swe/Stock_value_algorithm` med repository-behörigheten **Actions: Read and write**. Välj en kort giltighetstid. Contents-skrivbehörighet behövs inte för webbläsaren.
2. Öppna Nyheter och data, veckla ut Skrivåtkomst och anslut nyckeln. Den hålls i en JavaScript-closure och rensas när sidan lämnas eller laddas om. Den skickas bara som Authorization-header till `https://api.github.com`.
3. Välj aktie, fyll i rapportuppgifterna och välj Spara och räkna om. Uppgifterna och källan blir offentliga.

En nyckel måste anslutas på nytt efter en omladdning. Rapportuppgifter och ett registrerings-id kan sparas lokalt för att återuppta en osäker överföring; nyckeln lagras aldrig där. Använd Kontrollera / återuppta vid ett nätverksavbrott.

## Data och beräkning

Webbläsaren startar `web_eps_submission.yml` på main. Arbetsflödet delar kön `stock-data-${{ github.ref }}` med övriga dataskrivare och kontrollerar åter alla indata i `src.web_eps_submission`.

- TTM i aktiekursens valuta sparas med befintlig manuell prioritet och börjar gälla på rapportdatumet.
- Kvartals-EPS räknas om med befintliga kontroller för måttdefinition, tidigare TTM, jämförelseperiod och valuta.
- Saknas jämförbart underlag sparas kvartalsvärdet och en förklaring, utan att ersätta aktiv TTM.
- Valutaavvikelser sparas som `currency_review`; ingen automatisk omräkning görs för webbregistreringen. Ett användarverifierat TTM i kursvalutan kan registreras separat.
- Samma registrerings-id kan återupptas utan att skapa en ny rapportpost. Samma id med ändrat innehåll avvisas.

Arbetsflödet bygger och validerar webbdata före commit. Ett offentligt kvitto under `docs/data/manual_requests/` publiceras tillsammans med webbdata. Sidan visar färdigt först när kvittot går att läsa via Pages. Efter commit begär arbetsflödet uttryckligen en Pages-build, eftersom en push med GITHUB_TOKEN inte startar en branchbaserad Pages-build automatiskt.

## Senare inloggning

Byt transporten `createClient` i `docs/assets/eps-entry.js` mot en skyddad backend med användarbehörigheter. Behåll servervalidering, registrerings-id, manuell prioritet och publiceringskvitton. Lägg aldrig en gemensam skrivnyckel i den offentliga JavaScript-koden.

GitHub-dokumentation: [workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), [Pages builds](https://docs.github.com/en/rest/pages/pages#request-a-github-pages-build).
