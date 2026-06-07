# Pipeline #04 — Extraction des variables environnementales (GEE)

**Script** : `src/04_extraction_variables_gee.py`  
**Configuration** : `src/config_gee.py`  
**Entrée** : `data/region_naturelle/region_naturelle.shp` + Google Earth Engine  
**Sortie** : `data/processed/04_variables_environnementales.parquet`  
**Durée estimée** : 2–3 heures (run complet 2001–2026) ; 5–10 min en mode test  
**Dépendance obligatoire** : compte GEE authentifié (voir ci-dessous)

> Ce pipeline est le seul à nécessiter un accès internet et un compte Google Earth Engine. Pour la procédure d'installation et d'authentification, voir aussi le [runbook-04-extraction-gee.md](../runbook-04-extraction-gee.md).

---

## Objectif

Extraire les statistiques zonales des variables environnementales depuis Google Earth Engine sur les 90 régions naturelles de Madagascar, pour chaque décade de campagne acridienne de 2001 à 2026. Ces variables (précipitations, végétation, température, humidité du sol, etc.) constituent la majorité des features utilisées par les modèles ML dans les pipelines #07, #08 et #11.

---

## Entrées

| Source | Collection GEE / URL | Variables extraites |
|--------|---------------------|---------------------|
| `data/region_naturelle/region_naturelle.shp` | — | Géométries des 90 régions (polygones) |
| CHIRPS | `UCSB-CHG/CHIRPS/DAILY` | Précipitations décadaires cumulées (mm) |
| MODIS NDVI/EVI | `MODIS/061/MOD13A2` | Indices de végétation |
| MODIS LST | `MODIS/061/MOD11A2` | Température de surface diurne |
| ERA5 | `ECMWF/ERA5_LAND/MONTHLY_AGGR` | Humidité du sol (0–7 cm) |
| MODIS occupation sol | `MODIS/061/MCD12Q1` | Classe IGBP dominante (annuelle) |
| SRTM DEM | `USGS/SRTMGL1_003` | Altitude (statique) |
| OpenLandMap | texture sol | Texture sol : sable, argile, limon (statique) |
| NOAA CPC | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` | Indice ENSO/ONI mensuel |

---

## Sorties

Taille attendue : ~67 500 lignes (90 régions × ~750 décades de campagne).

| Colonne | Source | Type | Plage typique |
|---------|--------|------|---------------|
| `region_id` | — | int | 1–90 (= `rn_num`) |
| `region_nom` | — | str | Nom de la région naturelle |
| `campaign` | — | str | `"YYYY-YYYY+1"` |
| `decade_num` | — | int | 1–30 |
| `date_start`, `date_end` | — | Timestamp | Premier et dernier jour de la décade |
| `year`, `month`, `decade_part` | — | int | Composantes calendaires |
| `chirps_sum_mean/min/max/std` | CHIRPS | float (mm) | 0–300 |
| `chirps_anomaly_mean` | CHIRPS calculé | float (mm) | -200 à +200 |
| `ndvi_mean/min/max/std` | MODIS | float | -1 à 1 |
| `evi_mean/min/max/std` | MODIS | float | -1 à 1 |
| `lst_mean/min/max/std` | MODIS | float (Kelvin) | 270–330 |
| `soil_moisture_mean/min/max/std` | ERA5 | float (m³/m³) | 0–0.6 |
| `land_cover_mode` | MODIS | int | 1–17 (classes IGBP) |
| `dem_mean/min/max` | SRTM | float (m) | 0–3000 |
| `soil_sand_mean` | OpenLandMap | float (%) | 0–100 |
| `soil_clay_mean` | OpenLandMap | float (%) | 0–100 |
| `soil_silt_mean` | OpenLandMap | float (%) | 0–100 |
| `enso_oni` | NOAA CPC | float | -3 à 3 |

---

## Règles métier

### RM-1 : Anomalie pluviométrique CHIRPS

L'anomalie est calculée **en pandas** (pas sur GEE) par soustraction : `chirps_anomaly_mean = chirps_sum_mean − chirps_baseline_mean`. La baseline est la moyenne des sommes décadaires CHIRPS 1981–2010 pour le même mois et la même position dans le mois (D1, D2 ou D3), par région.

La baseline est calculée une seule fois et mise en cache dans `data/processed/04_chirps_baseline_cache.parquet` (90 régions × 36 décades-types). Ce cache est réutilisé sans recalcul lors des runs suivants (durée de la 1re fois : 30–45 min).

### RM-2 : Facteurs d'échelle MODIS obligatoires

Les valeurs brutes MODIS doivent être divisées par leur facteur d'échelle avant utilisation :

| Variable | Facteur d'échelle | Valeur brute → valeur réelle |
|----------|-------------------|------------------------------|
| NDVI, EVI | × 0,0001 | Ex. 8 000 → 0,8 |
| LST | × 0,02 | Ex. 15 000 → 300 K |

Des valeurs NDVI > 1 ou LST > 400 dans le fichier de sortie indiquent que le facteur d'échelle n'a pas été appliqué — le pipeline doit être relancé.

### RM-3 : Résolutions spatiales par source

| Source | Échelle spatiale (reduce) |
|--------|--------------------------|
| CHIRPS | 5 566 m |
| NDVI/EVI (MODIS) | 250 m |
| LST (MODIS) | 1 000 m |
| ERA5 | 27 750 m |
| Texture sol (OpenLandMap) | 250 m |

Les statistiques zonales (mean, stdDev, min, max) sont calculées via `ee.Reducer.mean().combine(ee.Reducer.stdDev(), ...).combine(ee.Reducer.min(), ...).combine(ee.Reducer.max(), ...)`.

### RM-4 : Occupation du sol — mode catégoriel

`land_cover_mode` utilise `ee.Reducer.mode()` et non mean/max. La valeur est un entier IGBP entre 1 et 17 (ex. 10 = Grasslands, 14 = Croplands). Mise en cache annuelle : les 3 décades d'un même mois partagent la même valeur de classe IGBP.

### RM-5 : Texture du sol — extraction statique

La texture sol (sable, argile, limon en %) est calculée une seule fois (données OpenLandMap, non disponibles en time-series) et jointe à toutes les lignes décadaires de la même région. Valeurs natives en g/kg divisées par 10 pour obtenir des pourcentages. La somme `sable + argile + limon` peut légèrement dépasser 100 % en raison des arrondis (seuil d'acceptation : ≤ 120 %).

### RM-6 : Robustesse et retry exponentiel GEE

En cas d'erreur `EEException` (quota GEE temporairement atteint ou timeout), le script réessaie jusqu'à 5 fois avec une attente exponentielle de 2^attempt secondes. En cas d'erreur `requests.HTTPError` lors de la récupération de l'indice ENSO/ONI (source NOAA), le script continue sans valeur ONI — cette variable n'est pas bloquante pour les pipelines aval.

---

## Exécution

```bash
# Authentification GEE (une seule fois par machine)
python -c "import ee; ee.Authenticate()"

# Test d'intégration — 5 régions, 2 campagnes (5–10 min)
python src/04_extraction_variables_gee.py --test-only

# Run sur une seule année (10–15 min)
python src/04_extraction_variables_gee.py --years 2010

# Run complet 2001–2026 (2–3 h) — recommandé en session détachée
nohup python src/04_extraction_variables_gee.py > logs/04_gee.log 2>&1 &
```

La variable `GEE_PROJECT_ID` doit être renseignée dans `src/config_gee.py` avant toute exécution.

---

## Dépendances

- **Amont** : aucun pipeline Python précédent — sources externes uniquement (GEE + NOAA)
- **Aval** : [#05](05-feature-engineering.md) — `04_variables_environnementales.parquet`
- **Bibliothèques** : `earthengine-api`, `geopandas`, `pandas`, `requests`, `pyarrow`

---

## Avertissements

**Taux de NaN NDVI** : Madagascar a une couverture nuageuse élevée pendant la saison des pluies (novembre–avril). Un taux de NaN NDVI atteignant 30–40 % est normal — il n'indique pas un problème d'extraction.

**Interruption en cours de run** : En cas d'interruption, relancer avec `--years` sur les années manquantes et fusionner les fichiers Parquet partiels avec `pandas.concat`. Ne pas relancer un run complet si une partie des données est déjà extraite.

**Cache baseline CHIRPS** : Si `04_chirps_baseline_cache.parquet` est supprimé, la prochaine exécution recalculera la baseline (30–45 min supplémentaires). Ne pas supprimer ce cache sauf en cas de mise à jour délibérée de la baseline de référence.
