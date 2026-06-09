# Flux de données — Variables environnementales

**Pipeline de bout en bout** : Collecte → Extraction → Feature engineering → Modèle → Prédiction

---

## Vue d'ensemble du pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SOURCES DE DONNÉES (Cloud)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ☔ CHIRPS                🌱 MODIS MOD13A2        🌡️ MODIS MOD11A2     │
│  (Pluviométrie)          (NDVI/EVI)              (LST)                  │
│  ~5.5 km / quotidien     250 m / 16 jours        1 km / 8 jours        │
│                                                                          │
│  🦗 Relevés IFVM                                                        │
│  (Terrain, stations éparses)                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                   #01 GRILLE 1 KM (preprocessing)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Génère grille régulière 1 km × 1 km dans aire grégarigène             │
│  ✓ 181 413 cellules (centroïdes)                                       │
│  ✓ Clip strict aux 12 polygones                                        │
│  📁 data/processed/01_grille_1km.parquet                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│              #04b EXTRACTION GEE (Google Earth Engine)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Échantillonne collections GEE aux centroïdes de la grille             │
│  ✓ sampleRegions(centroïdes, décades)                                  │
│  ✓ Agrégation temporelle : composite → décade (10 jours)               │
│  ✓ Export batch (39 tâches × ~14k cellules)                            │
│                                                                          │
│  Variables brutes extraites :                                           │
│    • chirps_sum_mean (pluie décadaire, mm)                             │
│    • ndvi_mean, evi_mean (indices végétation)                          │
│    • lst_mean (température surface, K)                                 │
│    • chirps_baseline_mean (climatologie 1981-2010)                     │
│                                                                          │
│  📁 data/processed/04_variables_environnementales/                      │
│     181 413 cellules × ~30 décades/an × 26 ans = ~140 M lignes         │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                #03 LABELS (preprocessing terrain)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Agrège relevés terrain → (cell_id × décade)                           │
│  ✓ Sévérité-phase max par cellule×décade                               │
│  ✓ Intensité (log densité)                                             │
│  ✓ Effort de prospection                                               │
│                                                                          │
│  📁 data/processed/03_labels_cellule_decade.parquet                     │
│     5 396 cellules observées × ~30 décades/an × 26 ans                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│              #05 FEATURE ENGINEERING (transformations)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Calcule features dérivées depuis variables brutes                     │
│                                                                          │
│  Transformations appliquées :                                           │
│  1️⃣ POP consécutif                                                     │
│     • Agrège décades → mois (somme pluie)                              │
│     • Teste si mois ∈ [50, 125] mm                                     │
│     • Compteur consécutif par cellule × campagne                       │
│                                                                          │
│  2️⃣ Lags temporels (D-1, D-2)                                          │
│     • chirps_sum_mean_lag1d = chirps_sum_mean.shift(1)                 │
│     • ndvi_mean_lag1d = ndvi_mean.shift(1)                             │
│     • etc. (toutes variables environnementales)                        │
│                                                                          │
│  3️⃣ Cumuls roulants                                                    │
│     • chirps_cumul_2d = rolling(2).sum()                               │
│     • chirps_cumul_3d = rolling(3).sum()                               │
│                                                                          │
│  4️⃣ Anomalie CHIRPS                                                    │
│     • chirps_anomaly = chirps_sum - chirps_baseline[mois, décade]      │
│                                                                          │
│  5️⃣ Sévérité historique (si labels disponibles)                        │
│     • severite_lag1 = severite.shift(1)                                │
│     • severite_lag2 = severite.shift(2)                                │
│                                                                          │
│  📁 data/processed/05_features_engineering.parquet                      │
│     Même taille que #04 + colonnes dérivées                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│          #06 TABLE D'ENTRAÎNEMENT (jointure features + labels)          │
├─────────────────────────────────────────────────────────────────────────┤
│  Jointure LEFT : features (#05) ← labels (#03)                         │
│  ✓ Toutes les cellules conservées (181 413)                            │
│  ✓ Labels = NaN pour cellules non observées                            │
│  ✓ Colonne a_predire : TRUE si label disponible                        │
│                                                                          │
│  📁 data/processed/06_table_entrainement_unifiee.parquet                │
│     32 colonnes (24 features + 8 métadonnées/cibles)                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                  #07 ENTRAÎNEMENT (benchmark modèles)                   │
├─────────────────────────────────────────────────────────────────────────┤
│  Entraîne 5 modèles sur cellules observées (a_predire=TRUE)            │
│  ✓ Régression ordinale (mord.LASSoclass)                               │
│  ✓ CatBoost, LightGBM, XGBoost, Random Forest                          │
│  ✓ Validation : 21 folds (leave-one-campaign-out)                      │
│  ✓ Métriques : QWK (ordinal), Recall 2-3, AUC binaire                  │
│                                                                          │
│  Sélection : select_robust (Recall 2-3 ≥ baseline, QWK max)            │
│  → Retenu : Régression Ordinale (QWK 0.307, Recall 54%)                │
│                                                                          │
│  📁 data/processed/07_modele_retenu.txt                                 │
│  📁 data/processed/07_benchmark_resume.csv                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                  #09 PRÉDICTION (carte opérationnelle)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Applique modèle retenu sur TOUTES les cellules (181 413)              │
│  ✓ Prédit sévérité-phase [0-3] pour une décade donnée                  │
│  ✓ Génère carte : GeoJSON + GeoTIFF + PNG                              │
│                                                                          │
│  Comportement selon cellule :                                           │
│    • Cellules observées (3%) : utilise toutes les 24 variables         │
│    • Cellules non obs. (97%) : 4 variables historiques = NaN           │
│                                                                          │
│  📁 data/outputs/09_carte_severite_decade.csv                           │
│  📁 data/outputs/09_carte_severite_decade.geojson                       │
│  📁 data/outputs/09_carte_severite_decade.tif                           │
│  📁 data/outputs/09_carte_severite_decade.png                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Détail du feature engineering (#05)

### 1. Calcul POP consécutif

```
Entrée : chirps_sum_mean (décadaire)
         ↓
┌────────────────────────────────────┐
│  Agrégation décades → mois         │
│  chirps_monthly = sum(D1 + D2 + D3)│
└────────────────────────────────────┘
         ↓
┌────────────────────────────────────┐
│  Test POP : 50 ≤ mm ≤ 125 ?        │
│  in_pop = True/False               │
└────────────────────────────────────┘
         ↓
┌────────────────────────────────────┐
│  Compteur consécutif                │
│  par cellule × campagne             │
│  Réinitialise à 0 si rupture        │
└────────────────────────────────────┘
         ↓
Sortie : pop_consecutive (mois)

Exemple :
Mois   | Pluie | POP? | Consécutif
Oct    | 45    | Non  | 0
Nov    | 80    | Oui  | 1
Déc    | 110   | Oui  | 2
Jan    | 95    | Oui  | 3  ← Risque élevé
Fév    | 150   | Non  | 0
```

### 2. Lags temporels (shift)

```
Décade :  T-2      T-1       T      T+1
          ↓        ↓         ↓       ↓
NDVI    : 0.51 ── 0.58 ── 0.62 ── 0.65
                    ↓         ↓
                    │         └─→ ndvi_mean (prédicteur)
                    └───────────→ ndvi_mean_lag1d (prédicteur)
          └───────────────────→ ndvi_mean_lag2d (prédicteur)

⚠️ NDVI à T+1 (0.65) n'est JAMAIS utilisé (anti-fuite temporelle)
```

### 3. Cumuls roulants

```
Décade :       T-2    T-1     T
               ↓      ↓       ↓
Pluie (mm)  : 45  ── 72  ── 85
                      ↓       ↓
                      └───┐   │
                          │   │
chirps_cumul_2d :    72+85 = 157  (T + T-1)
chirps_cumul_3d :  45+72+85 = 202  (T + T-1 + T-2)
```

---

## Couverture des variables par cellule

### Cellule observée (ex : 5% de la grille)

```
┌─────────────────────────────────────────────┐
│ cell_id: "1234567"                          │
│ AIRE_CODE: 3 (ATM)                          │
│ Campagne: 2020-2021, Décade 15              │
├─────────────────────────────────────────────┤
│ ☔ Pluviométrie (CHIRPS)           ✅ 100%  │
│   chirps_sum_mean        : 85.3 mm          │
│   chirps_sum_mean_lag1d  : 72.1 mm          │
│   chirps_sum_mean_lag2d  : 45.6 mm          │
│   chirps_anomaly_mean    : 12.5 mm          │
│   chirps_cumul_2d        : 157.4 mm         │
│   chirps_cumul_3d        : 203.0 mm         │
│   pop_consecutive        : 3 mois           │
├─────────────────────────────────────────────┤
│ 🌱 Végétation (MODIS)              ✅ 100%  │
│   ndvi_mean              : 0.62             │
│   ndvi_mean_lag1d        : 0.58             │
│   evi_mean               : 0.45             │
│   (+ lags)                                  │
├─────────────────────────────────────────────┤
│ 🌡️ Température (MODIS LST)        ✅ 100%  │
│   lst_mean               : 305 K (~32°C)    │
│   lst_mean_lag1d         : 304 K (~31°C)    │
│   (+ lags)                                  │
├─────────────────────────────────────────────┤
│ 🦗 Historique acridien             ✅ 100%  │
│   severite_lag1          : 2 (transiens)    │
│   severite_lag2          : 1 (solitaire)    │
│   effort_prospection     : 5 relevés        │
│   intensite              : 2.3              │
├─────────────────────────────────────────────┤
│ → Prédiction avec 24 features               │
│ → Performance : QWK 0.307, Recall 54%       │
└─────────────────────────────────────────────┘
```

### Cellule non observée (ex : 95% de la grille)

```
┌─────────────────────────────────────────────┐
│ cell_id: "9876543"                          │
│ AIRE_CODE: 2 (AMI)                          │
│ Campagne: 2020-2021, Décade 15              │
├─────────────────────────────────────────────┤
│ ☔ Pluviométrie (CHIRPS)           ✅ 100%  │
│   chirps_sum_mean        : 92.1 mm          │
│   chirps_sum_mean_lag1d  : 68.5 mm          │
│   (etc.)                                    │
├─────────────────────────────────────────────┤
│ 🌱 Végétation (MODIS)              ✅ 100%  │
│   ndvi_mean              : 0.58             │
│   ndvi_mean_lag1d        : 0.54             │
│   (etc.)                                    │
├─────────────────────────────────────────────┤
│ 🌡️ Température (MODIS LST)        ✅ 100%  │
│   lst_mean               : 308 K (~35°C)    │
│   (etc.)                                    │
├─────────────────────────────────────────────┤
│ 🦗 Historique acridien             ❌ NaN   │
│   severite_lag1          : NaN              │
│   severite_lag2          : NaN              │
│   effort_prospection     : NaN              │
│   intensite              : NaN              │
├─────────────────────────────────────────────┤
│ → Prédiction avec 20 features               │
│ → Performance estimée : QWK ~0.25-0.28      │
└─────────────────────────────────────────────┘
```

---

## Résolution spatiale des sources

```
Résolution :  5.5 km        1 km         250 m
              ↓             ↓            ↓
           ┌─────┐       ┌───┐       ┌─┐
CHIRPS     │     │       │   │       │ │
           │     │       │   │       │ │
           └─────┘       └───┘       └─┘

           ┌─────┐       ┌───┐       ┌─┐
MODIS LST  │     │       │█████████████│
           │     │       │█████████████│
           └─────┘       └───┘       └─┘

           ┌─────┐       ┌───┐       ┌─┐
MODIS NDVI │     │       │   │       │█│
           │     │       │   │       │█│
           └─────┘       └───┘       └─┘

Grille cible : 1 km × 1 km
               ┌───┐
               │ ● │  ← centroïde
               └───┘

Méthode d'agrégation : sampleRegions(centroïdes) → moyenne
```

---

## Temporalité des composites

```
Timeline :  |────────────────────────────────────────────|
            Jan                                        Déc

CHIRPS      |══|══|══|  (décades 10j, quotidien agrégé)
            D1 D2 D3

MODIS       |════════════════|════════════════|  (16j)
NDVI/EVI    Composite 1       Composite 2

MODIS       |════════|════════|════════|  (8j)
LST         Comp 1    Comp 2   Comp 3

Alignement GEE :
  Pour chaque décade, chercher le composite le plus proche
  (fenêtre ± lead/lag jours, ex : ±10j)
```

---

## Anti-fuite temporelle

```
Timeline :    T-2      T-1       T      T+1
              ↓        ↓         ↓       ↓
Variables   : ✅      ✅       ✅      ❌
prédictives   OK      OK       OK      INTERDIT

Cible       : ──────────────→  🎯 severite (à prédire)

Règle : Prédire T+1 avec variables ≤ T
        (forecast, pas nowcast)

Implémentation : shift(k) avec k > 0
                groupby(cell_id) empêche fuite spatiale
```

---

## Documentation complète

- **Variables détaillées** : `docs/VARIABLES-ENVIRONNEMENTALES.md`
- **Référence rapide** : `docs/VARIABLES-REFERENCE-RAPIDE.md`
- **Pipelines** : `docs/pipelines/04-extraction-gee.md`, `05-feature-engineering.md`, `06-construction-table.md`
