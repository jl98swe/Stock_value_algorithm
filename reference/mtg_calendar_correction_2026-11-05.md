# Rättelse av MTG:s rapportförsäljning

Kalendern hade korrekt rapportdatum 5 november 2026 arkiverat från 15 september. `_combined_schedule` valde ändå bara en automatisk rad per aktie. MFN:s senare rapport 4 februari 2027 trängde undan Börskollens närmare datum 5 november på grund av källprioriteten. Det var ett bearbetningsfel, inte ett verifierat fel i någon av källornas datum.

Urvalet prioriterar nu källor inom ett rapporttillfälle (samma befintliga 45-dagarsavstånd som vid manuella kalenderkorrigeringar). Separata kvartal behålls. Regressionstest verifierar att en kommande rapport finns med och utlöser försäljning även innan dess EPS registrerats.

Det särskilda bevaringsundantaget för MTG:s novemberrapport från PR #125 tas bort. Den tidigare publicerade simuleringen saknade en försäljning som rätt kalenderdatum motiverar. Den korrekta affären ska ingå:

| Uppgift | Värde |
|---|---|
| Strategi | Rapportundvikande |
| Aktie | MTG-B.ST |
| Position | MTG-B-ST-lot-18 |
| Köpsignal / köp | 18 / 19 augusti 2026 |
| Rapport | 5 november 2026, 07:30 CET |
| Känd kalenderuppgift | 15 september 2026 |
| Försäljning | 4 november 2026, 119,20 SEK |
| Kursunderlag | Sparad Avanza-öppningskurs 4 november 09:00 CET i data/prices/opening_sessions.json |

`history_corrections.json` dokumenterar en addition-only-rättelse av just denna rapportförsäljning. Historikgrinden kontrollerar att dagen är föregående XSTO-handelsdag, att kalenderkunskapen fanns dessförinnan, och att försäljningen stänger en redan publicerad öppen position. Andra priser, datum, positioner, strategier, ändrade köp eller borttagning av affären tillåts inte av denna rättelse.

Det är skilt från värderingspoäng: ändrat rapportdatum får påverka dem från rapportdatumet, inte från kvartalsslutet. Om ett tidigare felaktigt datum redan släppt in EPS för tidigt behöver det felaktiga intervallet också återställas; befintlig omräkning använder därför det tidigare av gammalt och korrigerat rapportdatum. MTG:s verifierade rapportdatum och EPS ändras inte här, så inga historiska värderingspoäng ska ändras alls.

Denna rättelse ersätter beslutet att bevara den saknade MTG-försäljningen i reference/report_eps_audit_2026-11-05.md. Den tidigare texten behålls som spår av föregående publicering.
