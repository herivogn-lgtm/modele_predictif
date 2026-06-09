# 10 — Couche d'orchestration GEE sur grille 1 km + scaling 181k cellules (Pipeline 04)

Status: ready-for-human

> Recâblage code livré. Reste la **validation GEE live** (auth requise, non
> pytest-able) : `python src/04_extraction_variables_gee.py --test-only`.

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## Contexte

L'issue 03 a pivoté les **helpers ee-free** de `region_id` vers `cell_id`
(`src/extraction_gee_helpers.py`, 11 tests verts). La **couche d'orchestration GEE**
`src/04_extraction_variables_gee.py` n'a **pas** été adaptée : elle appelle encore les
anciennes signatures région (`load_regions`, `regions_table`, `assemble_decades(...regions...)`,
`assert_decade_completeness(n_regions=...)`, baseline CHIRPS clé `region_id`,
sources statiques/ERA5/ENSO clé `region_id`).

## What to build

Réécrire la couche ee pour extraire NDVI/EVI, LST, CHIRPS **sur la grille 1 km clipée**
(`data/processed/01_grille_1km.parquet`, issue 01) au lieu de `region_naturelle` :

- Charger la grille 1 km, reprojeter en EPSG:4326, construire la FeatureCollection avec
  les propriétés `cell_id` / `AIRE_CODE`.
- Câbler les builders dynamiques (`_chirps_image`/`_ndvi_evi_image`/`_lst_image`) +
  `extract_source` + `assemble_decades(calendar, cells_table, ...)` +
  `assert_decade_completeness(df, n_cells)` + `validate_output` (clés cellule).
- Baseline CHIRPS recalculée par cellule × décade-of-year.
- `config_gee.PATHS` : `regions_shp` → chemin de la grille 1 km.

## Obstacle principal — scaling 181k cellules

La grille 1 km clipée fait **~181 000 cellules** (cf. Findings issue 01), pas ~1 800.
Un `reduceRegions` sur 181 000 features vectorielles en un seul `getInfo` dépassera très
probablement les limites de calcul/réponse GEE — même par décade, même avec la bissection
des specs existante.

Options d'archi à trancher (needs-info) :

1. **Tiling par secteur** (`AIRE_CODE`/`SECT_NO`, 12 secteurs) : borne le nombre de cellules
   par getInfo. Simple, réutilise `reduceRegions`. À valider que chaque secteur tient.
2. **`image.sampleRegions` / échantillonnage par centroïde** : 1 point par cellule au lieu
   d'un polygone — plus léger, mais perd min/max/std intra-cellule (souvent OK à 1 km).
3. **Export d'image rééchantillonnée à 1 km** (Export.image → lecture raster client-side,
   snap aux `cell_id`) : robuste à l'échelle, mais sort du pattern getInfo actuel.

## Hors périmètre (à décider séparément)

- Les sources statiques/ERA5/ENSO/land-cover encore dans le fichier ne sont **pas** demandées
  par l'issue 03 (NDVI/EVI, LST, CHIRPS uniquement). Décider si on les conserve (et donc on
  les pivote aussi) ou si pipeline 04 est trimé aux 3 sources dynamiques.

## Décisions tranchées (2026-06-08)

- **Archi scaling → tiling par chunk de cellules + échantillonnage centroïde**
  (option 1 ⊕ 2). `image.sampleRegions` sur 1 point/cellule (pas de polygone) ;
  tuiles de `CELL_CHUNK_SIZE=5000` cellules (37 tuiles) ; réduction décadaire
  mappée côté serveur + bissection des décades si getInfo sature. Justif. : à 1 km,
  CHIRPS (~5,5 km) et LST (~1 km) ont ≤ 1 pixel/cellule → min/max/std intra-cellule
  = bruit ; on ne garde que la **moyenne**. Options polygones/export écartées
  (lourdes / gros rewrite).
- **Périmètre → 3 sources dynamiques** (NDVI/EVI, LST, CHIRPS + anomalie). ERA5,
  land-cover, DEM, texture sol, ENSO/ONI **retirés** (hors issue 03 ; à rouvrir en
  ticket dédié si le FE 05 les réclame).

## Implementation notes (2026-06-08)

- `src/config_gee.py` : `regions_shp`→`grille_parquet` ; `output_parquet`→
  `output_dir` (**dataset Parquet partitionné** `part-XXXX.parquet` ; à ~141 M
  lignes la table ne tient pas en 1 fichier) ; ajout `CELL_CHUNK_SIZE` ; constantes
  ERA5/LC/OLM/DEM/ENSO supprimées.
- `src/04_extraction_variables_gee.py` réécrit : `load_grid` (centroïdes UTM→4326),
  `chunk_cells`, `points_fc` (FC construite **côté serveur** depuis 2 listes plates,
  pas N `ee.Feature` clients), `_sample_specs` (sampleRegions + bissection),
  baseline CHIRPS par cellule × décade-of-year (`doy_id`), boucle **tuile = unité
  bout-en-bout** (extract→assemble→anomalie→completeness→validate→write part).
- Vérifié hors GEE : import module, `load_grid` (lon 43,2–47,4 / lat −25,6–−20,0 ;
  37 tuiles), chaîne assemble→anomalie→completeness→validate sur sources synthétiques
  (décade 1–30, colonnes cellule). Helpers ee-free : 11 tests verts.
- **Non vérifié** (auth GEE requise) : round-trip `sampleRegions`/`getInfo`,
  noms de propriétés réels renvoyés par sampleRegions, construction server-side
  `points_fc`. → lancer `--test-only`.

## Variante Export.table livrée (2026-06-08, option 3/B)

Le getInfo (#04) reste correct mais demande **~86 600 appels** à 181k cellules
(plancher imposé par le plafond GEE de 5000 éléments/getInfo). Variante scalable
ajoutée : **`src/04b_export_variables_gee.py`** (Export.table, pas de plafond).

- Primitives GEE (images, QA, `points_fc`, `sample_fc`, baseline) extraites dans
  **`src/extraction_gee_sources.py`**, partagées par #04 et #04b → valeurs identiques.
  #04 refactoré pour les importer (registre `DYNAMIC_SOURCES`).
- 04b en 3 étapes (Drive = tampon) : `submit` (52 tâches : 3 sources × 13 tuiles
  toutes années + 13 baseline) → `status`/`cancel` → télécharger Drive →
  `assemble` (CSV→parquet partitionné, par tuile pour borner la mémoire).
- Config : `POINT_EXPORT_TILE=15000`, `EXPORT_DRIVE_FOLDER`, `PATHS["exports_dir"]`.
- Vérifié hors GEE : imports, refactor #04, `grid_tiles` (13 tuiles/52 tâches),
  `_flatten_specs` (decade_id unique), chaîne `assemble` sur CSV synthétiques
  multi-shards. Helpers ee-free : 11 verts. **Non vérifié** (auth) : soumission/
  exécution des tâches Export, format réel des CSV Drive.

## Aval impacté (hors périmètre, à traiter)

- `src/feature_engineering_05.py` lit `04_variables_environnementales.parquet`
  (fichier) → doit lire le **répertoire** `output_dir` et clé `cell_id` (plus
  `region_id`). Adaptation pipeline 05 = ticket séparé.

## Notes

- Couche non testable en pytest (dépend de `ee` + auth) → validation via
  `python src/04_extraction_variables_gee.py --test-only` sur 1 cellule × 1 décade.
- Voir mémoire `[[pipeline-04-gee-refactor]]`.

## Blocked by

- `.scratch/severite-phase-forecast/issues/03-extraction-gee-decadaire-1km.md`
