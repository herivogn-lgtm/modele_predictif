# Pipeline #07 — LightGBM baseline présence/absence

**Script** : `src/lgbm_baseline_07.py`  
**Entrée** : `data/processed/06_table_entrainement_unifiee.parquet`  
**Sorties** : `07_lgbm_model.pkl`, `07_rapport_walk_forward.csv`, `07_feature_importances.csv`  
**Durée estimée** : 5–15 minutes  
**Dépendance obligatoire** : Pipeline [#06](06-table-entrainement.md)

---

## Objectif

Entraîner un classifieur binaire LightGBM pour prédire la présence ou l'absence de criquets migrateurs dans chaque cellule régionale × décade. La performance est évaluée par validation walk-forward expanding-window sur 8 folds (campagnes 2016-17 à 2021-22). Le pipeline exporte le modèle final et un rapport de performance détaillé.

---

## Entrées

| Fichier | Colonnes utilisées |
|---------|--------------------|
| `data/processed/06_table_entrainement_unifiee.parquet` | Toutes les features + `label` (0/1/NA) + `split` + `effort_prospection` |

Seules les lignes avec `split ∈ {train, validation}` (label non-NA) participent à la validation. Toutes les lignes labellisées sont utilisées pour le modèle final.

---

## Sorties

| Fichier | Description | Colonnes / contenu |
|---------|-------------|-------------------|
| `data/processed/07_lgbm_model.pkl` | Modèle LightGBM final (joblib) | `LGBMClassifier` entraîné sur train + validation |
| `data/processed/07_rapport_walk_forward.csv` | Métriques par fold + ligne GLOBAL | `campagne_calc`, `n_positifs`, `n_negatifs`, `auc_roc`, `precision`, `recall`, `f1`, `threshold` |
| `data/processed/07_feature_importances.csv` | Importance des features par gain (moyenne sur 8 folds) | `feature`, `importance_mean`, `importance_std` |

---

## Règles métier

### RM-1 : Correction du déséquilibre de classes

Le jeu de données acridien est naturellement déséquilibré (les absences vérifiées sont plus nombreuses que les présences). Correction par `scale_pos_weight = n_négatifs / n_positifs`, calculé dynamiquement sur le set d'entraînement de chaque fold.

### RM-2 : Hyperparamètres LightGBM

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| `objective` | `"binary"` | Classification binaire |
| `metric` | `"auc"` | Optimisation en entraînement |
| `learning_rate` | 0,05 | Convergence stable |
| `num_leaves` | 31 | Complexité modérée |
| `n_estimators` | 300 | Avec early stopping |
| `random_state` | 42 | Reproductibilité |

L'early stopping est appliqué sur 20 % du set d'entraînement (validation interne) avec une patience de 30 arbres.

### RM-3 : Optimisation du seuil de décision

Pour chaque fold, le seuil de classification optimal est cherché dans `[0.05, 0.50]` par pas de 0,01 pour **maximiser le F1 binaire** sur le set de validation. Le seuil optimal est stocké dans la colonne `threshold` de `07_rapport_walk_forward.csv`.

Le seuil de la **ligne GLOBAL** (métriques poolées sur tous les folds) est le seuil utilisé par le pipeline [#09](09-sorties-operationnelles.md) pour les prédictions de production.

### RM-4 : Walk-forward expanding-window

8 folds, fenêtre d'entraînement croissante :

| Fold | Entraînement | Validation |
|------|-------------|------------|
| 1 | 2001-02 à 2015-16 | 2016-17 |
| 2 | 2001-02 à 2016-17 | 2017-18 |
| 3 | 2001-02 à 2017-18 | 2018-19 |
| 4 | 2001-02 à 2018-19 | 2019-20 |
| 5 | 2001-02 à 2019-20 | 2020-21 |
| 6 | 2001-02 à 2020-21 | 2021-22 |
| 7 | 2001-02 à 2021-22 | 2022-23 |
| 8 | 2001-02 à 2022-23 | dernière campagne labellisée disponible |

La ligne `GLOBAL` du rapport correspond aux métriques calculées en poolant toutes les prédictions de validation de tous les folds.

### RM-5 : Modèle final

Le modèle exporté dans `07_lgbm_model.pkl` est entraîné sur **toutes** les données labellisées (`split ∈ {train, validation}`), sans held-out. C'est ce modèle qui est déployé en production via [#09](09-sorties-operationnelles.md).

### RM-6 : Cible de performance

`auc_roc (GLOBAL) ≥ 0,85` — affiché en fin d'exécution avec le statut `[OK >= 0.85]` ou `[!! < 0.85 — cible non atteinte]`.

---

## Exécution

```bash
python src/lgbm_baseline_07.py
```

---

## Dépendances

- **Amont** : [#06](06-table-entrainement.md) — `06_table_entrainement_unifiee.parquet`
- **Aval** :
  - [#08](08-lgbm-hierarchique.md) — charge `07_lgbm_model.pkl` pour la chaîne d'inférence
  - [#09](09-sorties-operationnelles.md) — utilise `07_lgbm_model.pkl` et le seuil de `07_rapport_walk_forward.csv` (ligne GLOBAL)
  - [#10](10-rapport-performance.md) — charge `07_rapport_walk_forward.csv` et `07_feature_importances.csv`
  - [#11](11-neuralprophet.md) — charge `07_rapport_walk_forward.csv` pour la table de décision de déploiement
- **Bibliothèques** : `lightgbm`, `pandas`, `scikit-learn`, `joblib`, `numpy`, `pyarrow`

---

## Avertissements

La colonne `niveau_gregarite_dominant` est encodée en `pd.Categorical` avec les catégories `["absent", "S", "St", "T", "G"]` avant d'être passée à LightGBM. Si cette colonne est absente de #06 (cas de dégradation gracieuse), LightGBM la reçoit comme NaN et continue sans erreur — mais l'importance de cette feature sera nulle.

Les importances de features sont des moyennes sur les 8 folds — elles représentent le gain moyen sur l'ensemble de la validation et non le gain d'un modèle unique.
