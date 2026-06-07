# Pipeline #03 — Labels d'entraînement

**Script** : `src/labels_entrainement_03.py`  
**Entrée** : `data/processed/02_gregarite_potentiel.parquet`  
**Sortie** : `data/processed/03_labels_region_decade.parquet`  
**Durée estimée** : < 2 minutes  
**Dépendance obligatoire** : Pipeline [#02](02-gregarite-potentiel.md)

---

## Objectif

Agréger les relevés acridiens individuels en labels d'entraînement au niveau de la cellule spatio-temporelle (région naturelle × campagne × décade). Distinguer rigoureusement les trois états possibles : **présence** (1 = locusta confirmée), **absence vérifiée** (0 = prospection effectuée, aucun criquet trouvé), et **cellule non prospectée** (NA = valeur inconnue, à ne pas confondre avec une absence). Ce fichier constitue la variable cible de tous les modèles ML.

---

## Entrées

| Fichier | Description | Colonnes clés utilisées |
|---------|-------------|-------------------------|
| `data/processed/02_gregarite_potentiel.parquet` | Relevés avec indicateurs acridiens | `rn_num`, `campagne_calc`, `campagne_decade`, `Sol`, `Trans`, `Greg` |
| `data/region_naturelle/region_naturelle.shp` | Catalogue des 90 régions naturelles | `rn_num`, `rn_nom` |

---

## Sorties

| Colonne | Type | Description |
|---------|------|-------------|
| `rn_num` | Int64 | Identifiant de la région naturelle (1–90) |
| `rn_nom` | str | Nom de la région naturelle |
| `campagne_calc` | str | Campagne au format `"YYYY-YYYY+1"` |
| `campagne_decade` | int (1–30) | Position de la décade dans la campagne |
| `label` | Int64 nullable | 1 = présence, 0 = absence vérifiée, NA = cellule non prospectée |
| `effort_prospection` | int | Nombre de relevés terrain effectués dans cette cellule |

---

## Règles métier

### RM-1 : Règle de présence (label = 1)

Pour un groupe de relevés appartenant à la même cellule (rn_num × campagne_calc × campagne_decade) : `label = 1` si au moins **une** ligne vérifie `Sol + Trans + Greg > 0`. Les valeurs NaN dans ces colonnes sont traitées comme 0 pour ce calcul.

### RM-2 : Règle d'absence vérifiée (label = 0)

`label = 0` si la cellule contient au moins un relevé ET que toutes les lignes vérifient `Sol + Trans + Greg = 0`. Une cellule avec `label = 0` représente une **prospection effectuée sans observation** — c'est une information positive sur l'état de la population, pas une absence de données.

### RM-3 : Règle des cellules non prospectées (label = NA)

Une cellule (rn_num × campagne × décade) sans aucun relevé terrain reçoit `effort_prospection = 0` et `label = NA`. Cette valeur **masquée** (NA) ne doit jamais être interprétée comme une absence — elle signifie que l'état de la population dans cette cellule est inconnu.

La grille de toutes les cellules possibles est construite comme le produit cartésien de toutes les 90 régions avec toutes les décades des campagnes prospectées. Toutes les cellules manquantes sont explicitement représentées avec `label = NA`.

### RM-4 : Exclusion de la campagne 2023-2024

`label = NA` est forcé pour toutes les cellules de la campagne `"2023-2024"`, même si des relevés terrain existent. L'`effort_prospection` est conservé (les relevés sont comptés). Ces cellules seront utilisées en **inférence uniquement** dans les pipelines #07, #08 et #09 — elles ne participent jamais à l'entraînement ni à la validation du modèle.

### RM-5 : Assertions de cohérence en sortie

Le pipeline vérifie en fin d'exécution :
1. Aucune cellule avec `effort_prospection = 0` ne doit avoir `label != NA`
2. Aucune cellule avec `effort_prospection > 0` ne doit avoir `label = NA`, sauf si la campagne est explicitement exclue (ex. 2023-2024)

Une violation de ces assertions déclenche une erreur bloquante.

---

## Exécution

```bash
python src/labels_entrainement_03.py
```

---

## Dépendances

- **Amont** : [#02](02-gregarite-potentiel.md) — `02_gregarite_potentiel.parquet`
- **Aval** : [#06](06-table-entrainement.md) — `03_labels_region_decade.parquet` est la source des labels et de l'effort de prospection
- **Bibliothèques** : `pandas`, `geopandas`, `numpy`, `pyarrow`

---

## Avertissements

Les relevés avec `hors_aire = True` (hors des 12 polygones de l'aire grégarigène, marqués en [#01](01-nettoyage-jointure.md)) sont **inclus** dans ce calcul s'ils ont un `rn_num` valide. Ils constituent de vraies prospections et contribuent à l'effort. Les régions naturelles partiellement situées en dehors de l'aire grégarigène peuvent donc avoir des labels valides.

Le biais de détection lié à l'effort de prospection est analysé en détail dans le [#10](10-rapport-performance.md) : les régions peu prospectées (`effort_prospection` faible) ont un taux de présence artificiellement bas, non par absence réelle mais par manque d'observation. Ce biais est inhérent aux données terrain et non à la qualité du modèle.
