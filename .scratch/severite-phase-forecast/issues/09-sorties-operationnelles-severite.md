# 09 — Sorties opérationnelles : carte de sévérité 0–3 + export SIG (Pipeline 09)

Status: ready-for-human

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

> **HITL** : un humain valide le modèle retenu (via le rapport de l'issue 08) **avant** de
> générer les cartes destinées au terrain.

Restituer les prédictions de sévérité-phase pour la décade T+1 :

- **Carte de sévérité 0–3** à 1 km pour la décade à venir (alerte précoce)
- **Agrégat mensuel** par aire complémentaire (AMI/ATM/AD/AGT) pour la planification
- **Binaire dérivé** (probabilité de présence) pour comparaison AUC à la littérature
- Export **PNG** + export **SIG** (vectoriel/raster) pour intégration aux supports terrain

L'outil oriente les prospections vers les cellules à sévérité 2–3 et signale les passages au
niveau 3 (grégaire) en T+1.

## Acceptance criteria

- [ ] Carte de sévérité 0–3 à 1 km pour la décade T+1
- [ ] `to_severity_map` : agrégation décade → mois correcte
- [ ] Agrégat mensuel par aire AMI/ATM/AD/AGT
- [ ] Binaire dérivé restitué (carte de probabilité de présence)
- [ ] Export PNG + export SIG produits
- [ ] Modèle de production validé par un humain via le rapport (issue 08) avant génération
- [ ] Tests dans `tests/test_09_*.py` (`to_severity_map`, `derive_binary`)

## Blocked by

- `.scratch/severite-phase-forecast/issues/07-benchmark-modeles-ordinaux.md`
- `.scratch/severite-phase-forecast/issues/08-rapport-performance-walk-forward.md`
