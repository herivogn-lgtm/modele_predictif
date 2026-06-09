# Pipeline #06 — Table d'entraînement unifiée (cellule 1 km × décade)

**Script** : `src/table_entrainement_06.py`
**Entrées** : `data/processed/05_features_engineering.parquet`, `data/processed/03_labels_cellule_decade.parquet`
**Sortie** : `data/processed/06_table_entrainement_unifiee.parquet`
**Durée estimée** : < 2 minutes
**Dépendances obligatoires** : Pipelines [#05](05-feature-engineering.md), [#03](03-labels-entrainement.md)

---

## Objectif

Assembler la table unique que consomment les pipelines modèles ([#07](07-benchmark-ordinal.md), [#10](10-rapport-performance.md)) et la restitution ([#09](09-sorties-operationnelles.md)).

- Les **features** (#05) forment l'épine dorsale : **toute la grille 1 km × décades**, covariables environnementales, POP, lags et `AIRE_CODE`.
- Les **labels** (#03) — `severite` 0–3, `binaire` dérivé, `intensite` optionnelle — sont joints en **LEFT** sur `cell_id × campagne_calc × campagne_decade`.

Les cellules **non prospectées** restent présentes avec leurs covariables mais sans label (`severite = NA`, `a_predire = True`) : c'est la **surface de prédiction**, distincte des **vraies absences** (`severite = 0`, relevé à zéro). Le découpage walk-forward (train/validation) relève du seam `walk_forward_split`, pas de ce pipeline.

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/05_features_engineering.parquet` | `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, toutes les features |
| `data/processed/03_labels_cellule_decade.parquet` | `cell_id`, `campagne_calc`, `campagne_decade`, `severite`, `binaire`, `intensite`, `effort_prospection` |

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `data/processed/06_table_entrainement_unifiee.parquet` | ~4,2 M lignes cellule × décade ; features + `severite` (0–3 / NA) + `binaire` + `intensite` + `effort_prospection` + `a_predire` |

Colonnes notables : `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, `chirps_sum_mean`, `ndvi_mean`, `evi_mean`, `lst_mean`, `chirps_anomaly_mean`, `pop_consecutive`, lags (`*_lag1d/_lag2d`, `chirps_cumul_2d/_3d`, `severite_lag1/_lag2`), `severite`, `intensite`, `effort_prospection`, `binaire`, `a_predire`.

---

## Fonctions pures (testées — `tests/test_06_table_entrainement_unifiee.py`)

| Fonction | Rôle |
|----------|------|
| `assemble_table(features, labels)` | Jointure LEFT features←labels, colonnes attendues, marquage `a_predire` |

---

## Lancement

```bash
./.venv/bin/python src/table_entrainement_06.py
```

## Aval

Entrée unique des pipelines [#07](07-benchmark-ordinal.md) (benchmark), [#10](10-rapport-performance.md) (rapport) et [#09](09-sorties-operationnelles.md) (cartes).
