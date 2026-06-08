# 02 — Cible ordinale sévérité-phase 0–3 + binaire dérivé (Pipeline 03)

Status: ready-for-agent

## Parent

`.scratch/severite-phase-forecast/PRD.md`

## What to build

Transformer la cible binaire (`compute_label`) en **sévérité-phase ordinale 0–3** =
**phase maximale** observée dans la cellule × décade :

- 0 si relevé à zéro partout (vraie absence)
- 1 si `Sol`/`Sol larve` > 0 seuls
- 2 si `Trans`/`Trans larve` > 0
- 3 si `Greg`/`Greg larve` > 0

`aggregate_per_cell` agrège plusieurs relevés d'une même cellule × décade par la **phase max**.
Un **binaire dérivé** (sévérité ≥ 1) est conservé pour l'AUC. Une **intensité optionnelle**
`log(densité)` (`DL_*`/`DI_*`) est produite là où renseignée, **jamais bloquante** (~35 % NaN).

La fenêtre 2001–2026 est conservée intégralement (ne pas couper les années précoces qui
portent les rares exemples grégaires 2004/2007/2008).

## Acceptance criteria

- [x] `compute_severite` : cas canoniques 0/1/2/3 corrects
- [x] `compute_severite` : NaN traité différemment de zéro (tout-NaN → pd.NA)
- [x] `compute_severite` : phase max retenue quand plusieurs phases présentes
- [x] `aggregate_per_cell` : plusieurs relevés d'une cellule × décade → max
- [x] `derive_binary` : sévérité ≥ 1 → 1, sinon 0
- [x] Intensité optionnelle calculée sans bloquer la sortie quand la densité manque
- [x] Fenêtre 2001–2026 conservée (années grégaires précoces présentes)
- [x] Tests dans `tests/test_03_labels_entrainement.py`

## Blocked by

- `.scratch/severite-phase-forecast/issues/01-snap-clip-grille-1km.md`
