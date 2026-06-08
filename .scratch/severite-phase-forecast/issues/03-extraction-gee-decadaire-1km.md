# 03 — Extraction GEE décadaire sur grille 1 km (Pipeline 04)

Status: ready-for-agent

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Extraire les covariables de télédétection via Google Earth Engine, **agrégées à la décade**
sur la **grille 1 km** issue de l'issue 01 :

- NDVI/EVI (MODIS / Sentinel-2)
- LST (MODIS)
- Précipitations (CHIRPS)

Réutiliser le batch d'extraction côté serveur et conserver le module de **helpers ee-free**
pour la testabilité (les tests ne dépendent pas de `ee`). La **lacune de labels 2023-2024**
ne doit pas casser l'extraction : les covariables GEE restent continues sur toute la fenêtre.

## Acceptance criteria

- [x] Sortie = table cellule 1 km × décade avec NDVI/EVI, LST, CHIRPS *(forme produite par les helpers : `assemble_decades` clé `cell_id`)*
- [x] Agrégation décadaire correcte (col. décade 1–**30** campagne, **pas 1–36** — voir Findings)
- [~] Extraction alignée sur la grille 1 km clipée (issue 01), pas sur la région naturelle *(helpers pivotés ; câblage couche ee → issue 10)*
- [x] Covariables continues malgré la lacune labels 2023-2024 *(calendrier couvre 2023/2024, test dédié)*
- [x] Helpers ee-free testés dans `tests/test_04_extraction_helpers.py` (sans import `ee`)

## Findings — correction doc à traiter

- **Décade 1–30, pas 1–36** : le PRD/critère disaient « Decade 1–36 » (année civile),
  mais le pipeline 03 déjà livré produit `campagne_decade` **1–30** (mois de campagne
  oct–juil) ; c'est la clé de jointure des labels. Décision (2026-06-08) : sortie GEE
  alignée sur 1–30 + `campagne_calc`/`campagne_decade`/`cell_id`/`AIRE_CODE`. Le « 1–36 »
  du doc (PRD ligne 65) est une imprécision à corriger (même ticket doc que l'aire grégarigène).

## Implementation notes (2026-06-08, /tdd)

- **Helpers ee-free pivotés `region_id`→`cell_id`** dans `src/extraction_gee_helpers.py` :
  `assemble_decades(calendar, cells_df, sources)` (méta `cell_id`/`AIRE_CODE`/
  `campagne_calc`/`campagne_decade`, merge sur `["decade_id","cell_id"]`),
  `compute_chirps_anomaly` (clé `cell_id`), `assert_decade_completeness(df, n_cells)`.
  Temporels (`build_decade_calendar` 1–30, `build_specs`, `decade_id`, `parse_reduce_features`)
  inchangés (déjà key-agnostic). Tests : `tests/test_04_extraction_helpers.py` (11 verts).
- **Couche d'orchestration ee NON adaptée ici** (`04_extraction_variables_gee.py` appelle
  encore les anciennes signatures région) → **issue 10**. Raison : à ~181 000 cellules
  (cf. Findings issue 01), `reduceRegions` direct dépasse les limites GEE ; le câblage
  grille 1 km + scaling est un choix d'archi (tiling par secteur / sampleRegions / export),
  non testable en pytest.

## Blocked by

- `.scratch/severite-phase-forecast/issues/01-snap-clip-grille-1km.md`

## Follow-up

- `.scratch/severite-phase-forecast/issues/10-couche-ee-grille-1km-scaling.md`
