# Architecture du système de modélisation — Chaîne des 11 pipelines

## Vue d'ensemble

Le système transforme deux sources de données brutes — les relevés acridiens terrain (`data/2001_2026_Acrido_vf.xls`, 29 706 lignes, 2001–2026) et les variables environnementales satellitaires (Google Earth Engine) — en cartes de niveau de risque acridien 0–4 par acrido-région, à trois horizons temporels : décadaire (10 jours), mensuel et saisonnier.

Conformément à l'[ADR-0001](adr/0001-architecture-double-sortie.md), le système produit deux natures de sorties en parallèle :

| Nature | Destinataire | Forme | Contenu |
|--------|-------------|-------|---------|
| **Opérationnelle** | CNA terrain, logistique | CSV + GeoJSON par secteur | Niveau de risque 0–4, 3 horizons |
| **Analytique** | Chercheurs, publication | Rapports walk-forward, courbes | Présence/absence (AUC), densité (RMSE), phase (F1-macro) |

Toute l'architecture est contrainte à tourner sur **CPU standard sans GPU** ([ADR-0002](adr/0002-contrainte-cpu-uniquement.md)). Le périmètre est exclusivement *Locusta migratoria capito* (LMC) — les colonnes `_NSE` (*Nomadacris septemfasciata*) sont ignorées dès le pipeline #01.

---

## Flux de données — les 11 pipelines

```
SOURCE BRUTE
  data/2001_2026_Acrido_vf.xls (29 706 relevés terrain)
  data/region_naturelle/      (90 polygones)
  data/aire_gregarigene/      (12 polygones / secteurs)
       │
       ▼
  #01 nettoyage_jointure_01.py
       │  → data/processed/01_releves_nettoyes.parquet
       ▼
  #02 gregarite_potentiel_02.py
       │  → data/processed/02_gregarite_potentiel.parquet
       ├──────────────────────────────────────┐
       ▼                                      │
  #03 labels_entrainement_03.py               │
       │  → data/processed/03_labels_region_decade.parquet
       │                                      │
SOURCE GEE                                    │
  Google Earth Engine (CHIRPS, MODIS…)        │
       │                                      │
       ▼                                      │
  #04 04_extraction_variables_gee.py          │
       │  → data/processed/04_variables_environnementales.parquet
       ▼                                      │
  #05 feature_engineering_05.py               │
       │  → data/processed/05_features_engineering.parquet
       │                                      │
       ▼◄─────────────────────────────────────┘
  #06 table_entrainement_06.py
       │  → data/processed/06_table_entrainement_unifiee.parquet
       │
       ├────────────────────────────────────────────────────────┐
       │ Chemin LightGBM (opérationnel)                        │ Chemin NeuralProphet
       ▼                                                        │ (expérimental)
  #07 lgbm_baseline_07.py                                      ▼
       │  → data/processed/07_lgbm_model.pkl              #11 neuralprophet_11.py
       │  → data/processed/07_rapport_walk_forward.csv         │  → 11_rapport_walk_forward.csv
       │  → data/processed/07_feature_importances.csv          │  → 11_neuralprophet_model.pkl
       ▼                                                        │  → 11_decision_deploiement.csv
  #08 lgbm_hierarchique_08.py
       │  → data/processed/08_lgbm_densite.pkl
       │  → data/processed/08_lgbm_phase.pkl
       │  → data/processed/08_rapport_walk_forward.csv
       ▼
  #09 sorties_operationnelles_09.py
       │  → data/processed/09_rn_risque_decade.parquet
       │  → data/processed/09_sorties_decadaire.{csv,geojson}
       │  → data/processed/09_sorties_mensuelle.{csv,geojson}
       │  → data/processed/09_sorties_saisonniere.{csv,geojson}
       ▼
  #10 notebooks/10_rapport_performance.ipynb
          → data/processed/10_courbe_performance.png
```

### Tableau de dépendances

| Pipeline | Script | Fichier(s) consommé(s) | Fichier(s) produit(s) | Consommateur(s) aval |
|----------|--------|------------------------|----------------------|----------------------|
| #01 | `src/nettoyage_jointure_01.py` | XLS brut + shapefiles | `01_releves_nettoyes.parquet` | #02, #03 |
| #02 | `src/gregarite_potentiel_02.py` | Sortie #01 | `02_gregarite_potentiel.parquet` | #03, #06, #08 |
| #03 | `src/labels_entrainement_03.py` | Sortie #02 + shapefile régions | `03_labels_region_decade.parquet` | #06 |
| #04 | `src/04_extraction_variables_gee.py` | GEE + shapefile régions | `04_variables_environnementales.parquet` | #05 |
| #05 | `src/feature_engineering_05.py` | Sortie #04 + shapefile régions | `05_features_engineering.parquet` | #06 |
| #06 | `src/table_entrainement_06.py` | Sorties #02, #03, #05 | `06_table_entrainement_unifiee.parquet` | #07, #08, #09, #11 |
| #07 | `src/lgbm_baseline_07.py` | Sortie #06 | `07_lgbm_model.pkl`, `07_rapport_walk_forward.csv`, `07_feature_importances.csv` | #09, #10, #11 |
| #08 | `src/lgbm_hierarchique_08.py` | Sorties #06, #02, `07_lgbm_model.pkl` | `08_lgbm_densite.pkl`, `08_lgbm_phase.pkl`, `08_rapport_walk_forward.csv` | #09, #10 |
| #09 | `src/sorties_operationnelles_09.py` | Sorties #06, #07, #08 + shapefiles | `09_rn_risque_decade.parquet`, 6 fichiers CSV/GeoJSON | #10 |
| #10 | `notebooks/10_rapport_performance.ipynb` | Sorties #06, #07, #08, #09 | `10_courbe_performance.png` | — |
| #11 | `src/neuralprophet_11.py` | Sorties #06, `07_rapport_walk_forward.csv` | `11_rapport_walk_forward.csv`, `11_neuralprophet_model.pkl`, `11_decision_deploiement.csv` | — |

---

## Les deux chemins parallèles depuis le pipeline #06

À partir du pipeline #06, le système bifurque en deux chemins indépendants partageant la même table d'entrée.

**Chemin LightGBM (opérationnel)** — #07 → #08 → #09 :
- Modèle hiérarchique en trois étapes : présence/absence → densité → phase acridienne
- Sorties opérationnelles 0–4 par acrido-région
- Ce chemin est le chemin de production recommandé

**Chemin NeuralProphet (expérimental)** — #11 :
- Modèle de séries temporelles multi-horizon (décadaire / mensuel / saisonnier)
- Son déploiement est **conditionnel** : consulter `data/processed/11_decision_deploiement.csv`
- Critère de déploiement : AUC décadaire NeuralProphet > AUC LightGBM (#07) ET temps d'entraînement < 30 min
- Si le critère n'est pas atteint : maintenir le chemin LightGBM

---

## Unités spatio-temporelles

### Deux unités spatiales

| Unité | Shapefile | Nombre | Usage |
|-------|-----------|--------|-------|
| **Région naturelle** | `data/region_naturelle/` | 90 polygones | Unité de modélisation ML |
| **Acrido-région / Secteur** | `data/aire_gregarigene/` | 12 polygones | Unité de sortie opérationnelle CNA |

Les 90 régions naturelles sont agrégées vers les 12 secteurs dans le pipeline #09 (jointure spatiale, projection UTM 38S).

### Structure temporelle

| Concept | Valeurs | Description |
|---------|---------|-------------|
| **Campagne acridienne** | `"YYYY-YYYY+1"` (ex. `"2001-2002"`) | Période d'octobre à juillet, chevauchant deux années civiles |
| **Mois de campagne** | 1 à 10 | Octobre = mois 1, juillet = mois 10 |
| **Décade intra-mois** | 1 à 3 | D1 = jours 1–10, D2 = jours 11–20, D3 = jours 21–fin |
| **Décade de campagne** (`campagne_decade`) | 1 à 30 | Position dans la campagne ; octobre-D1 = 1, juillet-D3 = 30 |

Les mois d'août et septembre ne font partie d'aucune campagne acridienne — les relevés de ces mois sont conservés dans le fichier mais reçoivent `campagne_calc = None` et ne participent pas à l'entraînement.

---

## Prérequis d'exécution par pipeline

| Pipeline | Prérequis spéciaux | Durée estimée |
|----------|--------------------|---------------|
| #01 | Fichier XLS brut + shapefiles présents dans `data/` | < 5 min |
| #02 | Sortie #01 | < 2 min |
| #03 | Sortie #02 + shapefile `region_naturelle` | < 2 min |
| #04 | **Compte GEE authentifié** + `GEE_PROJECT_ID` renseigné dans `src/config_gee.py` | 2–3 h (run complet 2001–2026) |
| #05 | Sortie #04 + shapefile `region_naturelle` | 5–15 min |
| #06 | Sorties #02, #03, #05 | < 2 min |
| #07 | Sortie #06 | 5–15 min |
| #08 | Sorties #06, #02 + `07_lgbm_model.pkl` | 5–15 min |
| #09 | Sorties #06, #07, #08 (modèles pkl + rapports CSV) + shapefiles | < 5 min |
| #10 | Sorties #07, #08, #09, #06 | Interactif (notebook Jupyter) |
| #11 | Sortie #06 + `07_rapport_walk_forward.csv` | Variable (CPU) — peut dépasser 30 min |

> Le pipeline #04 est le seul à nécessiter une connexion internet active et un compte Google Earth Engine. Voir la fiche [04-extraction-gee.md](pipelines/04-extraction-gee.md) et le runbook [runbook-04-extraction-gee.md](runbook-04-extraction-gee.md).

---

## Contraintes architecturales

**CPU uniquement** ([ADR-0002](adr/0002-contrainte-cpu-uniquement.md)) : Tous les modèles (LightGBM, NeuralProphet) sont configurés pour tourner sur CPU standard sans GPU. Les architectures nécessitant un GPU (ConvLSTM, GAT-LSTM, Temporal Fusion Transformer) ont été explicitement écartées.

**Double sortie** ([ADR-0001](adr/0001-architecture-double-sortie.md)) : Les sorties opérationnelles (0–4) et les métriques analytiques (AUC, RMSE, F1-macro) poursuivent des objectifs incompatibles et sont produites en parallèle dans des fichiers distincts.

**Périmètre LMC** : Le fichier XLS contient des données sur deux espèces. Toutes les colonnes relatives à *Nomadacris septemfasciata* (suffixe `_NSE`) sont supprimées dès le pipeline #01 et n'apparaissent dans aucun fichier intermédiaire ni final.
