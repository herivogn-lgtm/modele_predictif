# Architecture du système — Chaîne de pipelines (OS3 sévérité-phase)

## Vue d'ensemble

Le système (volet technique **OS3** de la thèse N. RANDRIANARIJAONA) transforme deux sources brutes — les relevés acridiens terrain (`data/2001_2026_Acrido_vf.xls`, 2001–2026) et les variables environnementales satellitaires (Google Earth Engine) — en une **carte de sévérité-phase ordinale 0–3** à la maille **cellule 1 km × décade** pour la **décade T+1**, restituée en carte décadaire (alerte précoce) et agrégée au mois (planification), avec un **binaire présence/absence dérivé** pour la validation AUC exigée par la thèse (§31/§33).

| Sortie | Destinataire | Forme | Contenu |
|--------|-------------|-------|---------|
| **Carte décadaire** | Prospecteur IFVM | PNG + GeoJSON + GeoTIFF | Sévérité 0–3 à 1 km, décade T+1 |
| **Agrégat mensuel** | Responsable lutte | CSV par `AIRE_CODE` | Sévérité max + comptage foyers (sév ≥ 2) |
| **Rapport analytique** | Chercheurs / revue HITL | CSV + résumé | QWK, rappel 2–3, AUC binaire, calibration, gain/lift |

Périmètre exclusivement *Locusta migratoria capito* (LMC). Décisions structurantes : ADR [0001](adr/0001-cible-ordinale-severite-phase.md) (cible ordinale), [0002](adr/0002-forecast-decade-t-plus-1.md) (forecast T+1), [0003](adr/0003-emprise-aire-gregarigene-clip-strict.md) (emprise clip 1 km), [0004](adr/0004-fenetre-entrainement-complete.md) (fenêtre 2001–2026), [0005](adr/0005-benchmark-modeles-selection-robustesse.md) (benchmark + suppression NeuralProphet).

---

## Flux de données

```
SOURCE BRUTE
  data/2001_2026_Acrido_vf.xls         (relevés terrain)
  data/aire_gregarigene/  (12 polygones secteurs, AIRE_CODE 1–4)
       │
       ▼
  #01 nettoyage_jointure_01.py    snap point→cellule 1 km + clip strict
       │  → 01_releves_nettoyes.parquet
       │  → 01_grille_1km.parquet  (grille partagée entraînement = prédiction)
       ▼
  #02 gregarite_potentiel_02.py
       │  → 02_gregarite_potentiel.parquet
       ▼
  #03 labels_entrainement_03.py   cible ordinale sévérité 0–3 (cellule × décade)
       │  → 03_labels_cellule_decade.parquet ──────────────┐
       │                                                   │
SOURCE GEE  (CHIRPS, MODIS NDVI/EVI/LST)                   │
       ▼                                                   │
  #04 04_extraction_variables_gee.py / 04b (Export.table)  │
       │  → 04_variables_environnementales/  (cellule 1 km)│
       ▼                                                   │
  #05 feature_engineering_05.py   POP + lags + anti-fuite T+1
       │  → 05_features_engineering.parquet                │
       ▼◄──────────────────────────────────────────────────┘
  #06 table_entrainement_06.py    features ⟕ labels (LEFT) + surface a_predire
       │  → 06_table_entrainement_unifiee.parquet
       ▼
  #07 benchmark_ordinal_07.py     benchmark ordinal + select_robust (walk-forward)
       │  → 07_benchmark_par_campagne.csv / 07_benchmark_resume.csv
       │  → 07_modele_retenu.txt ───────────────┬───────────────┐
       ▼                                        ▼               ▼
  #10 rapport_performance_08.py            #09 sorties_operationnelles_09.py
       │  QWK / rappel 2–3 / AUC /          │  (après validation HITL du rapport #10)
       │  calibration / gain-lift          │  → 09_carte_severite_decade.csv
       │  → 08_rapport_par_campagne.csv     │  → 09_carte_severite_mensuelle.csv
       │  → 08_calibration.csv              │  → 09_agregat_aire_mensuel.csv
       │  → 08_gain_lift.csv                │  → 09_carte_severite.{geojson,tif,png}
       │  → 08_rapport_resume.txt           │
       └──────────► REVUE HUMAINE (HITL) ───┘
```

### Tableau de dépendances

| Pipeline | Script | Consomme | Produit | Aval |
|----------|--------|----------|---------|------|
| #01 | `nettoyage_jointure_01.py` | XLS + `aire_gregarigene` | `01_releves_nettoyes.parquet`, `01_grille_1km.parquet` | #02, #04, #09 |
| #02 | `gregarite_potentiel_02.py` | #01 | `02_gregarite_potentiel.parquet` | #03 |
| #03 | `labels_entrainement_03.py` | #02 | `03_labels_cellule_decade.parquet` | #05, #06 |
| #04 | `04_extraction_variables_gee.py` / `04b_export_variables_gee.py` | `01_grille_1km` + GEE | `04_variables_environnementales/` | #05 |
| #05 | `feature_engineering_05.py` | #04, #03 | `05_features_engineering.parquet` | #06 |
| #06 | `table_entrainement_06.py` | #05, #03 | `06_table_entrainement_unifiee.parquet` | #07, #09, #10 |
| #07 | `benchmark_ordinal_07.py` | #06 | `07_benchmark_*.csv`, `07_modele_retenu.txt` | #09, #10 |
| #09 | `sorties_operationnelles_09.py` | #06, #07, `01_grille_1km` | cartes CSV + GeoJSON + GeoTIFF + PNG | terrain (HITL) |
| #10 | `rapport_performance_08.py` | #06, #07 | `08_rapport_*.csv`, `08_calibration.csv`, `08_gain_lift.csv` | revue humaine |

> Numérotation : le PRD nomme le rapport **Pipeline 10** ; son script garde le suffixe `_08` (numéro d'issue). Le **Pipeline 11 (NeuralProphet) est supprimé** ([ADR 0005](adr/0005-benchmark-modeles-selection-robustesse.md)). Les anciens modules `lgbm_baseline_07.py` / `lgbm_hierarchique_08.py` (pivot risque 0–4 / Annexe 8) sont **abandonnés** et remplacés par le benchmark #07.

---

## Unité spatio-temporelle

| Concept | Valeurs | Description |
|---------|---------|-------------|
| **Maille spatiale** | grille régulière **1 km** | Cellules `cell_id` clipées à l'aire grégarigène (EPSG:32738), ~181 000 cellules |
| **Aire complémentaire** | `AIRE_CODE` 1–4 | AMI / ATM / AD / AGT — prédicteur catégoriel + unité d'agrégation opérationnelle |
| **Campagne acridienne** | `"YYYY-YYYY+1"` | Période saisonnière chevauchant deux années civiles |
| **Décade de campagne** | `campagne_decade` 1–36 | Position dans la campagne ; restitution agrégée au mois (3 décades) |

La cible est la **sévérité-phase ordinale** : `0` absence · `1` solitaire · `2` transiens · `3` grégaire = **phase maximale** observée dans la cellule × décade. Le **binaire dérivé** (sév ≥ 1) est conservé pour l'AUC.

---

## Décisions architecturales

- **Cible ordinale 0–3** ([ADR 0001](adr/0001-cible-ordinale-severite-phase.md)) — remplace le binaire présence/absence et l'échelle 0–6 Annexe 8 (abandonnée).
- **Forecast décade T+1** ([ADR 0002](adr/0002-forecast-decade-t-plus-1.md)) — anti-fuite : aucune feature de T+1.
- **Emprise 1 km clip strict** ([ADR 0003](adr/0003-emprise-aire-gregarigene-clip-strict.md)) — entraînement = prédiction ; relevés hors polygones écartés.
- **Fenêtre 2001–2026 complète** ([ADR 0004](adr/0004-fenetre-entrainement-complete.md)) — lacune 2023-2024 gérée (GEE continu, campagne sautée en validation).
- **Benchmark + robustesse** ([ADR 0005](adr/0005-benchmark-modeles-selection-robustesse.md)) — régression ordinale, RF, XGBoost, LightGBM, CatBoost, LSTM ; sélection sur rappel 2–3 sous contrainte QWK ≥ baseline, départage variance inter-folds puis simplicité. NeuralProphet supprimé.

**Parcimonie spatiale** : ~1,5 % des cellules-décades sont observées → le modèle généralise via les covariables environnementales (POP, NDVI/EVI, LST, CHIRPS). Les cellules non prospectées sont la **surface de prédiction** (`a_predire`), distincte des **vraies absences** (`severite = 0`).

---

## Fiches pipelines

[#01](pipelines/01-nettoyage-jointure.md) ·
[#02](pipelines/02-gregarite-potentiel.md) ·
[#03](pipelines/03-labels-entrainement.md) ·
[#04](pipelines/04-extraction-gee.md) ·
[#05](pipelines/05-feature-engineering.md) ·
[#06](pipelines/06-table-entrainement.md) ·
[#07](pipelines/07-benchmark-ordinal.md) ·
[#09](pipelines/09-sorties-operationnelles.md) ·
[#10](pipelines/10-rapport-performance.md)

Runbook GEE : [runbook-04-extraction-gee.md](runbook-04-extraction-gee.md).
