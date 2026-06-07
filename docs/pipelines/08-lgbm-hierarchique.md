# Pipeline #08 — Modèle hiérarchique densité + phase acridienne

**Script** : `src/lgbm_hierarchique_08.py`  
**Entrées** : Sorties de #06, #02 et `07_lgbm_model.pkl`  
**Sorties** : `08_lgbm_densite.pkl`, `08_lgbm_phase.pkl`, `08_rapport_walk_forward.csv`  
**Durée estimée** : 5–15 minutes  
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#02](02-gregarite-potentiel.md), [#07](07-lgbm-baseline.md)

---

## Objectif

Ajouter deux étapes conditionnelles à la chaîne de prédiction : (1) régression LightGBM de la densité d'imagos (ind/ha) sur les cellules où la présence a été confirmée, (2) classification LightGBM de la phase acridienne (S / St / T / G) sur ces mêmes cellules, avec correction du déséquilibre sévère de la classe grégaire (G ≈ 5,8 % des présences). Ces deux modèles complètent le modèle de présence/absence (#07) pour former l'architecture hiérarchique complète.

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/06_table_entrainement_unifiee.parquet` | Toutes les features + `label` + `split` |
| `data/processed/02_gregarite_potentiel.parquet` | `rn_num`, `campagne_calc`, `campagne_decade`, `densite_imago`, `niveau_gregarite` — pour les cibles des deux modèles |
| `data/processed/07_lgbm_model.pkl` | Chargé pour la chaîne d'inférence en [#09](09-sorties-operationnelles.md) |

---

## Sorties

| Fichier | Description | Contenu |
|---------|-------------|---------|
| `data/processed/08_lgbm_densite.pkl` | Modèle régression densité (joblib) | `LGBMRegressor` entraîné sur les cellules avec présence |
| `data/processed/08_lgbm_phase.pkl` | Modèle classification phase (joblib) | `LGBMClassifier` multiclasse (S/St/T/G) |
| `data/processed/08_rapport_walk_forward.csv` | Métriques par fold + ligne GLOBAL | `campagne_calc`, `n_presence`, `rmse_densite`, `mae_densite`, `f1_macro_phase`, `recall_G`, `threshold_G` |

---

## Règles métier

### RM-1 : Filtre de présence — condition obligatoire

Les modèles densité et phase sont entraînés et évalués **exclusivement sur les cellules avec `label = 1`** (présence confirmée). Une prédiction d'absence par le modèle #07 court-circuite entièrement ces étapes : `densite_pred = NaN` et `phase_pred = None`.

Ce filtrage est appliqué à chaque fold walk-forward et au modèle final.

### RM-2 : Cible densité — agrégation par médiane

La cible du modèle de régression est `densite_imago_median` : médiane de la colonne `densite_imago` (calculée en [#02](02-gregarite-potentiel.md)) sur l'ensemble des relevés de la cellule (rn_num × campagne × décade). Cette agrégation est distincte de `potentiel_acridien_dominant` (mode) de [#06](06-table-entrainement.md).

### RM-3 : Correction du déséquilibre de classe G

La classe grégaire (G) représente environ 5,8 % des observations avec présence — déséquilibre sévère. Deux mécanismes correcteurs sont combinés :

1. **`class_weight="balanced"`** dans `LGBMClassifier` : LightGBM pondère chaque classe inversement à sa fréquence dans le set d'entraînement
2. **Seuil abaissé sur P(G)** : pour chaque fold, un seuil `threshold_G` est cherché dans `[0.05, 0.50]` pour maximiser le rappel sur la classe G, sous contrainte `F1-macro ≥ 0,30`. La décision finale est :
   ```
   si P(G) ≥ threshold_G → phase_pred = "G"
   sinon → phase_pred = argmax(P(S), P(St), P(T))
   ```

La fonction `_apply_threshold_G(probas, threshold_G)` qui implémente cette logique est réutilisée à l'identique dans [#09](09-sorties-operationnelles.md).

### RM-4 : Cible de performance — rappel G

`recall_G (GLOBAL) ≥ 0,70` — affiché en fin d'exécution. La cible 0,70 signifie que le modèle doit détecter au moins 70 % des occurrences de phase grégaire dans les données de validation. C'est la métrique opérationnelle critique : manquer un foyer grégaire est plus grave qu'une fausse alarme.

### RM-5 : Skip automatique des folds insuffisants

Si le fold de validation contient **moins de 2 lignes avec présence**, ou si le set d'entraînement contient **moins de 10 lignes avec présence**, le fold est sauté avec un message de log `[SKIP densité]` ou `[SKIP phase]`. Les métriques de ce fold sont enregistrées comme `NaN` dans le rapport.

### RM-6 : Walk-forward identique à #07

Les 8 folds utilisent exactement la même partition temporelle qu'en [#07](07-lgbm-baseline.md). La fonction `walk_forward_folds()` est importée depuis `lgbm_baseline_07.py`.

---

## Exécution

```bash
python src/lgbm_hierarchique_08.py
```

---

## Dépendances

- **Amont** :
  - [#06](06-table-entrainement.md) — `06_table_entrainement_unifiee.parquet`
  - [#02](02-gregarite-potentiel.md) — `02_gregarite_potentiel.parquet` (cibles densité et phase)
  - [#07](07-lgbm-baseline.md) — `07_lgbm_model.pkl` (utilisé pour la chaîne d'inférence en #09)
- **Aval** :
  - [#09](09-sorties-operationnelles.md) — charge les deux pkl et le rapport (seuil G ligne GLOBAL)
  - [#10](10-rapport-performance.md) — charge `08_rapport_walk_forward.csv`
- **Bibliothèques** : `lightgbm`, `pandas`, `scikit-learn`, `joblib`, `numpy`, `pyarrow`

---

## Avertissements

Le seuil G abaissé (`threshold_G`) de la ligne GLOBAL du rapport est le seuil déployé en production via [#09](09-sorties-operationnelles.md). Ce seuil peut varier d'un run à l'autre si les données d'entraînement évoluent — toujours vérifier que `recall_G (GLOBAL) ≥ 0,70` après un run sur de nouvelles données.

La classe G encode les conditions de déclenchement de la lutte curative (densités supérieures au seuil de grégarisation de ~1 500–2 500 imagos/ha). Un faux négatif sur G (détection manquée) est opérationnellement plus coûteux qu'un faux positif — d'où la tolérance à un rappel G > précision G.
