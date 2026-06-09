# 06 — Seams de validation : walk_forward_split + select_robust

Status: ready-for-agent

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

- [ ] `walk_forward_split` : folds chronologiques par campagne
- [ ] `walk_forward_split` : campagnes 2023-2024 absentes des folds
- [ ] `walk_forward_split` : aucun chevauchement temporel train/test
- [ ] `select_robust` : départage rappel niv. 2–3 → variance inter-folds → simplicité (métriques synthétiques)
- [ ] `select_robust` : respecte la contrainte QWK ≥ baseline
- [ ] Tests dans `tests/` (DataFrames/métriques synthétiques)

## Blocked by

- `.scratch/severite-phase-forecast/issues/05-table-entrainement-cellule-decade.md`
