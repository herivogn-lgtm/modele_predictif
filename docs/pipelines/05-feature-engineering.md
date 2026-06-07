# Pipeline #05 — Feature engineering

**Script** : `src/feature_engineering_05.py`  
**Entrée** : `data/processed/04_variables_environnementales.parquet`  
**Sortie** : `data/processed/05_features_engineering.parquet`  
**Durée estimée** : 5–15 minutes  
**Dépendance obligatoire** : Pipeline [#04](04-extraction-gee.md)

---

## Objectif

Enrichir les variables environnementales satellitaires avec trois catégories de features dérivées : le compteur de Plage d'Optimum Pluviométrique (POP), qui est le signal précurseur de grégarisation le plus documenté dans la littérature acridologique, les lags temporels (décade-1, décade-2, mois-1) pour capturer la dynamique passée, et les lags spatiaux (moyenne des régions contiguës) pour capturer la diffusion spatiale entre secteurs voisins.

---

## Entrées

| Fichier | Description | Colonnes clés utilisées |
|---------|-------------|-------------------------|
| `data/processed/04_variables_environnementales.parquet` | Variables GEE par région × décade | `region_id`, `campaign`, `decade_num`, `date_start`, `chirps_sum_mean`, `ndvi_mean`, `evi_mean`, `lst_mean`, `soil_moisture_mean` |
| `data/region_naturelle/region_naturelle.shp` | 90 polygones | `rn_num`, `geometry` — pour la topologie d'adjacence spatiale |

---

## Sorties

Toutes les colonnes de `04_variables_environnementales.parquet`, plus 14 colonnes ajoutées :

| Colonne | Type | Description |
|---------|------|-------------|
| `pop_consecutive` | int | Nombre de mois consécutifs en POP à la date de cette décade |
| `chirps_sum_mean_lag1d` | float | `chirps_sum_mean` de la décade précédente (D-1) |
| `chirps_sum_mean_lag2d` | float | `chirps_sum_mean` de 2 décades avant (D-2) |
| `chirps_sum_mean_lag1m` | float | `chirps_sum_mean` de 3 décades avant (proxy M-1) |
| `ndvi_mean_lag1d/lag2d/lag1m` | float | Lags temporels NDVI |
| `evi_mean_lag1d/lag2d/lag1m` | float | Lags temporels EVI |
| `lst_mean_lag1d/lag2d/lag1m` | float | Lags temporels LST |
| `soil_moisture_mean_lag1d/lag2d/lag1m` | float | Lags temporels humidité sol |
| `chirps_sum_mean_spatial_lag` | float | Moyenne `chirps_sum_mean` des régions contiguës |
| `ndvi_mean_spatial_lag` | float | Moyenne NDVI des régions contiguës |
| `evi_mean_spatial_lag` | float | Moyenne EVI des régions contiguës |
| `lst_mean_spatial_lag` | float | Moyenne LST des régions contiguës |
| `soil_moisture_mean_spatial_lag` | float | Moyenne humidité sol des régions contiguës |

---

## Règles métier

### RM-1 : Calcul du compteur POP (Plage d'Optimum Pluviométrique)

La POP est définie comme la période où les précipitations mensuelles sont comprises dans l'intervalle optimal pour *Locusta migratoria capito* : `CHIRPS mensuel ∈ [50, 125] mm` (bornes incluses).

Procédure de calcul :
1. Agréger les 3 décades de chaque mois en total mensuel : `chirps_mensuel = somme(chirps_sum_mean des 3 décades)`
2. Vérifier si `50 ≤ chirps_mensuel ≤ 125` → le mois est "en POP"
3. Calculer le compteur de mois consécutifs en POP, par (région × campagne), de la décade 1 à la décade 30

Règles :
- Le compteur se **réinitialise à 0** au début de chaque nouvelle campagne acridienne (octobre)
- Un mois avec `chirps_mensuel = NaN` est traité comme "hors POP" (compteur remis à 0)
- Les 3 décades d'un même mois partagent toutes la **même valeur** de `pop_consecutive` (la valeur du mois en cours)

Un `pop_consecutive ≥ 3` indique 3 mois consécutifs de précipitations optimales — condition reconnue comme précurseur de grégarisation dans la littérature (Manuel de lutte préventive ; thèse Randrianarijaona 2026).

### RM-2 : Lags temporels sans fuite de données

Les lags sont calculés par `shift(k)` sur les séries triées par `date_start` et groupées par `region_id`. Aucune valeur future n'est jamais utilisée.

| Suffixe | Décalage | Signification |
|---------|----------|---------------|
| `_lag1d` | shift(1) | Valeur de la décade précédente (D-1) |
| `_lag2d` | shift(2) | Valeur de 2 décades avant (D-2) |
| `_lag1m` | shift(3) | Valeur de 3 décades avant (approximation M-1) |

Les premières décades de chaque région × campagne recevront NaN pour les lags manquants — comportement attendu.

### RM-3 : Contiguïté spatiale (critère Queen)

La matrice d'adjacence est construite via `shapely.touches()` sur les polygones du shapefile `region_naturelle` — deux régions sont voisines si elles partagent au moins un point de frontière (critère Queen). Pas de buffer artificiel.

Les lags spatiaux sont calculés comme la **moyenne simple** des valeurs de toutes les régions voisines à la même décade. Les régions sans aucun voisin contigu (ex. îles) reçoivent `NaN` pour leurs lags spatiaux.

### RM-4 : Taux de NaN attendus

| Feature | Taux NaN attendu | Cause |
|---------|-----------------|-------|
| `_lag1d` | ~3 % | Première décade de chaque campagne par région |
| `_lag2d` | ~3–6 % | Deux premières décades |
| `_lag1m` | ~3–9 % | Trois premières décades |
| `_spatial_lag` | < 1 % | Régions sans voisin contigu uniquement |

Un taux de NaN significativement supérieur indique un problème de tri ou de groupement lors du calcul des lags.

---

## Exécution

```bash
python src/feature_engineering_05.py
```

---

## Dépendances

- **Amont** : [#04](04-extraction-gee.md) — `04_variables_environnementales.parquet`
- **Aval** : [#06](06-table-entrainement.md) — `05_features_engineering.parquet`
- **Bibliothèques** : `pandas`, `geopandas`, `shapely`, `numpy`, `pyarrow`

---

## Avertissements

La feature `pop_consecutive` est le signal acridologique le plus interprétable du modèle. Sa valeur est visible dans les sorties opérationnelles via `07_feature_importances.csv` — une importance élevée confirme que le modèle a appris à utiliser ce signal précurseur documenté dans la littérature.

Le renommage des colonnes clés de `04_variables_environnementales.parquet` (`region_id`, `campaign`, `decade_num`) vers les noms canoniques du projet (`rn_num`, `campagne_calc`, `campagne_decade`) est effectué dans le pipeline [#06](06-table-entrainement.md), pas ici.
