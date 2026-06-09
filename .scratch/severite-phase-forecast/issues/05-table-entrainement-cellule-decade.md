# 05 — Table d'entraînement cellule × décade + surface de prédiction (Pipeline 06)

Status: ready-for-agent

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Assembler la table d'entraînement unifiée à la maille **cellule 1 km × décade** :
features laggées (issue 04) + **cible ordinale 0–3** + binaire dérivé + intensité optionnelle
(issue 02).

Inclure la **surface de prédiction** : les cellules non prospectées sont des lignes à
**prédire** (covariables présentes, label inconnu), et **non** des absences. Les vraies
absences (relevé à zéro partout, niveau 0) restent distinctes des cellules non observées.

## Acceptance criteria

- [ ] `assemble_table` : jointure features ↔ labels correcte, colonnes attendues présentes
- [ ] Cible ordinale, binaire dérivé et intensité optionnelle tous présents dans la table
- [ ] Cellules non prospectées présentes comme surface de prédiction (≠ absences)
- [ ] Vraies absences (niveau 0) distinguées des cellules non observées
- [ ] Tests dans `tests/test_06_table_entrainement_unifiee.py`

## Blocked by

- `.scratch/severite-phase-forecast/issues/02-cible-ordinale-severite-phase.md`
- `.scratch/severite-phase-forecast/issues/04-features-pop-lags.md`
