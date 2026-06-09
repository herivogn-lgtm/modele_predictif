# 04 — Features POP + lags anti-fuite + AIRE_CODE (Pipeline 05)

Status: done

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Construire les features prédictives sur la table cellule × décade :

- **POP (plage d'optimum pluviométrique)** : appartenance à la bande **50–125 mm/mois** en
  fenêtre glissante + **persistance multi-mois**. Descripteur écologique dérivé (pas la pluie
  brute), hérité du support CHIRPS, attaché aux cellules 1 km.
- **Lags** : cumul pluie 2–3 décades, NDVI/LST décalés, sévérité historique de la cellule.
- `AIRE_CODE` (AMI/ATM/AD/AGT) comme prédicteur **catégoriel**.

**Interdiction absolue de toute covariable de la décade T+1** (anti-fuite temporelle) : toutes
les features doivent être calculées à partir de décades ≤ T.

## Acceptance criteria

- [x] `compute_pop` : bande 50–125 mm/mois correcte + persistance multi-mois
- [x] `build_lags` : décalages corrects (cumul pluie 2–3 décades, NDVI/LST, sévérité historique)
- [x] `build_lags` : **aucune feature issue de T+1** (test anti-fuite explicite)
- [x] `AIRE_CODE` présent comme variable catégorielle
- [x] Tests dans `tests/test_05_feature_engineering.py`

## Implementation notes (2026-06-09, /tdd)

- **Migration maille `region_id` → `cell_id`** : `feature_engineering_05.py` réécrit pour
  consommer le répertoire GEE `data/processed/04_variables_environnementales/` (déjà en
  maille cellule : `cell_id`, `AIRE_CODE` 1–4, `campagne_calc`, `campagne_decade`).
- **`compute_pop`** : POP 50–125 mm/mois + persistance, groupée par `(cell_id, campagne_calc)`.
- **`build_lags(df, labels=None)`** : lags D-1/D-2 par cellule (`shift`), cumul pluie roulant
  `chirps_cumul_2d`/`_3d` (≤ T), et **sévérité historique** `severite_lag1`/`_lag2` (≤ T-1)
  jointe depuis #03 ; la **sévérité courante T (cible) est retirée** des features (anti-fuite
  cible). Anti-fuite T+1 vérifié par test explicite.
- **Lags spatiaux supprimés** (`compute_spatial_lags`/`build_neighbor_dict` + dépendance
  shapefile `region_naturelle`) : topologie région sans équivalent à la maille cellule, hors
  scope #04. À rouvrir si un voisinage cellule devient nécessaire.
- **`soil_moisture_mean`** retiré de `LAG_FEATURES` : absent de la sortie GEE #04 réelle.
- Tests : `tests/test_05_feature_engineering.py` (17 unitaires verts + 3 intégration gardés
  par skip tant que `05_features_engineering.parquet` est absent).

## Blocked by

- `.scratch/severite-phase-forecast/issues/02-cible-ordinale-severite-phase.md`
- `.scratch/severite-phase-forecast/issues/03-extraction-gee-decadaire-1km.md`
