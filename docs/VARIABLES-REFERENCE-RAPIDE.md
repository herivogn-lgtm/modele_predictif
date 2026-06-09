# Variables prédictives — Référence rapide

**Modèle** : Régression Ordinale  
**Variables** : 24 prédicteurs  
**Performance** : QWK 0.307, Recall 2-3 54.18%

---

## Résumé par source

| Source | Variables | Couverture | Rôle écologique |
|--------|-----------|------------|-----------------|
| ☔ **CHIRPS** | 7 | 97% | Déclencheur de la reproduction + POP |
| 🌱 **MODIS végétation** | 6 | 97% | Disponibilité de nourriture |
| 🌡️ **MODIS LST** | 3 | 74% | Vitesse de développement |
| 🦗 **Relevés terrain** | 4 | 0.5% | Persistance locale (cellules observées) |
| 📍 **Métadonnées** | 4 | 100% | Saisonnalité + différences régionales |

---

## Les 7 variables les plus importantes (hypothèse)

1. **`pop_consecutive`** (CHIRPS) — Mois consécutifs en POP (50-125 mm/mois) 🔴 CRITIQUE
2. **`ndvi_mean`** (MODIS) — Disponibilité végétation herbacée
3. **`chirps_sum_mean`** (CHIRPS) — Pluie décadaire directe
4. **`severite_lag1`** (Terrain) — Persistance locale (si disponible)
5. **`AIRE_CODE`** (Spatial) — Différences régionales AMI/ATM/AD/AGT
6. **`ndvi_mean_lag1d`** (MODIS) — Dynamique de végétation
7. **`chirps_anomaly_mean`** (CHIRPS) — Anomalie climatique

---

## Variables détaillées

### ☔ Pluviométrie — CHIRPS (97% couverture)

```
chirps_sum_mean         Pluie décadaire (mm) à T
chirps_sum_mean_lag1d   Pluie à T-1
chirps_sum_mean_lag2d   Pluie à T-2
chirps_anomaly_mean     Anomalie vs climatologie 1981-2010
chirps_cumul_2d         Cumul roulant 2 décades
chirps_cumul_3d         Cumul roulant 3 décades
pop_consecutive         🔴 Mois consécutifs en POP [50-125 mm/mois]
```

**POP = Plage d'Optimum Pluviométrique** : Facteur majeur de grégarisation (thèse §006, §013)

---

### 🌱 Végétation — MODIS MOD13A2 (97% couverture)

```
ndvi_mean         NDVI décade T (vigueur végétative) [-1, 1]
ndvi_mean_lag1d   NDVI T-1
ndvi_mean_lag2d   NDVI T-2
evi_mean          EVI décade T (végétation dense) [-1, 1]
evi_mean_lag1d    EVI T-1
evi_mean_lag2d    EVI T-2
```

**NDVI** : Normalized Difference Vegetation Index (verdure)  
**EVI** : Enhanced Vegetation Index (moins saturé en zones denses)

---

### 🌡️ Température — MODIS MOD11A2 (74% couverture)

```
lst_mean         Température surface diurne (K) à T
lst_mean_lag1d   LST T-1
lst_mean_lag2d   LST T-2
```

⚠️ **Couverture plus faible** (74%) : Nuages bloquent l'infrarouge thermique

**Conversion** : °C = K - 273.15

---

### 🦗 Historique acridien — Relevés IFVM (0.5% couverture)

```
severite_lag1        Sévérité-phase [0-3] à T-1
severite_lag2        Sévérité-phase [0-3] à T-2
effort_prospection   Nombre de relevés dans la cellule
intensite            Log(densité DL/DI)
```

❌ **Disponible uniquement pour 5 396 cellules observées** (3% de la grille)  
❌ **NaN pour 175 017 cellules non observées** (97%)

---

### 📍 Spatial/Temporel (100% couverture)

```
AIRE_CODE      Code aire grégarigène [1-4]
               1=AGT, 2=AMI, 3=ATM, 4=AD
year           Année civile
month          Mois [1-12]
decade_part    Position dans mois [1-3]
```

---

## Lags temporels

**Profondeur** : 2 décades (T-1, T-2) = ~20 jours de fenêtre d'observation

| Variable source | Valeurs disponibles |
|-----------------|---------------------|
| CHIRPS, NDVI, EVI, LST | T, T-1, T-2 |
| Sévérité | T-1, T-2 (T est la cible à prédire) |

**Anti-fuite** : Aucune valeur de T+1 (futur) n'entre dans les features.

---

## Impact sur grille pleine (181 413 cellules)

### Cellules observées (5 396 = 3%)

✅ **24 variables disponibles** (y compris historique)  
✅ Performance : **QWK 0.307, Recall 2-3 54%**

### Cellules non observées (175 017 = 97%)

⚠️ **20 variables disponibles** (historique = NaN)  
⚠️ Performance estimée : **QWK ~0.25-0.28, Recall 2-3 ~45-50%**

**Stratégie** : Le modèle généralise les relations pluie/végétation → criquet apprises sur les 3% aux 97% restants.

---

## Variables absentes (hors périmètre)

❌ **ENSO/ONI** (NOAA) — Redondant avec `chirps_anomaly_mean`  
❌ **Humidité sol** (ERA5) — Corrélée avec CHIRPS  
❌ **Altitude/Pente** (SRTM) — Faible variance (plaines)  
❌ **Occupation sol** (MODIS LC) — Homogène (savane)  
❌ **Texture sol** (OpenLandMap) — Pertinence incertaine

---

## Données manquantes

| Variable | Couverture | Cause |
|----------|------------|-------|
| CHIRPS | 97% | Pixels masqués, erreurs GEE |
| NDVI/EVI | 97% | Nuages persistants |
| LST | 74% | Nuages (bloquent infrarouge thermique) |
| Historique | 0.5% | Relevés éparses (5 396 cellules/181 413) |

---

## Collections GEE

```python
CHIRPS      = "UCSB-CHG/CHIRPS/DAILY"      # ~5.5 km, quotidien
MODIS_NDVI  = "MODIS/061/MOD13A2"          # 250 m, 16 jours
MODIS_LST   = "MODIS/061/MOD11A2"          # 1 km, 8 jours
```

**Période** : 2001-2026  
**Extraction** : `src/04b_export_variables_gee.py`  
**Feature engineering** : `src/feature_engineering_05.py`

---

## Documentation complète

Voir : `docs/VARIABLES-ENVIRONNEMENTALES.md`

---

## Exemple : ligne typique

```
Date : 2021-02-01 (Campagne 2020-2021, Décade 15)
Aire : ATM (AIRE_CODE=3)

Pluie      : 85 mm (T), 72 mm (T-1), 46 mm (T-2)
             POP = 3 mois consécutifs ✅
Végétation : NDVI 0.62 (T), 0.58 (T-1), 0.51 (T-2)
Température: 32°C (T), 30°C (T-1), 29°C (T-2)
Historique : Sévérité 2 (T-1), 1 (T-2)

→ Prédiction : Sévérité 3 (grégaire)
```

Si cellule non observée : `severite_lag* = NaN`
