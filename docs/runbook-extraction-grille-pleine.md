# Runbook — Extraction GEE grille pleine et prédiction opérationnelle mensuelle

**Objectif** : Guide opérationnel pour extraire les variables environnementales sur la **grille complète (181 413 cellules)** et générer des cartes de prédiction mensuelles.

**Cas d'usage** : Prédiction opérationnelle du mois en cours (ex : juin 2026) sur toute l'aire grégarigène.

---

## Contexte

### Architecture des données

| Population | Cellules | Couverture temporelle | Usage |
|------------|----------|----------------------|-------|
| **Cellules observées** | 5 396 | 2001-2026 (historique complet) | Entraînement du modèle #07 |
| **Grille complète** | 181 413 | Mois récents (extraction incrémentale) | Prédiction opérationnelle #09 |

**Stratégie de fusion** : Les nouvelles extractions (grille complète × mois récents) sont **fusionnées automatiquement** avec l'historique existant via dédoublonnage sur `(cell_id, date_start)`.

### Prérequis

- ✓ Baseline CHIRPS déjà extraite (~179 646 cellules)
- ✓ Historique 2001-2026 pour cellules observées (5 396 cellules)
- ✓ Compte GEE authentifié : `./.venv/bin/python -c "import ee; ee.Authenticate()"`
- ✓ Espace Drive : ~2-3 GB pour les CSV d'une extraction mensuelle

---

## Workflow opérationnel mensuel

### Étape 1 : Extraction GEE (submit)

**Commande pour le mois en cours** (exemple : juin 2026) :

```bash
# Avec buffer automatique (2 décades) pour les lags
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --month 2026-06 \
  --no-baseline

# OU avec buffer personnalisé (3 décades)
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --month 2026-06 \
  --buffer 3 \
  --no-baseline
```

**Ce qui est extrait** :
- `--month 2026-06` = juin 2026 (décades 16-18)
- `--buffer 2` (défaut) = ajoute 2 décades avant (décades 14-15 = mai D2-D3)
- **Total** : décades 14-18 (5 décades) × 181 413 cellules = ~900 000 lignes
- **Tâches GEE** : 39 tâches dynamiques (3 sources × 1 lot × 13 tuiles)
- **Durée estimée** : 10-20 minutes (tâches parallèles)

**Variante : extraction par plage de décades (contrôle fin)** :

```bash
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --decades 2026-14:2026-18 \
  --no-baseline
```

---

### Étape 2 : Suivi des tâches (status)

```bash
./.venv/bin/python src/04b_export_variables_gee.py status
```

**Sortie attendue** :
```
Tâches actives (préfixe v04_*) :
  v04_CHIRPS_y2026_t000       : RUNNING
  v04_NDVI_y2026_t000         : COMPLETED
  ...
  Total : 12 COMPLETED, 3 RUNNING, 0 FAILED
```

**Attendre** que toutes les tâches soient `COMPLETED`.

---

### Étape 3 : Téléchargement des CSV depuis Drive

1. Ouvrir Google Drive : [https://drive.google.com](https://drive.google.com)
2. Naviguer vers le dossier `ee_exports_locusta_v04/`
3. Télécharger **tous les nouveaux CSV** (préfixe `v04_*_y2026_t*.csv`)
4. Déplacer les CSV dans : `data/processed/04_exports_drive/`

**Astuce** : Les CSV peuvent être téléchargés en batch (sélectionner → clic droit → Télécharger).

---

### Étape 4 : Assemblage des CSV → Parquet (assemble)

```bash
./.venv/bin/python src/04b_export_variables_gee.py assemble \
  --cells all \
  --month 2026-06
```

**Comportement** :
- Lit **tous** les CSV `v04_*_t*.csv` dans `04_exports_drive/` (historique + nouveaux)
- Fusionne avec les parquets existants dans `04_variables_environnementales/`
- **Dédoublonnage automatique** : en cas de doublon `(cell_id, date_start)`, garde la version la plus récente
- Sortie : `data/processed/04_variables_environnementales/part-*.parquet` (mis à jour)

**Durée estimée** : 5-10 minutes

**Vérification** :

```bash
./.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/processed/04_variables_environnementales/')
print(f'Lignes totales : {len(df):,}')
print(f'Cellules uniques : {df.cell_id.nunique():,}')
print(f'Période : {df.date_start.min()} → {df.date_start.max()}')
print(f'\nJuin 2026 :')
june = df[(df.date_start >= '2026-06-01') & (df.date_start < '2026-07-01')]
print(f'  {len(june):,} lignes, {june.cell_id.nunique():,} cellules')
"
```

**Attendu pour juin 2026** :
- ~544 239 lignes (181 413 cellules × 3 décades)
- Si moins : vérifier que tous les CSV ont été téléchargés

---

### Étape 5 : Feature engineering (#05)

```bash
./.venv/bin/python src/feature_engineering_05.py
```

**Sortie** : `data/processed/05_features_engineering.parquet`

**Durée estimée** : 2-5 minutes

**Vérification RAM** : Le fichier `05_features_engineering.parquet` peut atteindre ~5 GB avec 181k cellules × historique complet. Surveiller la consommation mémoire.

---

### Étape 6 : Table d'entraînement unifiée (#06)

```bash
./.venv/bin/python src/construction_table_06.py
```

**Sortie** : `data/processed/06_table_entrainement_unifiee.parquet`

**Durée estimée** : 3-8 minutes

---

### Étape 7 : Génération de la carte de prédiction (#09)

**Prédire juin 2026 (une décade spécifique)** :

```bash
./.venv/bin/python src/sorties_operationnelles_09.py \
  --modele data/processed/07_modele_retenu.txt \
  --campagne 2025-2026 \
  --decade 18
```

**Sortie** :
- `data/outputs/09_carte_severite_decade.csv` (table prédictions)
- `data/outputs/09_carte_severite_decade.geojson` (carte vecteur)
- `data/outputs/09_carte_severite_decade.tif` (raster GeoTIFF)
- `data/outputs/09_carte_severite_decade.png` (visualisation)

**Prédire toutes les décades de juin** :

```bash
for decade in 16 17 18; do
  ./.venv/bin/python src/sorties_operationnelles_09.py \
    --modele data/processed/07_modele_retenu.txt \
    --campagne 2025-2026 \
    --decade $decade
  mv data/outputs/09_carte_severite_decade.png \
     data/outputs/09_carte_2026_D${decade}.png
done
```

---

## Extraction initiale (première fois)

**Objectif** : Extraire la grille complète pour la première fois (toutes les cellules, mois récents).

### Option A : Extraction d'une campagne complète

Pour prédire toute la campagne 2025-2026 (octobre 2025 → septembre 2026) :

```bash
# Extraction décades -1 à 36 (fin sept 2025 → fin sept 2026)
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --decades 2025-34:2026-36 \
  --no-baseline

# Durée : ~30-45 min (tâches parallèles)
# Tâches : ~130 tâches dynamiques (3 sources × 3 lots × 13 tuiles)
```

### Option B : Extraction de l'année en cours

```bash
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --years 2026 \
  --no-baseline

# Durée : ~30-45 min
# Tâches : 39 tâches (36 décades de 2026)
```

### Option C : Relancer la baseline complète (si nécessaire)

Si la baseline existante (~179 646 cellules) ne couvre pas les 181 413 cellules :

```bash
# Relancer baseline uniquement (sans --no-baseline)
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --years 2026 \
  --no-dynamic

# Durée : ~10-15 min (13 tâches baseline)
```

---

## Dépannage

### Problème : Tâches GEE échouées (FAILED)

**Diagnostic** :

```bash
./.venv/bin/python src/04b_export_variables_gee.py status
```

**Solutions** :
1. **Quota dépassé** : Attendre 24h ou upgrader le compte GEE
2. **Erreur temporaire** : Relancer les tâches échouées (même commande `submit`)
3. **Annuler toutes les tâches** :
   ```bash
   ./.venv/bin/python src/04b_export_variables_gee.py cancel
   ```

---

### Problème : CSV manquants après téléchargement

**Diagnostic** : Vérifier le nombre de CSV téléchargés :

```bash
ls -1 data/processed/04_exports_drive/v04_*_y2026_t*.csv | wc -l
```

**Attendu** : 39 CSV pour `--month 2026-06` (3 sources × 13 tuiles)

**Solution** : Retourner sur Drive et télécharger les CSV manquants.

---

### Problème : Erreur "FileNotFoundError: Aucun CSV pour v04_CHIRPS"

**Cause** : Les CSV pour l'année/décade demandée n'existent pas dans `04_exports_drive/`.

**Solution** :
1. Vérifier que `submit` a bien été lancé pour cette période
2. Vérifier que les CSV ont été téléchargés depuis Drive
3. Vérifier les noms de fichiers (préfixe `v04_`, pattern correct)

---

### Problème : RAM insuffisante (#05 ou #06)

**Symptôme** : `MemoryError` ou processus tué (Killed).

**Solutions** :
1. **Augmenter RAM disponible** (recommandé : ≥16 GB)
2. **Réduire la taille des données** :
   - Extraire par morceaux (ex : 1 mois à la fois)
   - Utiliser `--cells file` pour tester sur un sous-ensemble
3. **Optimiser le code** : Passer à des traitements par batch (chunking pandas)

---

## Automatisation (cron mensuel)

Pour un système opérationnel automatisé, créer un script wrapper :

```bash
#!/bin/bash
# cron-extraction-mensuelle.sh

MONTH=$(date +%Y-%m)  # Mois en cours
VENV="/path/to/.venv/bin/python"

echo "=== Extraction mensuelle : $MONTH ==="

# 1. Submit
$VENV src/04b_export_variables_gee.py submit --cells all --month $MONTH --no-baseline

# 2. Attendre (polling status)
while true; do
  STATUS=$($VENV src/04b_export_variables_gee.py status | grep "RUNNING" | wc -l)
  if [ $STATUS -eq 0 ]; then
    break
  fi
  echo "En attente... ($STATUS tâches en cours)"
  sleep 300  # 5 minutes
done

# 3. Télécharger CSV depuis Drive (nécessite rclone ou API Drive)
# rclone sync gdrive:ee_exports_locusta_v04/ data/processed/04_exports_drive/

# 4. Assemble
$VENV src/04b_export_variables_gee.py assemble --cells all --month $MONTH

# 5. Pipeline complet
$VENV src/feature_engineering_05.py
$VENV src/construction_table_06.py

# 6. Génération cartes
for D in {1..36}; do
  $VENV src/sorties_operationnelles_09.py --campagne 2025-2026 --decade $D
done

echo "=== Extraction terminée ==="
```

**Cron** :

```cron
# Exécuter le 1er de chaque mois à 2h du matin
0 2 1 * * /path/to/cron-extraction-mensuelle.sh >> /var/log/extraction-gee.log 2>&1
```

---

## Références

- **Pipeline #04b** : `docs/pipelines/04-extraction-gee.md`
- **Architecture complète** : `docs/architecture-pipeline.md`
- **Configuration GEE** : `src/config_gee.py`
- **Issue tracker** : `.scratch/severite-phase-forecast/issues/`
