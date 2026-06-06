# Runbook — #04 Extraction des variables environnementales GEE

Pipeline : `src/04_extraction_variables_gee.py`  
Sortie : `data/processed/04_variables_environnementales.parquet`  
Durée estimée : 2–3 h (run complet 2001–2026)

---

## Prérequis

### Compte Google Earth Engine
1. Créer un compte sur [earthengine.google.com](https://earthengine.google.com)
2. Créer un projet Google Cloud associé (onglet **Projects** dans la console EE)
3. Activer l'API Earth Engine sur ce projet Cloud

### Environnement Python
```bash
pip install earthengine-api geopandas pandas pyarrow requests
```

Versions testées : `earthengine-api >= 0.1.390`, `geopandas >= 0.14`, `pandas >= 2.0`.

### Données requises
- `data/region_naturelle/region_naturelle.shp` — doit exister (90 polygones, EPSG:4326)

---

## Configuration (une seule fois)

**1. Renseigner le projet GEE**

Ouvrir `src/config_gee.py` et remplacer :
```python
GEE_PROJECT_ID = "your-gee-project-id"   # ← mettre l'ID du projet Cloud
```

**2. Authentifier le compte GEE**

```bash
python -c "import ee; ee.Authenticate()"
```

Un navigateur s'ouvre. Se connecter avec le compte associé au projet. Les credentials sont sauvegardés localement (~/.config/earthengine/credentials) — cette étape n'est faite qu'une fois par machine.

---

## Exécution

### Étape 1 — Test d'intégration (5–10 min)

Valide que chaque extracteur fonctionne sur 1 région × 1 décade avant de lancer le run complet.

```bash
python src/04_extraction_variables_gee.py --test-only
```

Sortie attendue :
```
GEE initialisé.
90 régions chargées.

=== Test d'intégration : région 1, janvier 2010 D1 ===
  CHIRPS somme : OK
  NDVI/EVI     : OK
  LST          : OK
  ERA5 sol     : OK
  DEM SRTM     : OK
  Texture sol  : OK
  ENSO/ONI     : OK
=== Test d'intégration réussi ===
```

Si une assertion échoue, voir la section **Dépannage** ci-dessous.

### Étape 2 — Baseline CHIRPS (30–45 min, une seule fois)

La première exécution calcule la baseline pluviométrique 1981–2010 (36 décades × 90 régions) et la met en cache dans `data/processed/04_chirps_baseline_cache.parquet`. Les runs suivants utilisent ce cache.

Ce calcul se déclenche automatiquement au lancement du run complet ou du run partiel.

### Étape 3 — Run de validation sur une année (10–15 min)

```bash
python src/04_extraction_variables_gee.py --years 2010
```

Vérifie que la boucle complète fonctionne. Inspecter la sortie :
```bash
python - <<'EOF'
import pandas as pd
df = pd.read_parquet("data/processed/04_variables_environnementales.parquet")
print(df.shape)
print(df[["ndvi_mean","lst_mean","chirps_sum_mean"]].describe())
print("NaN NDVI :", df["ndvi_mean"].isna().mean())
EOF
```

### Étape 4 — Run complet 2001–2026 (2–3 h)

```bash
python src/04_extraction_variables_gee.py
```

Le script affiche sa progression décade par décade :
```
[1/750] 2001-02 décade 01 (2001-10-01 → 2001-10-10) OK
[2/750] 2001-02 décade 02 (2001-10-11 → 2001-10-20) OK
...
```

**Conseil** : lancer dans un terminal détaché (`nohup` ou session `tmux`/`screen`) pour éviter les interruptions réseau.

```bash
nohup python src/04_extraction_variables_gee.py > logs/04_gee.log 2>&1 &
tail -f logs/04_gee.log
```

---

## Vérification de la sortie

```bash
python - <<'EOF'
import pandas as pd

df = pd.read_parquet("data/processed/04_variables_environnementales.parquet")

print("=== Dimensions ===")
print(f"  {df.shape[0]} lignes × {df.shape[1]} colonnes")
print(f"  Campagnes : {df['campaign'].nunique()} ({df['campaign'].min()} → {df['campaign'].max()})")
print(f"  Régions   : {df['region_id'].nunique()} (attendu : 90)")

print("\n=== Taux de NaN ===")
nan_cols = ["chirps_sum_mean","chirps_anomaly_mean","ndvi_mean","evi_mean",
            "lst_mean","soil_moisture_mean","enso_oni"]
for col in nan_cols:
    if col in df.columns:
        print(f"  {col:30s} {df[col].isna().mean():.1%}")

print("\n=== Plages physiques ===")
checks = {
    "NDVI"           : ("ndvi_mean",          -1,   1),
    "EVI"            : ("evi_mean",            -1,   1),
    "LST (K)"        : ("lst_mean",           200, 400),
    "CHIRPS (mm)"    : ("chirps_sum_mean",      0, 999),
    "Humidité sol"   : ("soil_moisture_mean",   0,   1),
    "Altitude (m)"   : ("dem_mean",             0,3000),
}
for label, (col, lo, hi) in checks.items():
    if col in df.columns:
        v = df[col].dropna()
        ok = v.between(lo, hi).all()
        print(f"  {label:20s} [{v.min():.2f}, {v.max():.2f}]  {'OK' if ok else 'ATTENTION'}")
EOF
```

Critères d'acceptation :
- Lignes ≈ 67 500 (90 × ~750 décades)
- Régions = 90
- NDVI ∈ [-1, 1], LST ∈ [200, 400] K, CHIRPS ≥ 0
- Taux NaN NDVI < 40 % (couverture nuageuse Madagascar acceptable)

---

## Reprise après interruption

Le script ne reprend pas automatiquement là où il s'est arrêté. Pour reprendre sur les années manquantes :

```bash
# Exemple : le run s'est arrêté après 2015
python src/04_extraction_variables_gee.py --years $(seq 2016 2026 | tr '\n' ' ')
```

Fusionner les Parquets partiels si besoin :
```python
import pandas as pd, glob
parts = [pd.read_parquet(f) for f in sorted(glob.glob("data/processed/04_*.parquet"))]
df = pd.concat(parts).drop_duplicates(["region_id","date_start"]).sort_values(["region_id","date_start"])
df.to_parquet("data/processed/04_variables_environnementales.parquet", index=False)
```

---

## Dépannage

| Erreur | Cause probable | Action |
|---|---|---|
| `EEException: Quota exceeded` | Rate limit GEE dépassé | Le retry exponentiel gère automatiquement ; si persistant, attendre 1h et relancer |
| `EEException: Image.load: Asset ... not found` | Collection GEE indisponible ou ID incorrect | Vérifier l'ID dans `src/config_gee.py` ; consulter le [catalogue GEE](https://developers.google.com/earth-engine/datasets) |
| `AssertionError: rn_num doit être unique` | Doublons dans le shapefile | Inspecter `data/region_naturelle/region_naturelle.shp` avec geopandas |
| `requests.HTTPError` sur ENSO | NOAA CPC temporairement indisponible | Relancer plus tard ; l'ONI n'est pas bloquant pour la suite |
| `FileNotFoundError: region_naturelle.shp` | Chemin incorrect | Vérifier que `data/region_naturelle/` contient les 4 fichiers (.shp, .dbf, .shx, .prj) |
| NDVI hors [-1, 1] | Facteur d'échelle non appliqué | Vérifier que `multiply(0.0001)` est bien appelé dans `extract_ndvi_evi()` |
| LST en valeurs > 20 000 | Facteur d'échelle non appliqué | Vérifier que `multiply(0.02)` est bien appelé dans `extract_lst()` |
| Baseline CHIRPS recalculée à chaque run | Cache corrompu ou absent | Supprimer `data/processed/04_chirps_baseline_cache.parquet` et relancer |

---

## Étape suivante

Une fois le Parquet validé, lancer l'issue **#05 — Feature engineering** :
```bash
python src/05_feature_engineering.py
```

Le Parquet `04_variables_environnementales.parquet` est l'unique entrée requise.
