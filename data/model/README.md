# GBM-modell för värderingsalgoritmen

Filerna `gbm_model.b85.part1`–`part5` innehåller den exakta 100-trädsmodell som ligger inbäddad i Pine v3.0.

Modellen har extraherats utan ominlärning eller avrundning och lagras här som en förlustfri zlib + Base85-kodning för att hålla Git-filerna hanterbara.

Vid körning bygger `src/model_data.py` temporärt `data/model/gbm_model.json`, verifierar SHA-256 samt följande dimensioner innan modellen får användas:

- `node_feat`: 4 324
- `node_thr`: 4 324
- `node_left`: 4 324
- `node_right`: 4 324
- `tree_root`: 100

Förväntad SHA-256 för den avkodade JSON-filen:

`ea557ed23ef61363b6dd392e0135ea7c3c9d1119036c47b5dea1638234b7a73c`

Den materialiserade `gbm_model.json` är en byggprodukt och behöver inte versionshanteras.
