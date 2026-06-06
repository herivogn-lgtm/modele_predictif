"""Pipeline #06 — Table d'entraînement ML unifiée.

Joint la table de labels (#03) avec la table de features environnementales et
dérivées (#05) sur la clé (rn_num × campagne_calc × campagne_decade), ajoute
la colonne split pour le découpage walk-forward et persiste le panel ML complet
en Parquet.

Découpage temporel walk-forward :
  "train"      — campagnes 2001-02 à 2015-16, label non-NA uniquement
  "validation" — campagnes 2016-17 et au-delà avec label non-NA
  "inference"  — label = NA (dont campagne 2023-24 exclue)

Si le parquet #05 est absent (GEE non exécuté), la table est produite avec
les colonnes labels uniquement, ce qui permet de vérifier tous les critères
structurels sans GEE.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

DATA_DIR    = Path(__file__).parent.parent / "data"
IN_LABELS   = DATA_DIR / "processed" / "03_labels_region_decade.parquet"
IN_FEATURES = DATA_DIR / "processed" / "05_features_engineering.parquet"
IN_GEO      = DATA_DIR / "processed" / "02_gregarite_potentiel.parquet"
OUT_PARQUET = DATA_DIR / "processed" / "06_table_entrainement_unifiee.parquet"

TRAIN_END_YEAR = 2015   # dernière campagne d'entraînement : 2015-2016
# Campagnes avec label non-NA et start_year > TRAIN_END_YEAR → validation


def assign_split(campagne_calc: str, label) -> str:
    """Retourne le split walk-forward pour une cellule (campagne_calc, label).

    "inference" si label est NA (cellule non prospectée ou campagne exclue).
    "train"     si label connu ET campagne démarre en ≤ TRAIN_END_YEAR.
    "validation" sinon (label connu ET campagne démarre après TRAIN_END_YEAR).
    """
    if pd.isna(label):
        return "inference"
    start_year = int(str(campagne_calc).split("-")[0])
    return "train" if start_year <= TRAIN_END_YEAR else "validation"


def _mode_first(series: pd.Series):
    """Première valeur du mode d'une série ; pd.NA si série vide ou tout-NaN."""
    m = series.dropna().mode()
    return m.iloc[0] if len(m) > 0 else pd.NA


def aggregate_gregarite(geo_path: Path) -> pd.DataFrame:
    """Agrège depuis le parquet #02 le potentiel et le niveau de grégarité dominant.

    Retourne un DataFrame (rn_num, campagne_calc, campagne_decade,
    potentiel_acridien_dominant, niveau_gregarite_dominant).
    """
    gdf = gpd.read_parquet(geo_path)

    valid = gdf[
        gdf["rn_num"].notna()
        & gdf["campagne_calc"].notna()
        & gdf["campagne_decade"].notna()
    ].copy()
    valid["rn_num"] = valid["rn_num"].astype("Int64")

    agg = (
        valid.groupby(
            ["rn_num", "campagne_calc", "campagne_decade"],
            observed=True,
            dropna=False,
        )
        .apply(
            lambda g: pd.Series({
                "potentiel_acridien_dominant": _mode_first(g["potentiel_acridien"]),
                "niveau_gregarite_dominant":   _mode_first(g["niveau_gregarite"]),
            }),
            include_groups=False,
        )
        .reset_index()
    )

    agg["campagne_decade"] = agg["campagne_decade"].astype(int)
    return agg


def join_features(labels: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Joint les features (#05) sur la table de labels (#03).

    Harmonise les noms de clés : region_id→rn_num, campaign→campagne_calc,
    decade_num→campagne_decade. Supprime les colonnes temporelles redondantes.
    """
    features = features.rename(columns={
        "region_id":  "rn_num",
        "campaign":   "campagne_calc",
        "decade_num": "campagne_decade",
    }).copy()

    features["rn_num"] = features["rn_num"].astype("Int64")
    features["campagne_decade"] = features["campagne_decade"].astype(int)

    drop_cols = [c for c in ("year", "month", "decade_part", "date_end", "region_nom")
                 if c in features.columns]
    features = features.drop(columns=drop_cols)

    return labels.merge(
        features,
        on=["rn_num", "campagne_calc", "campagne_decade"],
        how="left",
    )


def build_training_table(
    labels_path: Path,
    features_path: Path | None = None,
    geo_path: Path | None = None,
) -> pd.DataFrame:
    """Construit la table ML unifiée.

    Paramètres
    ----------
    labels_path   : Parquet #03 (obligatoire)
    features_path : Parquet #05 (optionnel — ignoré si absent ou None)
    geo_path      : Parquet #02 (optionnel — pour potentiel + niveau grégarité)

    Colonnes garanties en sortie :
    rn_num, rn_nom, campagne_calc, campagne_decade, split,
    effort_prospection, label
    """
    df = pd.read_parquet(labels_path)

    if features_path is not None:
        if Path(features_path).exists():
            features = pd.read_parquet(features_path)
            df = join_features(df, features)
        else:
            warnings.warn(
                f"Parquet features absent ({features_path}) — "
                "table produite avec labels uniquement.",
                stacklevel=2,
            )

    if geo_path is not None:
        if Path(geo_path).exists():
            geo_agg = aggregate_gregarite(Path(geo_path))
            df = df.merge(
                geo_agg,
                on=["rn_num", "campagne_calc", "campagne_decade"],
                how="left",
            )
        else:
            warnings.warn(
                f"Parquet grégarité absent ({geo_path}) — colonnes omises.",
                stacklevel=2,
            )

    df["split"] = [
        assign_split(c, l)
        for c, l in zip(df["campagne_calc"], df["label"])
    ]

    # Aucune cellule labellisée ne doit être masquée
    labeled_mask = df["split"].isin({"train", "validation"})
    assert df.loc[labeled_mask, "label"].notna().all(), (
        "Des cellules split=train/validation ont label=NA"
    )

    # Aucune campagne ne doit être à la fois dans train et validation
    split_per_camp = df.groupby("campagne_calc")["split"].apply(
        lambda s: frozenset(s.unique())
    )
    leaked = split_per_camp[
        split_per_camp.apply(lambda s: "train" in s and "validation" in s)
    ]
    assert len(leaked) == 0, (
        f"Campagnes présentes dans train ET validation : {list(leaked.index)}"
    )

    key_cols     = ["rn_num", "rn_nom", "campagne_calc", "campagne_decade"]
    meta_cols    = ["split", "effort_prospection", "label"]
    optional_cols = [c for c in ("potentiel_acridien_dominant", "niveau_gregarite_dominant")
                     if c in df.columns]
    feature_cols = [
        c for c in df.columns
        if c not in key_cols + meta_cols + optional_cols
    ]
    ordered = key_cols + meta_cols + optional_cols + feature_cols
    return df[[c for c in ordered if c in df.columns]]


def run() -> None:
    print(f"Chargement labels : {IN_LABELS}")
    df = build_training_table(
        labels_path=IN_LABELS,
        features_path=IN_FEATURES,
        geo_path=IN_GEO,
    )

    print(f"Table ML : {len(df)} lignes × {len(df.columns)} colonnes")
    print("\nDistribution split × label :")
    print(df.groupby("split")["label"].value_counts(dropna=False).to_string())

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"\nSortie : {OUT_PARQUET}")


if __name__ == "__main__":
    run()
