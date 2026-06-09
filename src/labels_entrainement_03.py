"""Pipeline #03 — Cible ordinale sévérité-phase à la maille cellule 1 km × décade.

Charge le Parquet enrichi (pipeline #02) et agrège les relevés par
cellule (`cell_id` × `campagne_calc` × `campagne_decade`) en produisant :
  - `severite`  : ordinale 0–3 = phase maximale observée (imago + larve)
                  (0 vraie absence, 1 solitaire, 2 transiens, 3 grégaire ;
                   pd.NA si aucune phase observée — non observé ≠ absence) ;
  - `binaire`   : présence dérivée (sévérité ≥ 1), conservée pour l'AUC ;
  - `intensite` : log1p de la densité moyenne, optionnelle et non bloquante.

Seules les cellules × décades effectivement prospectées sont émises ; la
surface de prédiction (cellules non prospectées) est assemblée en aval
(pipeline #06). La fenêtre 2001–2026 est conservée intégralement, sans couper
les années grégaires précoces (2004/2007/2008).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path

DATA_DIR    = Path(__file__).parent.parent / "data"
IN_PARQUET  = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"
OUT_PARQUET = DATA_DIR / "processed" / "03_labels_cellule_decade.parquet"


_PHASE_LEVELS = (
    (3, ("Greg", "Greg_larve")),
    (2, ("Trans", "Trans_larve")),
    (1, ("Sol", "Sol_larve")),
)


def compute_severite(group_df: pd.DataFrame):
    """Sévérité-phase ordinale 0–3 = phase maximale observée dans le groupe.

    3 si `Greg`/`Greg_larve` > 0 ; 2 si `Trans`/`Trans_larve` > 0 ;
    1 si `Sol`/`Sol_larve` > 0 ; 0 si tous les comptages observés sont nuls
    (vraie absence). NaN ≠ zéro : si **aucune** valeur de phase n'est observée
    (tout NaN), retourne pd.NA (non observé, pas une absence vérifiée).
    """
    cols = [c for _, pair in _PHASE_LEVELS for c in pair]
    present = group_df[cols]
    if present.notna().to_numpy().sum() == 0:
        return pd.NA
    for level, pair in _PHASE_LEVELS:
        if (present[list(pair)].fillna(0) > 0).to_numpy().any():
            return level
    return 0


def compute_intensite(group_df: pd.DataFrame) -> float:
    """Intensité optionnelle = log1p de la densité imago moyenne du groupe.

    Source : `densite_imago` (ind/ha, pipeline #02). La moyenne ignore les
    valeurs manquantes ; si la densité est absente partout (~35 % des relevés),
    retourne NaN — jamais bloquant. log1p évite log(0) = -inf pour une densité
    nulle.
    """
    mean = group_df["densite_imago"].mean()  # skipna par défaut → NaN si tout NaN
    if pd.isna(mean):
        return float("nan")
    return float(np.log1p(mean))


def derive_binary(severite):
    """Binaire présence/absence dérivé de la sévérité : ≥ 1 → 1, 0 → 0, NA → NA.

    Conservé pour l'AUC exigée par la thèse.
    """
    if pd.isna(severite):
        return pd.NA
    return 1 if severite >= 1 else 0


_CELL_KEYS = ["cell_id", "campagne_calc", "campagne_decade"]


def aggregate_per_cell(df: pd.DataFrame) -> pd.DataFrame:
    """Agrège les relevés à la maille cellule 1 km × décade.

    Clé : `cell_id` × `campagne_calc` × `campagne_decade`. Exclut les lignes
    sans rattachement spatial (`cell_id`=NA) ou temporel (`campagne_calc`=None,
    `campagne_decade`=NA). Pour chaque cellule × décade observée, produit :
      - `severite` : phase maximale 0–3 (`compute_severite`),
      - `binaire`  : présence dérivée ≥ 1 (`derive_binary`),
      - `intensite`: log1p densité moyenne, optionnelle (`compute_intensite`),
      - `effort_prospection` : nombre de relevés du groupe.
    """
    valid = df[
        df["cell_id"].notna()
        & df["campagne_calc"].notna()
        & df["campagne_decade"].notna()
    ].copy()

    grouped = valid.groupby(_CELL_KEYS, observed=True, dropna=False)

    result = grouped.apply(
        lambda g: pd.Series({
            "severite": compute_severite(g),
            "intensite": compute_intensite(g),
            "effort_prospection": len(g),
        }),
        include_groups=False,
    ).reset_index()

    result["severite"] = result["severite"].astype("Int64")
    result["binaire"] = result["severite"].apply(derive_binary).astype("Int64")
    result["intensite"] = result["intensite"].astype(float)
    result["effort_prospection"] = result["effort_prospection"].astype(int)
    return result


def run() -> None:
    gdf = gpd.read_parquet(IN_PARQUET)
    print(f"Parquet chargé : {len(gdf)} lignes x {len(gdf.columns)} colonnes")

    labels = aggregate_per_cell(gdf)
    print(f"Cellules × décades observées : {len(labels)}")

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(OUT_PARQUET, index=False)

    dist = labels["severite"].value_counts(dropna=False).sort_index().to_dict()
    n_intensite = int(labels["intensite"].notna().sum())
    print(f"Distribution sévérité : {dist}")
    print(f"Intensité renseignée : {n_intensite}/{len(labels)}")
    print(f"Sortie : {OUT_PARQUET}")
    print(f"  {len(labels)} lignes x {len(labels.columns)} colonnes")


if __name__ == "__main__":
    run()
