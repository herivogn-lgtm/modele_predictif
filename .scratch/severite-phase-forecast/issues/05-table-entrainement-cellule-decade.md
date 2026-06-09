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

- [x] `assemble_table` : jointure features ↔ labels correcte, colonnes attendues présentes
- [x] Cible ordinale, binaire dérivé et intensité optionnelle tous présents dans la table
- [x] Cellules non prospectées présentes comme surface de prédiction (≠ absences)
- [x] Vraies absences (niveau 0) distinguées des cellules non observées
- [x] Tests dans `tests/test_06_table_entrainement_unifiee.py`

## Implementation notes (2026-06-09, /tdd)

- **`assemble_table(features, labels)`** dans `src/table_entrainement_06.py` (réécrit) :
  `features` = épine dorsale (grille 1 km × décade), LEFT join `labels` (#03) sur
  `cell_id × campagne_calc × campagne_decade`. Cellules non prospectées → label NA =
  surface de prédiction. Ancien code maille région naturelle (`rn_num`/`label` binaire,
  `build_training_table`/`join_features`/`assign_split`) **supprimé** (périmé vs #03).
- **Colonne `a_predire`** = `severite.isna()` : matérialise la surface de prédiction et
  la distingue des vraies absences (`severite=0`).
- **Split walk-forward retiré de #06** : relève de l'issue 06 (`walk_forward_split`).
- Tests : `tests/test_06_table_entrainement_unifiee.py` (4 unitaires verts + 3 intégration
  gardés par `skip` tant que le parquet de sortie est absent).
- **Dépend de #04** pour `run()` réel : tant que `05_features_engineering.parquet` reste
  à la maille `region_id` (pas `cell_id`), l'orchestration I/O ne peut pas tourner ;
  les fonctions pures sont testées sur DataFrames synthétiques cellule-maille.

## Blocked by

- `.scratch/severite-phase-forecast/issues/02-cible-ordinale-severite-phase.md`
- `.scratch/severite-phase-forecast/issues/04-features-pop-lags.md`
