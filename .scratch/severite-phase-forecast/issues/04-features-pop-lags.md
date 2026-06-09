# 04 — Features POP + lags anti-fuite + AIRE_CODE (Pipeline 05)

Status: ready-for-agent

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Construire les features prédictives sur la table cellule × décade :

- **POP (plage d'optimum pluviométrique)** : appartenance à la bande **50–125 mm/mois** en
  fenêtre glissante + **persistance multi-mois**. Descripteur écologique dérivé (pas la pluie
  brute), hérité du support CHIRPS, attaché aux cellules 1 km.
- **Lags** : cumul pluie 2–3 décades, NDVI/LST décalés, sévérité historique de la cellule.
- `AIRE_CODE` (AMI/ATM/AD/AGT) comme prédicteur **catégoriel**.

**Interdiction absolue de toute covariable de la décade T+1** (anti-fuite temporelle) : toutes
les features doivent être calculées à partir de décades ≤ T.

## Acceptance criteria

- [ ] `compute_pop` : bande 50–125 mm/mois correcte + persistance multi-mois
- [ ] `build_lags` : décalages corrects (cumul pluie 2–3 décades, NDVI/LST, sévérité historique)
- [ ] `build_lags` : **aucune feature issue de T+1** (test anti-fuite explicite)
- [ ] `AIRE_CODE` présent comme variable catégorielle
- [ ] Tests dans `tests/test_05_feature_engineering.py`

## Blocked by

- `.scratch/severite-phase-forecast/issues/02-cible-ordinale-severite-phase.md`
- `.scratch/severite-phase-forecast/issues/03-extraction-gee-decadaire-1km.md`
