"""Pipeline #06 — Table d'entraînement unifiée à la maille cellule 1 km × décade.

Assemble la table que consomment les pipelines modèles (07/08) :
  - les **features** (#05) forment l'épine dorsale : toute la grille 1 km × décades,
    covariables environnementales, POP, lags et `AIRE_CODE` ;
  - les **labels** (#03) — `severite` 0–3, `binaire` dérivé, `intensite` optionnelle —
    sont joints en LEFT sur `cell_id × campagne_calc × campagne_decade`.

Les cellules **non prospectées** restent présentes avec leurs covariables mais sans
label : c'est la **surface de prédiction** (à prédire), distincte des **vraies absences**
(`severite=0`, relevé à zéro). Le découpage walk-forward (split train/validation) relève
de l'issue #06 (`walk_forward_split`), pas de ce pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR    = Path(__file__).parent.parent / "data"
IN_LABELS   = DATA_DIR / "processed" / "03_labels_cellule_decade.parquet"
IN_FEATURES = DATA_DIR / "processed" / "05_features_engineering.parquet"
OUT_PARQUET = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"

KEYS = ["cell_id", "campagne_calc", "campagne_decade"]


def assemble_table(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Assemble la table cellule × décade : features (épine) ⟵ labels (LEFT join).

    Chaque ligne de `features` (grille 1 km × décade) est conservée ; les colonnes
    de label (`severite`, `binaire`, `intensite`, `effort_prospection`) sont
    rattachées quand la cellule a été prospectée, NA sinon (surface de prédiction).

    Une colonne booléenne `a_predire` matérialise la surface de prédiction
    (`severite` NA) et la distingue des **vraies absences** (`severite=0`).
    """
    table = features.merge(labels, on=KEYS, how="left")
    table["a_predire"] = table["severite"].isna()
    return table


def run() -> None:
    """Orchestration I/O : lit features (#05) + labels (#03), assemble, persiste.

    Note : requiert un parquet #05 à la maille `cell_id` (issue #04). Tant que #05
    reste à la maille région naturelle, l'assemblage ne peut pas tourner ici.
    """
    print(f"Chargement features : {IN_FEATURES}")
    features = pd.read_parquet(IN_FEATURES)
    print(f"Chargement labels   : {IN_LABELS}")
    labels = pd.read_parquet(IN_LABELS)

    table = assemble_table(features, labels)

    n_pred = int(table["a_predire"].sum())
    n_obs  = len(table) - n_pred
    print(f"Table : {len(table)} lignes × {len(table.columns)} colonnes")
    print(f"  observées : {n_obs} | surface de prédiction : {n_pred}")
    print("\nDistribution sévérité (observées) :")
    print(table["severite"].value_counts(dropna=False).sort_index().to_string())

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(OUT_PARQUET, index=False)
    print(f"\nSortie : {OUT_PARQUET}")


if __name__ == "__main__":
    run()
