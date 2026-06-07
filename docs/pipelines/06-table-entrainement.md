# Pipeline #06 — Table d'entraînement unifiée

**Script** : `src/table_entrainement_06.py`  
**Entrées** : Sorties de #02, #03 et #05  
**Sortie** : `data/processed/06_table_entrainement_unifiee.parquet`  
**Durée estimée** : < 2 minutes  
**Dépendances obligatoires** : Pipelines [#02](02-gregarite-potentiel.md), [#03](03-labels-entrainement.md), [#05](05-feature-engineering.md)

---

## Objectif

Construire la table ML unifiée en joignant les labels ([#03](03-labels-entrainement.md)), les features environnementales enrichies ([#05](05-feature-engineering.md)) et les variables acridologiques agrégées ([#02](02-gregarite-potentiel.md)), puis assigner le split walk-forward (`train` / `validation` / `inference`) à chaque cellule spatio-temporelle. Cette table est la seule entrée de tous les modèles ML (#07, #08, #09, #11).

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/03_labels_region_decade.parquet` | `rn_num`, `campagne_calc`, `campagne_decade`, `label`, `effort_prospection` |
| `data/processed/05_features_engineering.parquet` | `region_id` (→ `rn_num`), `campaign` (→ `campagne_calc`), `decade_num` (→ `campagne_decade`), toutes les features |
| `data/processed/02_gregarite_potentiel.parquet` | `rn_num`, `campagne_calc`, `campagne_decade`, `niveau_gregarite`, `potentiel_acridien` |

> **Attention** : Le fichier #05 utilise des noms de colonnes différents des noms canoniques du projet. Le renommage est effectué dans ce pipeline (voir RM-3).

---

## Sorties

Colonnes du fichier `06_table_entrainement_unifiee.parquet`, dans l'ordre :

| Groupe | Colonnes | Description |
|--------|----------|-------------|
| Clés | `rn_num`, `rn_nom`, `campagne_calc`, `campagne_decade` | Identifiants de la cellule |
| Méta | `split`, `effort_prospection`, `label` | Split ML + état de la cellule |
| Acridologie (features) | `potentiel_acridien_dominant`, `niveau_gregarite_dominant` | État acridien observé agrégé par mode |
| Features GEE + dérivées | Toutes les colonnes de #05 | Variables environnementales + lags + POP |

---

## Règles métier

### RM-1 : Assignation du split walk-forward

| Valeur `split` | Condition |
|----------------|-----------|
| `"inference"` | `label = NA` (quelle que soit la campagne, y compris 2023-2024) |
| `"train"` | `label` non-NA ET campagne_calc commence en 2015 ou avant (ex. `"2001-2002"` à `"2015-2016"`) |
| `"validation"` | `label` non-NA ET campagne_calc commence en 2016 ou après (ex. `"2016-2017"` à `"2022-2023"`) |

Le split suit la logique expanding-window : les données de validation sont toujours chronologiquement postérieures à celles d'entraînement.

### RM-2 : Assertions de cohérence en sortie

Le pipeline vérifie :
1. Aucune cellule `split ∈ {train, validation}` ne doit avoir `label = NA`
2. Aucune campagne ne doit apparaître à la fois dans `train` et dans `validation` — étanchéité temporelle garantie
3. La campagne `"2023-2024"` ne doit apparaître que dans `split = "inference"`

### RM-3 : Renommage des colonnes du fichier #05

| Colonne dans #05 | Colonne canonique dans #06 |
|------------------|---------------------------|
| `region_id` | `rn_num` |
| `campaign` | `campagne_calc` |
| `decade_num` | `campagne_decade` |

Ce renommage est appliqué avant la jointure.

### RM-4 : Agrégation grégarité et potentiel acridien depuis #02

Les colonnes `niveau_gregarite_dominant` et `potentiel_acridien_dominant` sont calculées par **mode** (valeur la plus fréquente) des relevés de la cellule. Ces colonnes sont des **features ML** représentant l'état acridien passé observé — elles ne sont pas des cibles.

En cas d'égalité de mode, le niveau le plus élevé est retenu (comportement conservateur).

### RM-5 : Dégradation gracieuse si #05 absent

Si `05_features_engineering.parquet` n'existe pas (pipeline #04 non exécuté, GEE non disponible), la table est produite avec les labels seuls et les features acridologiques de #02. Un avertissement Python est émis mais le script ne s'arrête pas. Dans ce cas, les modèles #07/#08 peuvent être testés structurellement mais l'AUC sera très faible (features satellitaires manquantes).

---

## Exécution

```bash
python src/table_entrainement_06.py
```

---

## Dépendances

- **Amont** :
  - [#02](02-gregarite-potentiel.md) — `02_gregarite_potentiel.parquet`
  - [#03](03-labels-entrainement.md) — `03_labels_region_decade.parquet`
  - [#05](05-feature-engineering.md) — `05_features_engineering.parquet`
- **Aval** : [#07](07-lgbm-baseline.md), [#08](08-lgbm-hierarchique.md), [#09](09-sorties-operationnelles.md), [#11](11-neuralprophet.md)
- **Bibliothèques** : `pandas`, `numpy`, `pyarrow`

---

## Avertissements

Le renommage des colonnes (RM-3) est un point de friction récurrent lors de la mise à jour du pipeline #05. Si #05 évolue et modifie les noms des colonnes `region_id`, `campaign` ou `decade_num`, la jointure échouera silencieusement ou produira un fichier vide. Vérifier les dimensions du fichier de sortie après chaque exécution.

La colonne `niveau_gregarite_dominant` est encodée en `pd.Categorical` avec les catégories ordonnées `["absent", "S", "St", "T", "G"]` pour permettre son utilisation directe par LightGBM.
