# Pipeline #07 — Benchmark de modèles ordinaux (sévérité-phase 0–3)

**Script** : `src/benchmark_ordinal_07.py`
**Entrée** : `data/processed/06_table_entrainement_unifiee.parquet`
**Sorties** : `07_benchmark_resume.csv`, `07_benchmark_par_campagne.csv`, `07_modele_retenu.txt`
**Durée estimée** : 5–30 minutes (mode léger) à plusieurs heures (run complet 300 arbres + LSTM)
**Dépendance obligatoire** : Pipeline [#06](06-table-entrainement.md)

---

## Objectif

Remplacer le « LightGBM seul » binaire par un **benchmark de modèles ordinaux** prédisant la sévérité-phase **0–3** à la maille cellule × décade ([ADR 0005](../adr/0005-benchmark-modeles-selection-robustesse.md)). Les modèles sont entraînés et évalués via les seams `walk_forward_split` + `select_robust` (issue #06), puis le **modèle retenu** est exporté pour le rapport ([#10](10-rapport-performance.md)) et les cartes ([#09](09-sorties-operationnelles.md)).

### Cadrage ordinal par modèle

| Modèle | Cadrage | Complexité |
|--------|---------|-----------|
| régression ordinale (**baseline**) | score continu arrondi par `to_ordinal` | 1 |
| Random Forest | classification multiclasse 0–3 | 3 |
| LightGBM | classification multiclasse 0–3 | 4 |
| XGBoost | classification multiclasse 0–3 | 4 |
| CatBoost | classification multiclasse 0–3 (catégoriel natif) | 4 |
| LSTM (torch) | régression arrondie | 5 |

**Pondération de classe** pour le niveau 3 minoritaire (~6,6 %) afin qu'il ne soit pas écrasé.

---

## Sélection du modèle (`select_robust`)

1. Classer par **rappel des niveaux 2–3** (« ne pas manquer un foyer ») sous contrainte **QWK ≥ baseline**.
2. Départager par **variance inter-folds** (robustesse, pas la meilleure moyenne — PRD §20).
3. Tie-break final vers le modèle **le plus simple / interprétable** (PRD §21).

Validation **walk-forward** par campagne (expanding window), **saut 2023-2024** (labels absents).

---

## Sorties

| Fichier | Contenu |
|---------|---------|
| `07_benchmark_par_campagne.csv` | Métriques par campagne × modèle (QWK, rappel 2–3, …) |
| `07_benchmark_resume.csv` | Agrégats par modèle (moyenne, variance inter-folds, pire campagne, complexité) |
| `07_modele_retenu.txt` | Nom du modèle retenu + classement + `baseline_qwk` (lu par #09/#10) |

---

## Fonctions pures (testées — `tests/test_07_benchmark_ordinal.py`)

| Fonction | Rôle |
|----------|------|
| `to_ordinal(y_continuous)` | Arrondi/clip d'un score continu en classe 0–3 |
| `compute_class_weights(y)` | Pondération de classe (niveau 3 minoritaire) |
| `evaluate_ordinal(y_true, y_pred)` | QWK + rappel des niveaux 2–3 |
| `aggregate_model_metrics(per_fold, modele, complexite)` | Moyenne / variance inter-folds / pire campagne |
| `build_models(n_estimators, n_jobs, include_lstm)` | Registre des specs de modèles |
| `get_feature_columns(df)` | Colonnes de features (exclut cibles/identifiants) |

Seams réutilisés (`src/validation_seams.py`, testés dans `tests/test_seams_validation.py`) : `walk_forward_split` (folds chronologiques, `SKIP_CAMPAGNES = {"2023-2024"}`), `select_robust`.

---

## Lancement

```bash
# Mode léger (itération rapide) : moins d'arbres, sans LSTM
BENCH_N_ESTIMATORS=120 BENCH_LSTM=0 ./.venv/bin/python src/benchmark_ordinal_07.py

# Run complet de référence (300 arbres + LSTM)
./.venv/bin/python -u src/benchmark_ordinal_07.py 2>&1 | tee /tmp/bench07.log
```

Variables d'environnement : `BENCH_N_ESTIMATORS` (défaut 300), `BENCH_N_JOBS` (défaut -1), `BENCH_LSTM` (`0` pour exclure le LSTM torch).

## Aval

[#10](10-rapport-performance.md) (rapport de performance sur le modèle retenu) et [#09](09-sorties-operationnelles.md) (génération des cartes après validation humaine).
