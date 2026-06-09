# 08 — Rapport de performance walk-forward par campagne (Pipeline 10)

Status: ready-for-agent

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

- [ ] Rapport ventilé par campagne (folds walk-forward)
- [ ] QWK, rappel niv. 2–3, AUC binaire, calibration, gain/lift présents
- [ ] Robustesse jugée sur variance inter-folds + pire campagne (pas la meilleure moyenne)
- [ ] Fonctions de métriques testées sur entrées synthétiques

## Blocked by

- `.scratch/severite-phase-forecast/issues/07-benchmark-modeles-ordinaux.md`
