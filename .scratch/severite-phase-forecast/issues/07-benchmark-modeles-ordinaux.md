# 07 — Benchmark modèles ordinaux (Pipelines 07/08, refonte)

Status: in-progress

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Remplacer le « LightGBM seul » par un **benchmark** de modèles entraînés et évalués via
`walk_forward_split` + `select_robust` (issue 06) :

- Régression ordinale (**baseline**)
- Random Forest (référence thèse)
- XGBoost
- LightGBM
- CatBoost (catégoriel natif)
- LSTM (**testé**)

Cadrage ordinal : régression 0–3 arrondie ou multiclasse. **Pondération de classe** pour le
niveau 3 minoritaire (~6,6 %) afin qu'il ne soit pas écrasé. Sortie = modèles entraînés +
métriques par campagne, prêts pour le rapport (issue 08).

Pipeline 11 (NeuralProphet) et `model_2/` sont **laissés intacts** (hors périmètre de ce lot).

## Acceptance criteria

- [x] Les 6 modèles sont entraînés et évalués via le split walk-forward *(5/6 vérifiés en sandbox ; LSTM torch à valider sur la machine de l'utilisateur, run réel à exécuter)*
- [x] Cadrage ordinal explicite (régression arrondie ou multiclasse)
- [x] Pondération de classe appliquée au niveau 3
- [x] Métriques par campagne produites pour chaque modèle (alimentent `select_robust` et le rapport)
- [x] Tests des fonctions pures dans `tests/test_07_*.py` / `tests/test_08_*.py`
- [x] Aucune suppression de Pipeline 11 ni de `model_2/`

## Implementation notes (2026-06-09, /tdd)

- **Nouveau module `src/benchmark_ordinal_07.py`** (`lgbm_baseline_07.py` binaire/région
  laissé intact). Fonctions pures (TDD, 12 tests `tests/test_07_benchmark_ordinal.py`) :
  - `to_ordinal(y)` : score continu → niveau 0–3 (round + clip).
  - `compute_class_weights(y)` : inverse-fréquence « balanced », surpondère niv. 3 (~6,6 %).
  - `evaluate_ordinal(y_true, y_pred)` : `{qwk, recall_23}` (QWK quadratique sklearn ;
    rappel des vrais niveaux 2–3, NaN si aucun foyer dans le fold).
  - `aggregate_model_metrics(per_fold, modele, complexite)` : agrège au **schéma exact de
    `select_robust`** (`recall_23`, `qwk`, `variance_inter_folds`, `pire_campagne`,
    `complexite`) — nanmean/nanvar/nanmin (ignore folds sans foyer).
  - `build_models()` : registre des 6 modèles (`ModelSpec` = framing + complexité +
    factory paresseuse). Cadrage **par modèle** : régression ordinale (Ridge) & LSTM en
    régression arrondie ; RF/LightGBM/XGBoost/CatBoost en multiclasse 0–3. Complexité
    croissante (tie-break simplicité) : régression (1) < arbres (3–4) < LSTM (5).
  - `run_benchmark(...)` : câble `walk_forward_split` (#06) × modèles × `evaluate_ordinal`
    × `aggregate`. **Résilient** : un modèle qui lève est consigné en NaN sans tuer le
    benchmark. `return_detail=True` → métriques ventilées par (modèle, campagne).
  - `run()` : lit #06, n'entraîne que les **observées** (severite non-NaN), impute les lags
    précoces (médiane), exécute le benchmark, applique `select_robust` (contrainte
    QWK ≥ baseline = QWK de la régression ordinale), écrit `07_benchmark_resume.csv`,
    `07_benchmark_par_campagne.csv`, `07_modele_retenu.txt`.
- **`src/lstm_ordinal.py`** : wrapper torch minimal (interface sklearn fit/predict, MSE
  pondérée). Limite assumée : séquence longueur 1 (pas d'index temporel passé), LSTM
  « testé » au sens PRD §17, pas optimisé.
- **xgboost + catboost installés** dans le venv (décision utilisateur).
- **Correctifs run réel** (2 bugs de config trouvés à l'exécution sur la table #06) :
  1. **XGBoost ≥ 2.0** exige des classes contiguës `0..k-1` ; or certains folds n'ont pas
     les 4 niveaux. Fix : encodage/décodage `LabelEncoder` dans la branche multiclasse de
     `_fit_predict` (inoffensif pour les autres). `num_class`/`objective` forcés retirés.
  2. **QWK indéfini** sur fold dégénéré (un seul niveau commun) → `NaN` (agrégé par
     `nanmean`), warning sklearn silencé dans `evaluate_ordinal`.
- **Mode léger** (`build_models(n_estimators, n_jobs, include_lstm)` + variables d'env
  `BENCH_N_ESTIMATORS` / `BENCH_N_JOBS` / `BENCH_LSTM`) pour limiter durée et chauffe.
- **Run express validé** (2026-06-09, 100 arbres, 4 cœurs, sans LSTM, 22 campagnes
  observées → **21 folds**, 5 modèles) :

  | modèle | recall 2–3 | QWK | pire campagne |
  |---|---|---|---|
  | regression_ordinale (retenu) | 0.542 | 0.307 | 0.0 |
  | catboost | 0.523 | 0.328 | 0.0 |
  | lightgbm | 0.516 | 0.297 | 0.0 |
  | random_forest | 0.477 | 0.282 | 0.1 |
  | xgboost | 0.428 | 0.304 | 0.0 |

  `select_robust` → `[regression_ordinale, catboost]` (QWK ≥ baseline 0.307) ; **retenu =
  régression ordinale** (meilleur rappel 2–3). QWK modestes + `pire_campagne` souvent 0 :
  signal à creuser dans le rapport #08 (variance inter-folds, pire campagne).
- **Reste à faire avant clôture** : run **complet** de référence (300 arbres + LSTM) à
  lancer par l'utilisateur au repos (`python src/benchmark_ordinal_07.py`) → valide le 6ᵉ
  modèle (LSTM) sur données réelles et fige les chiffres de référence. Chaîne déjà prouvée
  saine en express.

## Blocked by

- `.scratch/severite-phase-forecast/issues/06-seams-walk-forward-select-robust.md`
