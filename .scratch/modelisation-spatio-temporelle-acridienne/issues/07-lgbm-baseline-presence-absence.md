---
Status: done
---

# #07 — Modèle LightGBM baseline présence/absence + validation walk-forward

## What to build

Entraîner un modèle LightGBM de classification binaire (présence/absence du criquet migrateur malagasy) sur la table d'entraînement unifiée, avec validation walk-forward par campagne entière. Appliquer `scale_pos_weight` pour corriger le déséquilibre de classes, et optimiser le seuil de décision (cible ~0,15–0,20) pour maximiser le rappel sur la présence. Produire un rapport de performance par fold de campagne : AUC-ROC, précision, rappel, F1. La cible de performance est AUC > 0,85 sur le fold de validation (campagnes 2016–17 à 2021–22).

## Acceptance criteria

- [x] AUC > 0,85 sur le fold de validation walk-forward (campagnes 2016–17 à 2021–22) — AUC global = 0.9560
- [x] Le seuil de décision optimisé sur le rappel est documenté dans le rapport
- [x] Le rapport walk-forward présente les métriques campagne par campagne (pas uniquement une moyenne globale)
- [x] Aucune décade d'une campagne de validation n'apparaît dans l'ensemble d'entraînement du même fold
- [x] Les importances de features LightGBM sont exportées pour interprétation

## Blocked by

- `.scratch/modelisation-spatio-temporelle-acridienne/issues/06-table-entrainement-unifiee.md`
