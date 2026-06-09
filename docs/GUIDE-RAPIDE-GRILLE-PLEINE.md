# Guide rapide — Extraction grille pleine

## Commandes essentielles

### Extraction mensuelle (opérationnel)

```bash
# 1. Submit (lancer les tâches GEE)
./.venv/bin/python src/04b_export_variables_gee.py submit \
  --cells all \
  --month 2026-06 \
  --no-baseline

# 2. Status (suivre l'avancement)
./.venv/bin/python src/04b_export_variables_gee.py status

# 3. Télécharger les CSV depuis Google Drive
# → Dossier: ee_exports_locusta_v04/
# → Destination: data/processed/04_exports_drive/

# 4. Assemble (CSV → parquet avec fusion automatique)
./.venv/bin/python src/04b_export_variables_gee.py assemble \
  --cells all \
  --month 2026-06

# 5. Pipeline complet
./.venv/bin/python src/feature_engineering_05.py
./.venv/bin/python src/construction_table_06.py

# 6. Générer la carte (exemple: décade 18 = 3e décade de juin)
./.venv/bin/python src/sorties_operationnelles_09.py \
  --modele data/processed/07_modele_retenu.txt \
  --campagne 2025-2026 \
  --decade 18
```

---

## Options temporelles

### --month (opérationnel, recommandé)

```bash
# Extraction du mois en cours avec buffer automatique (2 décades)
--month 2026-06

# Buffer personnalisé (3 décades)
--month 2026-06 --buffer 3
```

**Calcul automatique** :
- `--month 2026-06 --buffer 2` → décades 14-18 (mai D2-D3 + juin D1-D3)
- Inclut automatiquement les lags nécessaires au modèle

---

### --decades (contrôle fin)

```bash
# Plage de décades précise (décades calendaires 1-36)
--decades 2026-14:2026-18

# Traversant années
--decades 2025-34:2026-03
```

**Décades calendaires** :
- 1-36 = janvier à décembre
- Décade 1 = 1-10 janv, Décade 36 = 21-31 déc

---

### --years (historique complet)

```bash
# Une ou plusieurs années complètes
--years 2026
--years 2025 2026
```

---

## Métriques attendues

### Extraction `--month 2026-06 --buffer 2`

```
Cellules:        181 413
Décades:         5 (2026-14 à 2026-18)
Lignes totales:  ~907 065
Tâches GEE:      39 (parallèles)
Durée:           10-20 minutes
Volume CSV:      ~170 MB
```

**⚠️ Note importante** : Le message "1 lot(s) de tâches GEE" ne signifie **pas** que toute l'année 2026 est extraite. GEE extrait **uniquement les 5 décades demandées** (vérification : ~907k lignes, pas 6,5M). Voir `docs/NOTE-BATCHES-ANNEES.md` pour l'explication technique.

---

## Vérifications

### Après submit

```bash
# Vérifier les tâches
./.venv/bin/python src/04b_export_variables_gee.py status

# Compter les tâches attendues
# → 39 tâches pour --month 2026-06
```

### Après téléchargement CSV

```bash
# Compter les CSV téléchargés
ls -1 data/processed/04_exports_drive/v04_*_y2026_t*.csv | wc -l
# → Attendu: 39 fichiers
```

### Après assemble

```bash
./.venv/bin/python -c "
import pandas as pd
df = pd.read_parquet('data/processed/04_variables_environnementales/')
print(f'Lignes totales : {len(df):,}')
print(f'Cellules uniques : {df.cell_id.nunique():,}')
print(f'Période : {df.date_start.min()} → {df.date_start.max()}')

# Vérifier juin 2026
june = df[(df.date_start >= '2026-06-01') & (df.date_start < '2026-07-01')]
print(f'\nJuin 2026 : {len(june):,} lignes, {june.cell_id.nunique():,} cellules')
"
```

**Attendu juin 2026** :
- ~544 239 lignes (181 413 cellules × 3 décades de juin)

---

## Dépannage rapide

### Tâches échouées (FAILED)

```bash
# Voir le statut
./.venv/bin/python src/04b_export_variables_gee.py status

# Relancer (mêmes arguments)
./.venv/bin/python src/04b_export_variables_gee.py submit --cells all --month 2026-06 --no-baseline

# Ou annuler toutes les tâches
./.venv/bin/python src/04b_export_variables_gee.py cancel
```

### CSV manquants

```bash
# Compter les CSV
ls data/processed/04_exports_drive/v04_*_y2026_t*.csv | wc -l

# Si < 39 → retourner sur Drive et télécharger les manquants
```

### Erreur "FileNotFoundError: Aucun CSV"

**Cause** : Les CSV n'ont pas été téléchargés depuis Drive.

**Solution** :
1. Vérifier Google Drive : `ee_exports_locusta_v04/`
2. Télécharger tous les `v04_*_y2026_t*.csv`
3. Déplacer dans `data/processed/04_exports_drive/`

---

## Documentation complète

- **Runbook détaillé** : `docs/runbook-extraction-grille-pleine.md`
- **Modifications** : `docs/MODIFICATIONS-GRILLE-PLEINE.md`
- **Pipeline #04b** : `docs/pipelines/04-extraction-gee.md`
- **Script de test** : `scripts/test-extraction-grille-pleine.sh`
