# 06 — Seams de validation : walk_forward_split + select_robust

Status: done

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Deux nouveaux seams (fonctions pures testables) pour la validation, indépendants de tout
algorithme :

- **`walk_forward_split`** : folds = campagnes chronologiques, avec **saut de 2023-2024**
  (labels absents). Pas de chevauchement train/test dans le temps ; chaque fold teste sur une
  saison future par rapport à son train.
- **`select_robust`** : classe les modèles par **rappel des niveaux 2–3** sous contrainte
  **QWK ≥ baseline**, puis départage par **variance inter-folds** (et pire campagne), puis par
  **simplicité/interprétabilité** du modèle. Opère sur des métriques (entrée), pas sur des
  modèles entraînés.

## Acceptance criteria

- [x] `walk_forward_split` : folds chronologiques par campagne
- [x] `walk_forward_split` : campagnes 2023-2024 absentes des folds
- [x] `walk_forward_split` : aucun chevauchement temporel train/test
- [x] `select_robust` : départage rappel niv. 2–3 → variance inter-folds → simplicité (métriques synthétiques)
- [x] `select_robust` : respecte la contrainte QWK ≥ baseline
- [x] Tests dans `tests/` (DataFrames/métriques synthétiques)

## Implementation notes (2026-06-09, /tdd)

- **Module dédié `src/validation_seams.py`** (sans numéro, comme `extraction_gee_helpers.py`) :
  seams purs, sans I/O, réutilisables par les pipelines 07/08 et le rapport 10.
- **`walk_forward_split(campagnes) -> list[(train_camps, test_camp)]`** : tri chronologique
  par année de début, expanding window (train = toutes les campagnes antérieures), test =
  campagne suivante. `SKIP_CAMPAGNES = {"2023-2024"}` retirée avant tout (ni test ni train).
  ≤ 1 campagne exploitable → aucun fold.
- **`select_robust(metrics, baseline_qwk) -> list[str]`** : une ligne par modèle
  (`recall_23`, `qwk`, `variance_inter_folds`, `pire_campagne`, `complexite`). Filtre
  `qwk ≥ baseline_qwk` (≥ inclusif), puis tri lexicographique : `recall_23` ↓,
  `variance_inter_folds` ↑, `pire_campagne` ↓, `complexite` ↑.
- **Pas de `run()`** : fonctions pures. L'intégration dans les pipelines 07/08 (production
  effective de la colonne `split` via `walk_forward_split`) relève de leur refonte benchmark,
  hors de cette issue.
- Tests : `tests/test_seams_validation.py` (10 tests, métriques/campagnes synthétiques).

## Blocked by

- `.scratch/severite-phase-forecast/issues/05-table-entrainement-cellule-decade.md`
