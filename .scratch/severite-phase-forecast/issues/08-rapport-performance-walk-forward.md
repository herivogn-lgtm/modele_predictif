# 08 — Rapport de performance walk-forward par campagne (Pipeline 10)

Status: in-progress

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Produire le rapport de performance walk-forward, **par campagne**, qui sert de support à la
revue humaine avant la mise en production des cartes (issue 09) :

- QWK (quadratic weighted kappa)
- Rappel des niveaux 2–3
- AUC binaire (sur le binaire dérivé) — exigence thèse §31/§33
- Calibration des probabilités
- Courbe de gain / lift (gain opérationnel)

La qualité prédictive réelle se mesure ici, sur données réelles — pas en test unitaire. Les
fonctions de calcul de métriques restent des fonctions pures testables.

## Acceptance criteria

- [x] Rapport ventilé par campagne (folds walk-forward)
- [x] QWK, rappel niv. 2–3, AUC binaire, calibration, gain/lift présents
- [x] Robustesse jugée sur variance inter-folds + pire campagne (pas la meilleure moyenne)
- [x] Fonctions de métriques testées sur entrées synthétiques

## Implementation notes (2026-06-09, /tdd)

- **Nouveau module `src/rapport_performance_08.py`** (Pipeline 10 du PRD ; nommé `_08`
  pour suivre le numéro d'issue). Fonctions pures (TDD, 10 tests
  `tests/test_08_rapport_performance.py`) :
  - `derive_binaire(severite)` : binaire présence dérivé = (sév ≥ 1) — exigence AUC thèse §31/§33.
  - `presence_from_proba(proba, classes)` : proba de présence multiclasse = `1 − P(absence)`
    (somme des colonnes des niveaux ≥ 1 ; robuste aux folds à niveaux manquants).
  - `auc_binaire(y_bin, score)` : AUC du binaire dérivé (`NaN` si classe unique dans le fold).
  - `calibration_table(y_bin, proba, n_bins=10)` : diagramme de fiabilité
    `{proba_moyenne, freq_observee, n}`, bins largeur égale, bins vides exclus.
  - `gain_lift_table(y_bin, score, n_bins=10)` : `{quantile, pop_cumulee, gain_cumule, lift}`
    (tri score décroissant, cumul) — gain opérationnel d'une prospection priorisée.
  - `rapport_par_campagne(folds)` : 1 ligne/campagne `{qwk, recall_23, auc_binaire, n}`
    (QWK + rappel 2–3 réutilisés de `evaluate_ordinal` #07).
  - `resume_robustesse(rapport)` : par métrique → moyenne, **variance inter-folds**,
    **pire campagne** (nan-agrégats ; PRD §20/§24, on juge la pire campagne, pas la moyenne).
- **Orchestration `run()`** (non testée, lourde) : lit la table #06 + le modèle retenu
  (`07_modele_retenu.txt`), ré-entraîne **uniquement ce modèle** par fold walk-forward,
  produit sévérité ordinale + score de présence (multiclasse : `predict_proba` ;
  régression : logistique centrée sur la frontière absence/présence 0.5), puis écrit
  `08_rapport_par_campagne.csv`, `08_calibration.csv`, `08_gain_lift.csv`, `08_rapport_resume.txt`.
- **Run réel validé** (2026-06-09, modèle retenu `regression_ordinale`, 22 020 lignes
  observées, 22 features, 21 folds) :
  - **AUC binaire moyen = 0.746** (pire campagne 0.435, variance inter-folds 0.012).
  - QWK moyen 0.3072 et recall_23 0.5418 = **identiques aux chiffres #07** (même modèle/folds,
    contrôle de cohérence).
  - Calibration monotone (freq observée croît avec la proba ; léger sous-confiance médian).
  - Gain/lift modeste (lift 1.20 au 1er décile → 1.0), cohérent avec le QWK modeste du
    modèle linéaire — signal à arbitrer en revue humaine (#09).
  - Folds dégénérés (2012-2013 sans présence, 2024-2025 n=1) → métriques NaN ignorées.
- **Reste avant clôture** : relancer après le **run complet de référence #07** (300 arbres +
  LSTM) si `select_robust` retient un autre modèle que la régression ordinale (le rapport
  s'adapte automatiquement via `07_modele_retenu.txt`).

## Blocked by

- `.scratch/severite-phase-forecast/issues/07-benchmark-modeles-ordinaux.md`
