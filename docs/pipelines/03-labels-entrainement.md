# Pipeline #03 — Cible ordinale sévérité-phase (cellule 1 km × décade)

**Script** : `src/labels_entrainement_03.py`
**Entrée** : `data/processed/02_gregarite_potentiel.parquet`
**Sortie** : `data/processed/03_labels_cellule_decade.parquet`
**Durée estimée** : < 2 minutes
**Dépendance obligatoire** : Pipeline [#02](02-gregarite-potentiel.md)

---

## Objectif

Agréger les relevés acridiens individuels en **cible ordinale sévérité-phase 0–3** à la maille `cell_id × campagne_calc × campagne_decade` ([ADR 0001](../adr/0001-cible-ordinale-severite-phase.md)). La sévérité d'une cellule × décade est la **phase maximale observée** (imago + larve) : le pire stade présent gouverne le risque.

- `0` vraie absence (relevé à zéro partout) · `1` solitaire · `2` transiens · `3` grégaire.
- `pd.NA` si **aucune phase observée** — une cellule non prospectée **n'est pas une absence**.

Sont aussi produits le **binaire dérivé** (présence = sévérité ≥ 1, conservé pour l'AUC, exigence thèse §31/§33) et l'**intensité optionnelle** (`log1p` de la densité, jamais bloquante, ~35 % NaN).

> Seules les cellules × décades **effectivement prospectées** sont émises ici. La surface de prédiction (cellules non prospectées) est assemblée en aval ([#06](06-table-entrainement.md)). La fenêtre 2001–2026 est conservée intégralement, sans couper les années grégaires précoces (2004/2007/2008, [ADR 0004](../adr/0004-fenetre-entrainement-complete.md)).

---

## Entrées

| Fichier | Colonnes clés utilisées |
|---------|-------------------------|
| `data/processed/02_gregarite_potentiel.parquet` | `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, `Sol`, `Trans`, `Greg` (+ larves), densités |

---

## Sorties

| Fichier | Colonnes |
|---------|----------|
| `data/processed/03_labels_cellule_decade.parquet` | `cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`, `severite` (0–3 / NA), `binaire`, `intensite`, `effort_prospection` |

---

## Fonctions pures (testées — `tests/test_03_labels_entrainement.py`)

| Fonction | Rôle |
|----------|------|
| `compute_severite(group_df)` | Sévérité ordinale 0–3 = phase max ; NA si rien d'observé (≠ zéro) |
| `compute_intensite(group_df)` | `log1p` de la densité moyenne (optionnelle) |
| `derive_binary(severite)` | Binaire présence dérivé = (sévérité ≥ 1) |
| `aggregate_per_cell(df)` | Agrège plusieurs relevés d'une même cellule × décade par la phase max |

---

## Lancement

```bash
./.venv/bin/python src/labels_entrainement_03.py
```

## Aval

Les labels sont joints aux features environnementales dans le pipeline [#06](06-table-entrainement.md). `severite_lag1/_lag2` sont calculés à partir de ce fichier dans le pipeline [#05](05-feature-engineering.md).
