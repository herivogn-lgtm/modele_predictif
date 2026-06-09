# 07 — Benchmark modèles ordinaux (Pipelines 07/08, refonte)

Status: ready-for-agent

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

- [ ] Les 6 modèles sont entraînés et évalués via le split walk-forward
- [ ] Cadrage ordinal explicite (régression arrondie ou multiclasse)
- [ ] Pondération de classe appliquée au niveau 3
- [ ] Métriques par campagne produites pour chaque modèle (alimentent `select_robust` et le rapport)
- [ ] Tests des fonctions pures dans `tests/test_07_*.py` / `tests/test_08_*.py`
- [ ] Aucune suppression de Pipeline 11 ni de `model_2/`

## Blocked by

- `.scratch/severite-phase-forecast/issues/06-seams-walk-forward-select-robust.md`
