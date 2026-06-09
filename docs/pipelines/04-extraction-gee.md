# Pipeline #04 — Extraction des variables environnementales (GEE, maille cellule 1 km)

**Scripts** : `src/04_extraction_variables_gee.py` (getInfo) · `src/04b_export_variables_gee.py` (Export.table)
**Configuration** : `src/config_gee.py`
**Entrée** : `data/processed/01_grille_1km.parquet` + Google Earth Engine
**Sortie** : `data/processed/04_variables_environnementales/` (dataset Parquet partitionné)
**Durée estimée** : variable (voir variantes) ; mode test 5–10 min
**Dépendance obligatoire** : compte GEE authentifié + Pipeline [#01](01-nettoyage-jointure.md) (grille)

> Ce pipeline est le seul à nécessiter un accès internet et un compte Google Earth Engine. Procédure d'installation/authentification : voir le [runbook-04-extraction-gee.md](../runbook-04-extraction-gee.md).

---

## Objectif

Extraire **NDVI/EVI** (MODIS MOD13A2), **LST** (MODIS MOD11A2) et **précipitations CHIRPS**, agrégés **à la décade** sur la **grille 1 km clipée** (#01), pour produire une table cellule 1 km × décade alignée sur les labels (#03) : `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`. Ces covariables forment la majorité des features des modèles ([#07](07-benchmark-ordinal.md)).

> Refonte vs l'ancien pipeline : passage de la maille **région naturelle** à la maille **cellule 1 km**, et réduction du jeu de variables à NDVI/EVI/LST/CHIRPS (+ anomalie). ERA5, DEM, texture de sol, occupation du sol et ENSO ont été retirés du périmètre.

---

## Entrées

| Source | Collection GEE | Variables |
|--------|----------------|-----------|
| `data/processed/01_grille_1km.parquet` | — | Géométries des ~181 000 cellules 1 km (centroïdes échantillonnés) |
| CHIRPS | `UCSB-CHG/CHIRPS/DAILY` | Précipitations décadaires cumulées (mm) + anomalie |
| MODIS NDVI/EVI | `MODIS/061/MOD13A2` | Indices de végétation |
| MODIS LST | `MODIS/061/MOD11A2` | Température de surface diurne |

À 1 km, CHIRPS (~5,5 km) et LST (~1 km) ont ≤ 1 pixel par cellule : on ne conserve que la **moyenne** par cellule (`sampleRegions`, 1 point/cellule).

---

## Sorties

`data/processed/04_variables_environnementales/` (Parquet partitionné). Colonnes : `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, `date_start`, `date_end`, `year`, `month`, `decade_part`, `chirps_sum_mean`, `ndvi_mean`, `evi_mean`, `lst_mean`, `chirps_anomaly_mean`.

---

## Deux variantes d'extraction

| Variante | Script | Mécanisme | Quand l'utiliser |
|----------|--------|-----------|------------------|
| **getInfo interactif** | `04_extraction_variables_gee.py` | `sampleRegions` côté serveur → `getInfo`, bissection des specs si > limite GEE (5000 éléments) | Petits lots, debug, run incrémental |
| **Export.table batch** | `04b_export_variables_gee.py` | Tâches d'export GEE asynchrones vers Drive, puis import | Run historique one-shot (~181 000 cellules × ~780 décades ≈ 141 M lignes) |

⚠️ À ~181 000 cellules, la variante getInfo demande ~86 000 appels (plafond GEE de 5000 éléments/getInfo) → plusieurs heures. Pour un run complet, préférer **04b** (Export.table), qui découpe les exports dynamiques par lots d'années.

---

## Règles métier

### Facteurs d'échelle MODIS

| Variable | Facteur | Brut → réel |
|----------|---------|-------------|
| NDVI, EVI | × 0,0001 | 8 000 → 0,8 |
| LST | × 0,02 | 15 000 → 300 K |

Des NDVI > 1 ou LST > 400 indiquent un facteur d'échelle non appliqué → relancer.

### Anomalie pluviométrique CHIRPS

`chirps_anomaly_mean` = écart de la pluie décadaire à la climatologie de référence pour le même mois et la même position dans le mois (D1/D2/D3), par cellule.

### Robustesse GEE

Retry exponentiel sur `EEException` (quota/timeout). Les erreurs déterministes liées à la taille d'un getInfo déclenchent une **bissection** des specs plutôt qu'un échec.

---

## Exécution

```bash
# Authentification GEE (une seule fois par machine)
./.venv/bin/python -c "import ee; ee.Authenticate()"

# Variante getInfo (lots / debug)
./.venv/bin/python src/04_extraction_variables_gee.py

# Variante Export.table batch (run historique complet — recommandé)
./.venv/bin/python src/04b_export_variables_gee.py
```

`GEE_PROJECT_ID` doit être renseigné dans `src/config_gee.py` avant toute exécution.

---

## Dépendances

- **Amont** : [#01](01-nettoyage-jointure.md) — `01_grille_1km.parquet`
- **Aval** : [#05](05-feature-engineering.md) — `04_variables_environnementales/`
- **Bibliothèques** : `earthengine-api`, `geopandas`, `pandas`, `pyarrow`

---

## Avertissements

**Taux de NaN NDVI** : couverture nuageuse élevée en saison des pluies (nov.–avr.) → 30–40 % de NaN NDVI est normal, pas un défaut d'extraction.

**Lacune 2023-2024** : les covariables GEE restent continues sur la lacune de labels 2023-2024 ([ADR 0004](../adr/0004-fenetre-entrainement-complete.md)) ; la campagne est sautée en validation, pas en extraction.
