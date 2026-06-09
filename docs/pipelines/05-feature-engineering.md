# Pipeline #05 — Feature engineering (cellule 1 km × décade)

**Script** : `src/feature_engineering_05.py`
**Entrées** : `data/processed/04_variables_environnementales/` + `data/processed/03_labels_cellule_decade.parquet`
**Sortie** : `data/processed/05_features_engineering.parquet`
**Durée estimée** : 5–15 minutes
**Dépendances obligatoires** : Pipelines [#04](04-extraction-gee.md), [#03](03-labels-entrainement.md)

---

## Objectif

Enrichir les variables environnementales GEE (maille cellule 1 km × décade) avec les features prédictives du modèle, **sans aucune fuite temporelle** : aucune feature n'utilise une covariable de la décade T+1.

- **POP** (`pop_consecutive`) : nombre de mois consécutifs en **Plage d'Optimum Pluviométrique** (CHIRPS 50–125 mm/mois), réinitialisé par campagne et par cellule — le précurseur de grégarisation le mieux documenté.
- **Lags temporels** (`*_lag1d`, `*_lag2d`) : décalages décadaires D-1 / D-2 par cellule (NDVI, EVI, LST, CHIRPS).
- **Cumuls de pluie** (`chirps_cumul_2d`, `chirps_cumul_3d`) : pluie roulante sur 2–3 décades (≤ T).
- **Sévérité historique** (`severite_lag1`, `severite_lag2`) : sévérité passée de la cellule (#03), strictement ≤ T-1.
- **`AIRE_CODE`** : prédicteur catégoriel (codes 1–4) conservé tel quel ([ADR 0001](../adr/0001-cible-ordinale-severite-phase.md)).

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/04_variables_environnementales/` (dataset Parquet partitionné) | `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, `chirps_sum_mean`, `ndvi_mean`, `evi_mean`, `lst_mean`, `chirps_anomaly_mean` |
| `data/processed/03_labels_cellule_decade.parquet` | `cell_id`, `campagne_calc`, `campagne_decade`, `severite` — pour les lags de sévérité |

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `data/processed/05_features_engineering.parquet` | Une ligne par cellule × décade : covariables GEE + POP + lags + cumuls + `severite_lag*` + `AIRE_CODE` |

---

## Fonctions pures (testées — `tests/test_05_feature_engineering.py`)

| Fonction | Rôle |
|----------|------|
| `consecutive_counter(series)` | Compteur de séquences consécutives (support du calcul POP) |
| `compute_pop(df)` | Bande 50–125 mm/mois + persistance multi-mois par cellule |
| `build_lags(df, labels=None)` | Lags décadaires + cumuls de pluie + sévérité historique, **anti-fuite T+1** |

---

## Lancement

```bash
./.venv/bin/python src/feature_engineering_05.py
```

## Aval

Pipeline [#06](06-table-entrainement.md) : jointure features + labels → table d'entraînement unifiée.
