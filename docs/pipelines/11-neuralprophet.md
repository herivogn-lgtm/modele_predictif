# Pipeline #11 — NeuralProphet multi-horizon

**Script** : `src/neuralprophet_11.py`  
**Entrées** : `data/processed/06_table_entrainement_unifiee.parquet` + `07_rapport_walk_forward.csv`  
**Sorties** : `11_rapport_walk_forward.csv`, `11_neuralprophet_model.pkl`, `11_decision_deploiement.csv`  
**Durée estimée** : variable selon le matériel (peut dépasser 30 minutes sur CPU standard)  
**Dépendances obligatoires** : Pipelines [#06](06-table-entrainement.md), [#07](07-lgbm-baseline.md)

> Ce pipeline est **expérimental**. Consulter `data/processed/11_decision_deploiement.csv` avant d'utiliser ses prédictions en production.

---

## Objectif

Entraîner un modèle NeuralProphet en mode panel sur les 90 séries temporelles de régions naturelles, produire des prédictions à trois horizons simultanément (décadaire, mensuel, saisonnier), comparer les performances avec le baseline LightGBM [#07](07-lgbm-baseline.md), et produire une décision automatique de déploiement. Ce pipeline explore la valeur ajoutée des modèles de séries temporelles par rapport au modèle tabulaire LightGBM.

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/06_table_entrainement_unifiee.parquet` | `rn_num`, `campagne_calc`, `campagne_decade`, `label`, `split` |
| `data/processed/07_rapport_walk_forward.csv` | `auc_roc` ligne GLOBAL — pour la table de décision |

---

## Sorties

| Fichier | Description | Colonnes |
|---------|-------------|---------|
| `data/processed/11_rapport_walk_forward.csv` | Métriques par fold × horizon + ligne GLOBAL | `campagne_calc`, `n_positifs`, `n_negatifs`, puis pour chaque horizon `{decadaire, mensuel, saisonnier}` : `auc_roc_X`, `f1_X`, `precision_X`, `recall_X`, `threshold_X` |
| `data/processed/11_neuralprophet_model.pkl` | Modèle final NeuralProphet (joblib) | Entraîné sur l'ensemble des données labellisées |
| `data/processed/11_decision_deploiement.csv` | Table de comparaison NP vs LightGBM | `modele`, `horizon`, `auc_global`, `f1_global`, `temps_train_min`, `decision` |

---

## Règles métier

### RM-1 : Encodage temporel synthétique (sans lacune estivale)

Pour éviter que NeuralProphet n'interprète les mois d'août-septembre (inter-campagne) comme des données manquantes et n'insère des lignes fictives, chaque décade de campagne reçoit une **date artificielle** espacée de 10 jours depuis la référence du 01/10/2001, sans lacune :

```
date_synthétique = REF_DATE + Timedelta(days=10) × ((start_year - 2001) × 30 + (decade - 1))
```

Où `start_year` est l'année de début de la campagne (ex. 2001 pour la campagne "2001-2002").

### RM-2 : Configuration NeuralProphet

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| `n_forecasts` | 10 | Horizon cible (10 décades) |
| `n_lags` | 0 | Pas de composante AR — voir note |
| `epochs` | 100 | Compromis vitesse/convergence (CPU) |
| `learning_rate` | 0,001 | Convergence stable |
| `accelerator` | `"cpu"` | Contrainte ADR-0002 |
| `normalize` | `"off"` | Labels binaires 0/1, normalisation inutile |
| `drop_missing` | `True` | Ignore les cellules non prospectées (y=NaN) |

**Note sur `n_lags=0`** : Avec `n_lags=0`, NeuralProphet force `n_forecasts=1` en interne (limitation de la version 0.8). La stratégie multi-horizon est réalisée par décalage : `pred_horizon_k = yhat1` calculé pour la date cible décalée de k décades. Le modèle prédit tendance + saisonnalité pour la date cible, sans composante autoregressive (lags AR).

### RM-3 : Construction du panel NeuralProphet

Le panel est une grille complète (90 régions × N décades de campagne) avec :
- Colonne `ID` : `region_num` converti en str (ex. `"42"`)
- Colonne `ds` : date synthétique (voir RM-1)
- Colonne `y` : label 0/1 ou NaN (cellule non prospectée → `drop_missing=True` supprime ces lignes lors de l'entraînement)

### RM-4 : Critère de déploiement

NeuralProphet est déployé en remplacement du baseline LightGBM si **les deux conditions** sont réunies :

1. `auc_roc_decadaire (GLOBAL NP) > auc_roc (GLOBAL LightGBM #07)`
2. Temps total d'entraînement du modèle final < 30 minutes

Si l'une des conditions n'est pas satisfaite : `decision = "keep_lgbm_baseline"`.

La décision est enregistrée dans `11_decision_deploiement.csv` et doit être consultée avant tout usage des prédictions NP en production.

### RM-5 : Walk-forward identique à #07

Le même découpage en 8 folds expanding-window est utilisé (voir [#07](07-lgbm-baseline.md) RM-4). La fonction `walk_forward_folds()` est importée depuis `lgbm_baseline_07.py`.

---

## Exécution

```bash
python src/neuralprophet_11.py
```

Le script affiche l'heure de début et la durée estimée. Si la durée dépasse 30 minutes, le critère de déploiement sera automatiquement `"keep_lgbm_baseline"`.

---

## Dépendances

- **Amont** :
  - [#06](06-table-entrainement.md) — `06_table_entrainement_unifiee.parquet`
  - [#07](07-lgbm-baseline.md) — `07_rapport_walk_forward.csv` (AUC LightGBM de référence)
- **Aval** : aucun pipeline n'est bloqué par les sorties de ce pipeline (chemin expérimental indépendant)
- **Bibliothèques** : `neuralprophet`, `torch` (CPU), `pandas`, `numpy`, `joblib`, `pyarrow`

---

## Avertissements

Ce pipeline est **expérimental**. Ses prédictions ne sont pas utilisées en production sauf si `11_decision_deploiement.csv` indique `decision = "deploy"`.

Sur CPU standard, le temps d'entraînement peut dépasser 30 minutes pour le run complet (8 folds × modèle final), déclenchant automatiquement la décision `keep_lgbm_baseline`. Ce comportement est conforme à la contrainte de 30 minutes du budget CPU ([ADR-0002](../adr/0002-contrainte-cpu-uniquement.md)).

Avec `n_lags=0`, le modèle ne capture pas les dynamiques autorégressives à court terme — son avantage éventuel sur LightGBM proviendrait uniquement d'une meilleure modélisation des tendances et de la saisonnalité intra-campagne. Si GPU devient disponible, envisager `n_lags > 0` pour capturer les dynamiques AR (referrer à l'ADR-0002 pour le candidat d'évolution : GAT-LSTM).
