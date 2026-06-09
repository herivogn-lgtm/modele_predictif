# Session d'interview — Prédiction grille pleine

**Date** : 2026-06-09  
**Durée** : ~17 questions  
**Objectif** : Clarifier et implémenter l'extraction GEE sur la grille complète pour la prédiction opérationnelle mensuelle

---

## Décisions prises (par ordre chronologique)

### ✓ Q1 : Taille réelle de la grille

**Question** : Contradiction entre CONTEXT.md (~1 800 cellules) et handoff (181 413 cellules)  
**Décision** : Confirmer 181 413 cellules, corriger CONTEXT.md  
**Rationale** : Aire grégarigène = 181 414 km², grille 1 km = 1 cellule/km²

---

### ✓ Q2 : Profondeur des lags

**Question** : Combien de décades antérieures le modèle utilise-t-il ?  
**Décision** : 2 décades (T-2)  
**Méthode** : Audit de `src/feature_engineering_05.py` (lignes 95-96, 109-110)  
**Impact** : Buffer automatique = 2 décades pour `--month`

---

### ✓ Q3 : Périmètre temporel pour juin 2026

**Question** : Faut-il extraire toute l'année 2026 ou juste juin ?  
**Décision** : Flexible selon besoin (5, 20, ou 36 décades)  
**Implémentation** : Options `--month`, `--decades`, `--years`

---

### ✓ Q4 : Pipeline #04 vs #04b

**Question** : Quel script utiliser pour l'extraction ?  
**Décision** : #04b (Export.table batch) obligatoire pour grille complète  
**Rationale** : #04 (getInfo) nécessiterait ~86 000 appels vs 39 tâches pour #04b

---

### ✓ Q5 : Architecture unifiée vs séparée

**Question** : Fusionner historique (5k cellules) + grille pleine (181k) ou garder séparé ?  
**Décision** : Architecture unifiée (Option A)  
**Rationale** : Simplifie le pipeline, modèle apprend à gérer cellules sans historique

---

### ✓ Q6 : Stratégie de fusion des données

**Question** : Comment fusionner nouvelles extractions avec l'existant ?  
**Décision** : Option B (fusion incrémentale avec modification code)  
**Implémentation** : Modifier `assemble()` pour charger + dédoublonner

---

### ✓ Q7 : Coût extraction `--cells all --years 2026`

**Question** : Combien de temps pour extraire 2026 complet ?  
**Réponse** : 39 tâches dynamiques, 30-45 min (tâches parallèles)  
**Baseline** : Déjà extraite (~179 646 cellules), utiliser `--no-baseline`

---

### ✓ Q8 : Baseline existante suffisante ?

**Question** : Baseline couvre 179 646 cellules, manque ~1 767 cellules  
**Décision** : Utiliser telle quelle pour l'instant (cellules manquantes auront `chirps_anomaly=NaN`)  
**Alternative** : Relancer baseline avec `--cells all` si problématique

---

### ✓ Q9 : Gestion des doublons

**Question** : Que faire si `(cell_id, date_start)` existe déjà ?  
**Décision** : Dédoublonnage automatique, garder la version la plus récente  
**Implémentation** : `part.drop_duplicates(subset=["cell_id", "date_start"], keep="last")`

---

### ✓ Q10 : Stratégie de fusion (décision critique)

**Question** : Big bang (tout ré-extraire) vs fusion incrémentale ?  
**Décision** : Option B (fusion incrémentale)  
**Rationale** : Minimise coût GEE (39 tâches vs ~1000), préserve historique

---

### ✓ Q11 : Besoin de toute l'année 2026 ?

**Question** : Faut-il extraire 36 décades ou juste le mois cible ?  
**Décision** : Extraction minimale selon besoin opérationnel  
**Implémentation** : Options `--month` (5 décades) vs `--decades` vs `--years` (36)

---

### ✓ Q12 : Interface CLI flexible

**Question** : Comment spécifier des décades précises (pas seulement années) ?  
**Décision** : Hybride `--decades` (précis) + `--month` (opérationnel)  
**Buffer** : Automatique (2 décades, profondeur lags) avec option `--buffer N`

---

### ✓ Q13 : Mode de fusion dans `assemble()`

**Question** : Fusion par défaut ou remplacement par défaut ?  
**Décision** : Option A + 1 (fusion safe par défaut, garder le plus récent)  
**Implémentation** : Pas de flag `--replace`, comportement automatique

---

### ✓ Q14 : Workflow simple sans modification ?

**Question** : Peut-on juste ajouter CSV dans exports_dir et relancer assemble ?  
**Réponse** : Oui, MAIS risque de doublons sans dédoublonnage  
**Décision** : Ajouter dédoublonnage automatique (Option B, 1 ligne de code)

---

### ✓ Q15 : Paramètres interface CLI

**Question A** : Buffer par défaut pour `--month` ?  
**Décision** : Auto (profondeur lags = 2), overridable via `--buffer N`

**Question B** : Convention décades (calendaires vs campagne) ?  
**Décision** : Décades calendaires (1-36 = janvier-décembre)  
**Rationale** : Collections GEE organisées par année civile

---

### ✓ Q16 : Vérification cohérence baseline

**Question** : Relancer baseline pour couvrir les 181 413 cellules ?  
**Décision** : Reporter à plus tard (Option A : utiliser existante)  
**Rationale** : ~1 767 cellules manquantes (< 1%) acceptable pour premiers tests

---

### ✓ Q17 : Ordre des opérations (première extraction)

**Question** : Tout en une fois ou validation incrémentale ?  
**Décision** : Implémenter directement, tests manuels par l'utilisateur  
**Rationale** : Utilisateur veut tester lui-même, pas de dérisquage automatique

---

## Livrables

### Code modifié

1. **`src/extraction_gee_helpers.py`** (+120 lignes)
   - `parse_month_to_decades()`
   - `parse_decades_range()`
   - `build_decade_calendar_range()`

2. **`src/04b_export_variables_gee.py`** (+100 lignes)
   - CLI `--month`, `--decades`, `--buffer`
   - `submit()` avec `decade_range` parameter
   - `assemble()` avec fusion + dédoublonnage automatique

3. **`CONTEXT.md`** (~2 lignes)
   - Correction taille aire grégarigène : 181 414 km² → ~181 413 cellules

---

### Documentation

1. **`docs/runbook-extraction-grille-pleine.md`** (nouveau)
   - Workflow opérationnel mensuel (5 étapes)
   - Extraction initiale (3 options)
   - Dépannage (tâches échouées, CSV manquants, RAM)
   - Automatisation (script cron)

2. **`docs/MODIFICATIONS-GRILLE-PLEINE.md`** (nouveau)
   - Résumé des modifications
   - Impact sur workflows existants
   - Métriques et tests

3. **`docs/GUIDE-RAPIDE-GRILLE-PLEINE.md`** (nouveau)
   - Commandes essentielles
   - Options temporelles
   - Vérifications rapides
   - Dépannage

4. **`scripts/test-extraction-grille-pleine.sh`** (nouveau)
   - Script de test interactif
   - Simulation + commandes guidées

---

## Tests effectués

✓ Parsing `--month 2026-06` → (2026, 14, 2026, 18)  
✓ Parsing `--month 2026-01` (traverse année) → (2025, 35, 2026, 3)  
✓ Parsing `--decades 2026-14:2026-18` → (2026, 14, 2026, 18)  
✓ Parsing `--decades 2025-34:2026-03` (traverse année) → (2025, 34, 2026, 3)  
✓ Génération calendrier 5 décades (2026-14 à 2026-18)  
✓ Génération calendrier traversant années  
✓ CLI help et exemples d'usage  
✓ Imports et syntaxe Python  
✓ Simulation workflow complet (dry-run)

---

## Métriques validation

### Extraction `--month 2026-06 --buffer 2`

```
Plage temporelle:  décades 2026-14 à 2026-18
Période:           2026-05-11 → 2026-06-30
Décades:           5
Cellules:          181,413
Tuiles spatiales:  13 (≤15,000 cellules/tuile)
Tâches GEE:        39 (3 sources × 1 lot × 13 tuiles)
Lignes attendues:  ~907,065
Volume CSV:        ~173 MB
Durée estimée:     10-20 minutes
```

---

## Prochaines étapes recommandées

1. **Test manuel** : `./scripts/test-extraction-grille-pleine.sh`
2. **Validation RAM** : Vérifier #05/#06 avec ~5-6 GB de données
3. **Extraction réelle** : Lancer `--month 2026-06` sur grille complète
4. **Baseline complète** (optionnel) : Relancer si cellules manquantes posent problème
5. **Automatisation** : Implémenter script cron pour extraction mensuelle

---

## Points d'attention

⚠️ **RAM** : `06_table_*.parquet` peut atteindre ~5 GB (181k cellules × historique)  
⚠️ **Durée** : Première extraction complète = 30-45 min + téléchargement CSV  
⚠️ **Drive** : Vérifier espace disponible (~2-3 GB pour CSV)  
⚠️ **Baseline** : ~1 767 cellules manquantes (< 1%), acceptable pour tests  

---

## Changements breaking

**Aucun** : Workflows existants (`--cells observed`) inchangés.

---

## Support

- **Runbook détaillé** : `docs/runbook-extraction-grille-pleine.md`
- **Guide rapide** : `docs/GUIDE-RAPIDE-GRILLE-PLEINE.md`
- **Modifications** : `docs/MODIFICATIONS-GRILLE-PLEINE.md`
- **Script de test** : `scripts/test-extraction-grille-pleine.sh`
