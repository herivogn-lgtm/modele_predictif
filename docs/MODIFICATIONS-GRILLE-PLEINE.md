# Modifications — Extraction grille pleine et prédiction opérationnelle

**Date** : 2026-06-09  
**Branche** : `amelioration`  
**Objectif** : Permettre l'extraction GEE sur la grille complète (181 413 cellules) et la prédiction opérationnelle mensuelle

---

## Résumé des modifications

### 1. Nouvelles options CLI pour `04b_export_variables_gee.py`

**Avant** : Extraction uniquement par années complètes (`--years`)

**Après** : Trois modes d'extraction temporelle :
- `--years YYYY [YYYY ...]` : Années civiles complètes (mode historique)
- `--month YYYY-MM` : Mois spécifique avec buffer automatique pour lags (mode opérationnel)
- `--decades YYYY-DD:YYYY-DD` : Plage de décades précise (contrôle fin)

**Exemples** :
```bash
# Extraction mensuelle (opérationnel)
python src/04b_export_variables_gee.py submit --cells all --month 2026-06 --no-baseline

# Extraction par décades
python src/04b_export_variables_gee.py submit --cells all --decades 2026-14:2026-18 --no-baseline

# Extraction par années (historique)
python src/04b_export_variables_gee.py submit --cells all --years 2026 --no-baseline
```

---

### 2. Dédoublonnage automatique dans `assemble()`

**Avant** : `assemble()` **supprimait** tous les parquets existants avant d'écrire les nouveaux → risque de perte de données

**Après** : `assemble()` **fusionne** automatiquement les nouvelles données avec l'existant :
- Charge les parquets existants avant traitement
- Concatène ancien + nouveau
- Dédoublonne sur `(cell_id, date_start)`, garde la version la plus récente
- Permet l'accumulation incrémentale sans perte d'historique

**Impact** : Workflow opérationnel mensuel sans manipulation manuelle

---

### 3. Fonctions helper dans `extraction_gee_helpers.py`

**Nouvelles fonctions** :
- `parse_month_to_decades(month_str, buffer)` : Parse `--month` en plage de décades
- `parse_decades_range(decades_str)` : Parse `--decades` en plage
- `build_decade_calendar_range(y_start, d_start, y_end, d_end)` : Génère calendrier pour une plage précise

**Cas d'usage** :
```python
# Juin 2026 avec buffer 2 décades
parse_month_to_decades("2026-06", buffer=2)
# → (2026, 14, 2026, 18)  # Mai D2-D3 + Juin D1-D3

# Plage traversant années
parse_decades_range("2025-34:2026-03")
# → (2025, 34, 2026, 3)  # Fin 2025 → début 2026
```

---

### 4. Correction CONTEXT.md

**Avant** : Aire grégarigène = 181 414 ha (~1 814 km²) → **~1 800 cellules**

**Après** : Aire grégarigène = **181 414 km²** → **~181 413 cellules**

**Impact** : Alignement avec la réalité (grille 1 km = 1 cellule/km²)

---

### 5. Documentation opérationnelle

**Nouveau fichier** : `docs/runbook-extraction-grille-pleine.md`

**Contenu** :
- Workflow opérationnel mensuel complet (5 étapes)
- Extraction initiale (première fois)
- Dépannage (tâches échouées, CSV manquants, RAM)
- Automatisation (script cron)

---

## Impact sur les workflows existants

### Workflow entraînement (inchangé)

```bash
# Extraction cellules observées (5 396 cellules) — INCHANGÉ
python src/04b_export_variables_gee.py submit --cells observed --years 2001-2026
python src/04b_export_variables_gee.py assemble --cells observed --years 2001-2026
```

**Aucun impact** : Le comportement par défaut (`--cells observed`) reste identique.

---

### Workflow prédiction opérationnelle (nouveau)

```bash
# 1. Extraction mensuelle (181 413 cellules × 5 décades)
python src/04b_export_variables_gee.py submit --cells all --month 2026-06 --no-baseline

# 2. Suivi des tâches
python src/04b_export_variables_gee.py status

# 3. Télécharger CSV depuis Drive → data/processed/04_exports_drive/

# 4. Assemblage avec fusion automatique
python src/04b_export_variables_gee.py assemble --cells all --month 2026-06

# 5. Pipeline complet
python src/feature_engineering_05.py
python src/construction_table_06.py
python src/sorties_operationnelles_09.py --campagne 2025-2026 --decade 18
```

---

## Métriques

### Extraction `--month 2026-06 --buffer 2`

| Métrique | Valeur |
|----------|--------|
| **Décades extraites** | 5 (2026-14 à 2026-18) |
| **Cellules** | 181 413 |
| **Lignes totales** | ~907 065 |
| **Tâches GEE** | 39 (3 sources × 1 lot × 13 tuiles) |
| **Durée estimée** | 10-20 min (tâches parallèles) |
| **Volume CSV** | ~170 MB |
| **Volume parquet final** | ~5-6 GB (historique complet + nouveaux mois) |

---

## Tests effectués

✓ Parsing `--month` avec buffer (juin 2026)  
✓ Parsing `--month` traversant années (janvier 2026)  
✓ Parsing `--decades` simple (2026-14:2026-18)  
✓ Parsing `--decades` traversant années (2025-34:2026-03)  
✓ Génération calendrier pour plage de décades  
✓ CLI help et exemples d'usage  
✓ Simulation workflow complet (dry-run)

---

## Changements breaking

**Aucun** : Tous les workflows existants restent compatibles.

---

## Prochaines étapes (recommandées)

1. **Test manuel** : Lancer une extraction `--month 2026-06` sur un petit échantillon (`--cells file` avec 1000 cellules)
2. **Validation RAM** : Vérifier que #05/#06 gèrent bien ~5-6 GB de données
3. **Extraction baseline complète** : Relancer baseline avec `--cells all` si les ~1 767 cellules manquantes posent problème
4. **Automatisation** : Implémenter le script cron pour extraction mensuelle automatique

---

## Fichiers modifiés

```
src/extraction_gee_helpers.py          (+120 lignes)  # Nouvelles fonctions parsing
src/04b_export_variables_gee.py        (+100 lignes)  # CLI + dédoublonnage
CONTEXT.md                             (~2 lignes)    # Correction taille grille
docs/runbook-extraction-grille-pleine.md  (nouveau)   # Documentation opérationnelle
docs/MODIFICATIONS-GRILLE-PLEINE.md    (nouveau)      # Ce fichier
```

---

## Support

**Questions/problèmes** : Voir `docs/runbook-extraction-grille-pleine.md` section "Dépannage"

**Issues** : `.scratch/severite-phase-forecast/issues/`
