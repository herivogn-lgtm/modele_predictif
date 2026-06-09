# Variables environnementales du modèle prédictif

**Version** : 1.0  
**Modèle retenu** : Régression Ordinale  
**Dernière mise à jour** : 2026-06-09

---

## Vue d'ensemble

Le modèle de prédiction de sévérité-phase du Criquet migrateur malagasy utilise **24 variables prédictives** issues de **4 sources de données principales** :

| Source | Variables | Couverture | Période | Résolution |
|--------|-----------|------------|---------|------------|
| **CHIRPS** (pluviométrie) | 7 | ~97% | 2001-2026 | ~5,5 km / quotidien |
| **MODIS** (végétation) | 6 | ~97% | 2001-2026 | 250 m / 16 jours |
| **MODIS LST** (température) | 3 | ~74% | 2001-2026 | 1 km / 8 jours |
| **Relevés IFVM** (historique) | 4 | ~0.5% | 2001-2026 | Stations éparses |
| **Métadonnées** (spatial/temporel) | 4 | 100% | — | — |

**Total** : 24 variables prédictives

---

## 1. Pluviométrie — CHIRPS (7 variables)

### Source de données

**CHIRPS** : Climate Hazards Group InfraRed Precipitation with Station data  
**Collection GEE** : `UCSB-CHG/CHIRPS/DAILY`  
**Résolution spatiale** : ~5,5 km  
**Résolution temporelle** : Quotidienne  
**Couverture** : Mondiale, 1981-présent  
**Référence** : [CHIRPS Documentation](https://www.chc.ucsb.edu/data/chirps)

### Variables extraites

| Variable | Description | Type | Renseignée |
|----------|-------------|------|------------|
| `chirps_sum_mean` | Pluie décadaire cumulée (mm) à la décade T | Continue | 97.1% |
| `chirps_sum_mean_lag1d` | Pluie décadaire à T-1 (lag 1 décade) | Continue | 97.1% |
| `chirps_sum_mean_lag2d` | Pluie décadaire à T-2 (lag 2 décades) | Continue | 97.1% |
| `chirps_anomaly_mean` | Anomalie par rapport à la climatologie 1981-2010 (mm) | Continue | 97.1% |
| `chirps_cumul_2d` | Cumul roulant sur 2 décades (T + T-1) | Continue | 96.9% |
| `chirps_cumul_3d` | Cumul roulant sur 3 décades (T + T-1 + T-2) | Continue | 96.8% |
| `pop_consecutive` | Mois consécutifs en Plage d'Optimum Pluviométrique | Entier | 100% |

### Variable clé : POP (Plage d'Optimum Pluviométrique)

**`pop_consecutive`** : Nombre de mois consécutifs où la pluie mensuelle est comprise entre **50 et 125 mm/mois**.

**Rationale écologique** (thèse §006, §013) :
- **50-125 mm/mois** : Plage optimale pour le développement du criquet
  - Incubation des oothèques (ponte dans le sol)
  - Disponibilité de végétation herbacée
- **Persistance multi-mois** : Facteur majeur de grégarisation
  - Permet plusieurs générations successives
  - Accumulation de populations

**Calcul** :
1. Agréger les décades → mois (somme des 3 décades)
2. Tester si pluie mensuelle ∈ [50, 125] mm
3. Compteur consécutif par cellule × campagne (remis à 0 à chaque rupture)

**Exemple** :
```
Mois    | Pluie (mm) | En POP ? | pop_consecutive
--------|------------|----------|----------------
Oct     | 45         | Non      | 0
Nov     | 80         | Oui      | 1
Déc     | 110        | Oui      | 2
Jan     | 95         | Oui      | 3  ← Risque élevé
Fév     | 150        | Non      | 0
```

### Anomalie pluviométrique

**`chirps_anomaly_mean`** : Écart entre la pluie décadaire observée et la climatologie de référence (1981-2010) pour la même décade de l'année.

**Interprétation** :
- `> 0` : Pluie supérieure à la normale
- `< 0` : Pluie inférieure à la normale (sécheresse)

### Données manquantes

**~3% de valeurs manquantes** dues à :
- Pixels masqués (eau, nuages persistants)
- Erreurs de téléchargement GEE

---

## 2. Végétation — MODIS (6 variables)

### Source de données

**MODIS MOD13A2** : Vegetation Indices 16-Day L3 Global 250m  
**Collection GEE** : `MODIS/061/MOD13A2`  
**Résolution spatiale** : 250 m  
**Résolution temporelle** : Composite 16 jours  
**Couverture** : Mondiale, 2000-présent  
**Référence** : [MODIS MOD13A2 Documentation](https://lpdaac.usgs.gov/products/mod13a2v061/)

### Variables extraites

| Variable | Description | Type | Renseignée |
|----------|-------------|------|------------|
| `ndvi_mean` | NDVI moyen de la cellule à la décade T | Continue [-1, 1] | 97.3% |
| `ndvi_mean_lag1d` | NDVI à T-1 (lag 1 décade) | Continue [-1, 1] | 97.3% |
| `ndvi_mean_lag2d` | NDVI à T-2 (lag 2 décades) | Continue [-1, 1] | 97.3% |
| `evi_mean` | EVI moyen de la cellule à la décade T | Continue [-1, 1] | 97.3% |
| `evi_mean_lag1d` | EVI à T-1 (lag 1 décade) | Continue [-1, 1] | 97.3% |
| `evi_mean_lag2d` | EVI à T-2 (lag 2 décades) | Continue [-1, 1] | 97.3% |

### NDVI (Normalized Difference Vegetation Index)

**Formule** : `NDVI = (NIR - Red) / (NIR + Red)`

**Interprétation** :
- **-1 à 0** : Eau, nuages, neige, surfaces minérales
- **0 à 0.2** : Sol nu, végétation clairsemée
- **0.2 à 0.5** : Végétation herbacée, cultures
- **0.5 à 0.8** : Végétation dense, forêts
- **> 0.8** : Végétation très dense

**Usage pour le criquet** : Indicateur de disponibilité de nourriture (végétation herbacée).

### EVI (Enhanced Vegetation Index)

**Formule** : `EVI = 2.5 × (NIR - Red) / (NIR + 6×Red - 7.5×Blue + 1)`

**Avantages vs NDVI** :
- Moins sensible à la saturation en zones de végétation dense
- Correction des effets atmosphériques (aérosols)
- Meilleure sensibilité aux variations structurelles de la canopée

**Interprétation similaire au NDVI** mais avec une dynamique étendue.

### Composite 16 jours

MODIS MOD13A2 fournit des **composites 16 jours** = images sans nuages obtenues en sélectionnant les meilleurs pixels sur 16 jours (critère : angle de vue, absence de nuages).

**Agrégation décadaire** : Pour chaque décade (10 jours), on prend le composite MODIS le plus proche temporellement (lead/lag de ±10 jours).

### Données manquantes

**~3% de valeurs manquantes** dues à :
- Nuages persistants en saison des pluies
- Angles de vue extrêmes (bord de tuile)

---

## 3. Température de surface — MODIS LST (3 variables)

### Source de données

**MODIS MOD11A2** : Land Surface Temperature 8-Day L3 Global 1km  
**Collection GEE** : `MODIS/061/MOD11A2`  
**Résolution spatiale** : 1 km  
**Résolution temporelle** : Composite 8 jours  
**Couverture** : Mondiale, 2000-présent  
**Référence** : [MODIS MOD11A2 Documentation](https://lpdaac.usgs.gov/products/mod11a2v061/)

### Variables extraites

| Variable | Description | Type | Renseignée |
|----------|-------------|------|------------|
| `lst_mean` | Température de surface diurne moyenne (K) à T | Continue | 73.9% |
| `lst_mean_lag1d` | LST à T-1 (lag 1 décade) | Continue | 73.9% |
| `lst_mean_lag2d` | LST à T-2 (lag 2 décades) | Continue | 73.9% |

### LST (Land Surface Temperature)

**Mesure** : Température radiative de la surface du sol captée par infrarouge thermique.

**Différence avec température de l'air** :
- LST ≈ température du sol (peut être plus chaude de 10-20°C en journée)
- Température de l'air = mesurée à 2m de hauteur (stations météo)

**Unité** : Kelvin (K)  
**Conversion** : °C = K - 273.15

**Interprétation** :
- **< 290 K** (~17°C) : Froid
- **290-310 K** (17-37°C) : Températures modérées
- **> 310 K** (> 37°C) : Chaud/très chaud

**Usage pour le criquet** : La température influence :
- Le taux de développement (vitesse de maturation)
- La reproduction (seuils thermiques pour la ponte)
- Le comportement (agrégation, migration)

### Composite 8 jours

Composite obtenu en moyennant les acquisitions sur 8 jours (meilleurs pixels sans nuages).

### Données manquantes

**~26% de valeurs manquantes** (couverture 74% seulement) dues à :
- **Nuages** : Le thermique infrarouge ne traverse pas les nuages (contrairement au NDVI qui utilise le proche infrarouge)
- Saison des pluies = nuages persistants → trous dans les données LST
- Fumées, aérosols

**Impact** : LST est la variable environnementale la moins bien renseignée.

---

## 4. Historique acridien — Relevés IFVM (4 variables)

### Source de données

**Base de données IFVM** : `data/2001_2026_Acrido_vf.xls`  
**Observations** : 29 706 relevés terrain (2001-2026)  
**Lacune** : Absence totale de données 2023-2024  
**Cellules observées** : 5 396 cellules (~3% de la grille)

### Variables extraites

| Variable | Description | Type | Renseignée |
|----------|-------------|------|------------|
| `severite_lag1` | Sévérité-phase de la cellule à T-1 | Ordinal [0-3] | 0.5% |
| `severite_lag2` | Sévérité-phase de la cellule à T-2 | Ordinal [0-3] | 0.5% |
| `effort_prospection` | Nombre de relevés dans la cellule | Entier | 0.5% |
| `intensite` | Log de la densité observée (DL/DI) | Continue | 0.5% |

### Sévérité-phase (variable cible et prédicteur)

**Échelle ordinale 0-3** :
- **0** : Absence (aucun criquet observé)
- **1** : Solitaire (individus isolés, comportement non grégaire)
- **2** : Transiens (début de grégarisation, formation de groupes)
- **3** : Grégaire (essaims, comportement grégaire confirmé)

**Usage comme prédicteur** : La sévérité passée (`severite_lag1`, `severite_lag2`) capture la **persistance locale** du phénomène acridien.

### Effort de prospection

**`effort_prospection`** : Nombre de relevés effectués dans la cellule depuis le début de la campagne.

**Usage** : Correction du biais d'échantillonnage (les zones plus prospectées sont mieux connues).

### Intensité

**`intensite`** : Logarithme de la densité observée (larvaire DL ou imaginale DI).

**Calcul** :
```python
intensite = log10(max(DL, DI) + 1)
```

**Interprétation** :
- `0` : Absence
- `1-2` : Densité faible
- `2-3` : Densité modérée
- `> 3` : Densité élevée

### ⚠️ Couverture critique : 0.5%

**Problème majeur** : Ces variables ne sont renseignées que pour **0.5%** des lignes de la table d'entraînement, correspondant aux **5 396 cellules observées** (3% de la grille).

**Impact sur la prédiction grille pleine** :
- **5 396 cellules observées** (3%) : `severite_lag*` disponibles → modèle utilise l'historique local
- **175 017 cellules non observées** (97%) : `severite_lag*=NaN` → modèle s'appuie uniquement sur les variables environnementales

**Stratégie du modèle** :
1. Apprendre la relation entre variables environnementales ET historique (sur les 3% de cellules observées)
2. Généraliser sur les 97% de cellules non observées en utilisant uniquement les variables environnementales

---

## 5. Métadonnées spatial/temporel (4 variables)

### Variables

| Variable | Description | Type | Renseignée |
|----------|-------------|------|------------|
| `AIRE_CODE` | Code de l'aire grégarigène (1-4) | Catégoriel | 100% |
| `year` | Année civile | Entier | 100% |
| `month` | Mois (1-12) | Entier | 100% |
| `decade_part` | Position dans le mois (1, 2, 3) | Entier | 100% |

### AIRE_CODE (prédicteur spatial)

**Codes des 4 aires complémentaires** :
- **1** : AGT (Aire Grégarigène Transitoire) — Zomandao, Makay, Morondava
- **2** : AMI (Aire de Multiplication Initiale) — démarrage de la reproduction
- **3** : ATM (Aire Transitoire de Multiplication) — plaines Androka, Befandriana Sud, Manombo
- **4** : AD (Aire de Densation) — concentration des populations

**Usage** : Capturer les différences écologiques et climatiques entre aires (proxy géographique).

### Variables temporelles

**`year`, `month`, `decade_part`** : Capturent la saisonnalité et les tendances inter-annuelles.

**Usage** :
- Cycle saisonnier annuel (campagne octobre-septembre)
- Tendances climatiques à long terme
- Interactions avec les autres variables (ex : NDVI dépend du mois)

---

## Résumé de couverture

### Excellent (>90%)

✅ **Pluviométrie (CHIRPS)** : 97%  
✅ **Végétation (NDVI/EVI)** : 97%  
✅ **Métadonnées** : 100%

### Acceptable (>70%)

⚠️ **Température (LST)** : 74%

### Critique (<5%)

❌ **Historique acridien** : 0.5% (uniquement cellules observées)

---

## Variables absentes (hors périmètre)

Les variables suivantes ont été **retirées du périmètre** après analyse initiale :

| Variable | Source | Raison de l'exclusion |
|----------|--------|-----------------------|
| **ENSO/ONI** | NOAA | Proxy des anomalies pluviométriques (redondant avec `chirps_anomaly_mean`) |
| **Humidité du sol** | ERA5 | Complexité d'extraction, corrélation avec CHIRPS |
| **Altitude/Pente** | SRTM DEM | Variance spatiale faible dans l'aire grégarigène (plaines) |
| **Occupation du sol** | MODIS Land Cover | Homogénéité (savane herbacée dominante) |
| **Texture du sol** | OpenLandMap | Disponibilité limitée, pertinence écologique incertaine |

**Décision de simplification** : Concentrer le modèle sur les 3 variables environnementales majeures (pluie, végétation, température) pour faciliter l'interprétation et la maintenance.

---

## Lags temporels

### Principe

Le modèle prédit la sévérité à la décade **T+1** en utilisant des variables **passées** (≤ T). Les **lags** décalent les variables dans le passé.

### Profondeur des lags : 2 décades

| Variable | Valeurs disponibles |
|----------|---------------------|
| Pluie, NDVI, EVI, LST | T, T-1, T-2 |
| Sévérité historique | T-1, T-2 (pas T, car c'est la cible) |

**Rationale** : 2 décades ≈ 20 jours de fenêtre d'observation, suffisant pour capturer :
- Dynamique de la végétation post-pluie (réponse en ~10-15 jours)
- Persistance des conditions favorables

### Anti-fuite temporelle

**Règle stricte** : Aucune variable de la décade **T+1** (futur) n'entre dans les features. Seules les valeurs ≤ T sont utilisées.

**Vérification** : Voir `src/feature_engineering_05.py` lignes 86-112 (garantit que `shift(k)` ne regarde que le passé).

---

## Performance du modèle par type de variable

### Test d'ablation (hypothétique)

| Variables utilisées | QWK | Recall 2-3 |
|---------------------|-----|------------|
| **Toutes (24 vars)** | **0.307** | **54.18%** |
| Sans historique acridien | ~0.28 (estimé) | ~48% (estimé) |
| Sans température (LST) | ~0.30 (estimé) | ~53% (estimé) |
| Sans végétation | ~0.22 (estimé) | ~40% (estimé) |
| Sans pluviométrie | ~0.18 (estimé) | ~35% (estimé) |

**Note** : Test d'ablation non effectué, valeurs estimées sur l'importance des variables.

### Variables les plus importantes (hypothèse)

D'après la littérature acridologique :
1. **`pop_consecutive`** : Plage d'Optimum Pluviométrique (facteur critique)
2. **`ndvi_mean`** : Disponibilité de nourriture
3. **`chirps_sum_mean`** : Pluie directe
4. **`severite_lag1`** : Persistance locale (pour cellules observées)
5. **`AIRE_CODE`** : Différences régionales

**Pour obtenir l'importance réelle** : Analyser le modèle CatBoost (feature importance intégrée) ou effectuer un test d'ablation.

---

## Impact sur la prédiction grille pleine

### Scénario 1 : Cellules observées (5 396 cellules, 3%)

✅ **Toutes les 24 variables disponibles**  
✅ Historique acridien (`severite_lag*`) renseigné  
✅ Performance attendue = **QWK 0.307**, **Recall 2-3 54%**

### Scénario 2 : Cellules non observées (175 017 cellules, 97%)

⚠️ **Seulement 20 variables disponibles** (4 variables historiques = NaN)  
❌ Absence d'historique local (`severite_lag1`, `severite_lag2`, `effort_prospection`, `intensite`)  
✅ Variables environnementales présentes (pluie, végétation, température)  
❓ **Performance attendue** : Légèrement inférieure (pas de signal de persistance locale)

**Estimation conservative** :
- QWK : ~0.25-0.28 (au lieu de 0.307)
- Recall 2-3 : ~45-50% (au lieu de 54%)

### Stratégie d'atténuation

1. **Le modèle apprend** sur les 5 396 cellules observées comment les variables environnementales seules prédisent la sévérité
2. **Généralisation spatiale** : Hypothèse que les relations pluie/végétation → criquet sont transférables aux cellules voisines
3. **Validation future** : Comparer les prédictions grille pleine avec de nouveaux relevés terrain

---

## Références

### Collections Google Earth Engine

- **CHIRPS** : `UCSB-CHG/CHIRPS/DAILY`  
  [Documentation](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY)

- **MODIS MOD13A2** (NDVI/EVI) : `MODIS/061/MOD13A2`  
  [Documentation](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A2)

- **MODIS MOD11A2** (LST) : `MODIS/061/MOD11A2`  
  [Documentation](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A2)

### Pipelines

- **Extraction GEE** : `src/04b_export_variables_gee.py` + `docs/pipelines/04-extraction-gee.md`
- **Feature engineering** : `src/feature_engineering_05.py` + `docs/pipelines/05-feature-engineering.md`
- **Table d'entraînement** : `src/construction_table_06.py` + `docs/pipelines/06-construction-table.md`

### Littérature

- **Lecoq et al. 1979** : Voies de déplacement du Criquet migrateur malagasy
- **Randrianarijaona 2026** : Thèse doctorale (système de prévision acridien)
- **Manuel de lutte préventive** : EDGRND

---

## Annexe : Exemple de ligne de données

Voici un exemple de ligne de la table d'entraînement (`06_table_entrainement_unifiee.parquet`) :

```
cell_id               : "1234567"
campagne_calc         : "2020-2021"
campagne_decade       : 15
date_start            : 2021-02-01
AIRE_CODE             : 3 (ATM)
year                  : 2021
month                 : 2
decade_part           : 1

# Pluie
chirps_sum_mean       : 85.3 mm
chirps_sum_mean_lag1d : 72.1 mm
chirps_sum_mean_lag2d : 45.6 mm
chirps_anomaly_mean   : 12.5 mm
chirps_cumul_2d       : 157.4 mm
chirps_cumul_3d       : 203.0 mm
pop_consecutive       : 3 mois

# Végétation
ndvi_mean             : 0.62
ndvi_mean_lag1d       : 0.58
ndvi_mean_lag2d       : 0.51
evi_mean              : 0.45
evi_mean_lag1d        : 0.42
evi_mean_lag2d        : 0.38

# Température
lst_mean              : 305.2 K (~32°C)
lst_mean_lag1d        : 303.8 K (~30°C)
lst_mean_lag2d        : 302.1 K (~29°C)

# Historique acridien (si cellule observée)
severite_lag1         : 2 (transiens à T-1)
severite_lag2         : 1 (solitaire à T-2)
effort_prospection    : 5 relevés
intensite             : 2.3 (densité modérée)

# Cible (à prédire)
severite              : 3 (grégaire à T)
```

Si la cellule n'a jamais été observée, `severite_lag*`, `effort_prospection` et `intensite` sont `NaN`.
