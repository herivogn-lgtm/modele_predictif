"""Pipeline #03 — Agrégation en labels d'entraînement par région naturelle × décade.

Charge le Parquet enrichi (pipeline #02), agrège les relevés par cellule
(rn_num × campagne_calc × campagne_decade) et produit trois états de label :
  - 1 (présence)        : au moins une ligne a Sol+Trans+Greg > 0
  - 0 (absence vérifiée): toutes les lignes ont Sol=Trans=Greg=0
  - NA (masqué)         : aucune ligne de prospection pour cette cellule
La campagne 2023-2024 est exclue des labels (NA) mais conservée pour l'inférence.
"""

from __future__ import annotations

import pandas as pd
import geopandas as gpd
from pathlib import Path

DATA_DIR    = Path(__file__).parent.parent / "data"
IN_PARQUET  = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"
OUT_PARQUET = DATA_DIR / "processed" / "03_labels_region_decade.parquet"
SHP_RN      = DATA_DIR / "region_naturelle" / "region_naturelle.shp"

_EXCLUDED_CAMPAIGNS = {"2023-2024"}


def load_rn_reference(shp_path: Path) -> pd.DataFrame:
    """Catalogue (rn_num, rn_nom) des 90 régions naturelles depuis le shapefile."""
    rn_ref = gpd.read_file(shp_path)[["rn_num", "rn_nom"]].copy()
    rn_ref["rn_num"] = rn_ref["rn_num"].astype("Int64")
    assert rn_ref["rn_num"].is_unique, "rn_num doit être unique dans le shapefile région naturelle"
    return rn_ref.sort_values("rn_num").reset_index(drop=True)


def compute_label(group_df: pd.DataFrame) -> int:
    """Label de présence/absence pour un groupe de lignes d'une même cellule.

    Retourne 1 si au moins une ligne a Sol+Trans+Greg > 0, 0 sinon.
    NaN dans les comptages est traité comme 0 (conservateur : évite les faux positifs).
    Le cas masqué (aucune ligne) est géré en aval au niveau de la grille.
    """
    totals = (
        group_df["Sol"].fillna(0)
        + group_df["Trans"].fillna(0)
        + group_df["Greg"].fillna(0)
    )
    return 1 if (totals > 0).any() else 0


def aggregate_per_cell(df: pd.DataFrame) -> pd.DataFrame:
    """Agrège les relevés par cellule (rn_num × campagne_calc × campagne_decade).

    Exclut les lignes sans assignation spatiale (rn_num=NA) ou temporelle
    (campagne_calc=None). Les relevés hors_aire sont conservés — ils
    constituent de vraies prospections contribuant à l'effort et aux labels.

    Retourne uniquement les cellules effectivement prospectées, sans rn_nom
    (ajouté dans build_full_grid depuis le shapefile de référence).
    """
    valid = df[
        df["rn_num"].notna()
        & df["campagne_calc"].notna()
        & df["campagne_decade"].notna()
    ].copy()

    grouped = valid.groupby(
        ["rn_num", "campagne_calc", "campagne_decade"],
        observed=True,
        dropna=False,
    )

    result = grouped.apply(
        lambda g: pd.Series({
            "label": compute_label(g),
            "effort_prospection": len(g),
        }),
        include_groups=False,
    ).reset_index()

    result["label"] = result["label"].astype("Int64")
    result["effort_prospection"] = result["effort_prospection"].astype(int)
    return result


def build_full_grid(observed_df: pd.DataFrame, rn_ref: pd.DataFrame) -> pd.DataFrame:
    """Produit cartésien (rn_num × calendrier des décades prospectées) + join des labels.

    Le calendrier est extrait de observed_df (décades réellement prospectées)
    plutôt que d'une liste théorique 1-30, pour éviter des cellules masquées
    pour des décades inexistantes dans le dataset.

    Cellules absentes du jeu observé → effort_prospection=0, label=pd.NA.
    """
    calendar = (
        observed_df[["campagne_calc", "campagne_decade"]]
        .drop_duplicates()
        .sort_values(["campagne_calc", "campagne_decade"])
        .reset_index(drop=True)
    )

    rn_ref = rn_ref.copy()
    rn_ref["_key"] = 1
    calendar["_key"] = 1
    grid = rn_ref.merge(calendar, on="_key").drop(columns="_key")

    full = grid.merge(
        observed_df[["rn_num", "campagne_calc", "campagne_decade", "label", "effort_prospection"]],
        on=["rn_num", "campagne_calc", "campagne_decade"],
        how="left",
    )

    full["effort_prospection"] = full["effort_prospection"].fillna(0).astype(int)
    full["label"] = full["label"].astype("Int64")
    # campagne_decade vient de la grille (jamais NaN) mais peut être float si le
    # parquet amont l'a converti lors de la présence de NaN dans d'autres lignes.
    full["campagne_decade"] = full["campagne_decade"].astype(int)
    return full


def apply_exclusions(
    df: pd.DataFrame,
    excluded_campaigns: set[str] = _EXCLUDED_CAMPAIGNS,
) -> pd.DataFrame:
    """Met label=NA pour les campagnes exclues ; conserve effort_prospection."""
    df = df.copy()
    df.loc[df["campagne_calc"].isin(excluded_campaigns), "label"] = pd.NA
    return df


def run() -> None:
    gdf = gpd.read_parquet(IN_PARQUET)
    print(f"Parquet chargé : {len(gdf)} lignes x {len(gdf.columns)} colonnes")

    rn_ref = load_rn_reference(SHP_RN)
    print(f"Référentiel régions naturelles : {len(rn_ref)} régions")

    labels_observed = aggregate_per_cell(gdf)
    print(f"Cellules observées : {len(labels_observed)}")

    labels_full = build_full_grid(labels_observed, rn_ref)
    print(f"Grille complète : {len(labels_full)} cellules")

    labels_final = apply_exclusions(labels_full)

    # Sanité : aucune cellule sans effort ne doit avoir un label non-NA
    assert (
        labels_final[labels_final["effort_prospection"] == 0]["label"].isna().all()
    ), "Des cellules sans prospection ont un label non-NA"

    # Sanité : cellules avec effort > 0 et label=NA → uniquement campagnes exclues
    unlabeled_with_effort = labels_final[
        (labels_final["effort_prospection"] > 0) & labels_final["label"].isna()
    ]
    assert unlabeled_with_effort["campagne_calc"].isin(_EXCLUDED_CAMPAIGNS).all(), (
        "Des cellules prospectées ont label=NA hors campagnes exclues"
    )

    output_cols = ["rn_num", "rn_nom", "campagne_calc", "campagne_decade",
                   "effort_prospection", "label"]
    labels_final = labels_final[output_cols]

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    labels_final.to_parquet(OUT_PARQUET, index=False)

    n_presence = int((labels_final["label"] == 1).sum())
    n_absence  = int((labels_final["label"] == 0).sum())
    n_masque   = int(labels_final["label"].isna().sum())
    print(f"Distribution labels : présence={n_presence}, absence={n_absence}, masqué={n_masque}")
    print(f"Sortie : {OUT_PARQUET}")
    print(f"  {len(labels_final)} lignes x {len(labels_final.columns)} colonnes")


if __name__ == "__main__":
    run()
