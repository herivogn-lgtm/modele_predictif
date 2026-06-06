"""Pipeline #05 — Feature engineering acridologique.

À partir des variables environnementales GEE (#04), calcule :
  - pop_consecutive   : compteur mensuel de mois consécutifs en Plage d'Optimum
                        Pluviométrique (CHIRPS 50–125 mm/mois), réinitialisé par campagne
  - *_lag1d / _lag2d / _lag1m : lags temporels décadaires (D-1, D-2, M-1) sans fuite
  - *_spatial_lag     : moyenne des régions naturelles contiguës (topologie shapefile)

Sortie : data/processed/05_features_engineering.parquet
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
SHP_RN   = DATA_DIR / "region_naturelle" / "region_naturelle.shp"
IN_PATH  = DATA_DIR / "processed" / "04_variables_environnementales.parquet"
OUT_PATH = DATA_DIR / "processed" / "05_features_engineering.parquet"

POP_MIN = 50    # mm/mois, borne inférieure de la Plage d'Optimum Pluviométrique
POP_MAX = 125   # mm/mois, borne supérieure

TEMPORAL_LAG_FEATURES = [
    "chirps_sum_mean",
    "ndvi_mean",
    "evi_mean",
    "lst_mean",
    "soil_moisture_mean",
]

SPATIAL_LAG_FEATURES = [
    "chirps_sum_mean",
    "ndvi_mean",
    "evi_mean",
    "lst_mean",
    "soil_moisture_mean",
]


# ── 1. Compteur POP ────────────────────────────────────────────────────────────

def consecutive_counter(series: pd.Series) -> pd.Series:
    """Compteur de valeurs True consécutives, remis à 0 à chaque rupture ou NaN.

    Entrée : série booléenne (True = mois en POP).
    Sortie : série entière, même index que l'entrée.
    """
    result = []
    count = 0
    for v in series:
        if pd.isna(v) or not bool(v):
            count = 0
        else:
            count += 1
        result.append(count)
    return pd.Series(result, index=series.index)


def compute_pop(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute la colonne pop_consecutive au DataFrame.

    Agrège les décades → mois, applique le compteur consécutif POP par
    (region_id × campagne), puis rejoint au DataFrame décadaire d'origine.
    Les 3 décades d'un même mois partagent la même valeur.
    """
    # Agrégation décadaire → mensuelle (somme des 3 décades du mois)
    monthly = (
        df.groupby(["region_id", "campaign", "year", "month"], sort=True)["chirps_sum_mean"]
        .sum()
        .reset_index()
        .rename(columns={"chirps_sum_mean": "chirps_monthly_sum"})
    )

    # Flag POP : borne incluse (between est fermé par défaut dans pandas)
    monthly["in_pop"] = monthly["chirps_monthly_sum"].between(POP_MIN, POP_MAX)

    # Tri chronologique dans chaque groupe (year, month assure l'ordre oct→juil)
    monthly = monthly.sort_values(["region_id", "campaign", "year", "month"]).reset_index(drop=True)

    # Compteur consécutif par (region_id × campaign) — réinitialisation à la rupture de campagne
    monthly["pop_consecutive"] = (
        monthly.groupby(["region_id", "campaign"])["in_pop"]
        .transform(consecutive_counter)
    )

    # Jointure vers le df décadaire (les 3 décades d'un mois héritent la même valeur)
    pop_cols = monthly[["region_id", "campaign", "year", "month", "pop_consecutive"]]
    result = df.merge(pop_cols, on=["region_id", "campaign", "year", "month"], how="left")
    return result


# ── 2. Lags temporels ─────────────────────────────────────────────────────────

def compute_temporal_lags(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les lags D-1, D-2 et M-1 pour chaque feature de TEMPORAL_LAG_FEATURES.

    Le tri est effectué sur date_start (datetime) pour garantir l'ordre multi-campagne.
    Aucune valeur future n'est utilisée : shift(k) décale vers le passé.
    """
    df = df.sort_values(["region_id", "date_start"]).reset_index(drop=True)

    for feat in TEMPORAL_LAG_FEATURES:
        if feat not in df.columns:
            continue
        grp = df.groupby("region_id", sort=False)[feat]
        df[f"{feat}_lag1d"] = grp.shift(1)
        df[f"{feat}_lag2d"] = grp.shift(2)
        df[f"{feat}_lag1m"] = grp.shift(3)

    return df


# ── 3. Lags spatiaux ──────────────────────────────────────────────────────────

def build_neighbor_dict(shp_path: Path) -> dict[int, list[int]]:
    """Construit la matrice d'adjacence topologique depuis le shapefile.

    Utilise shapely .touches() : deux polygones sont voisins s'ils partagent
    au moins un point de frontière (contiguïté Queen). Pas de buffer distance.
    """
    gdf = gpd.read_file(shp_path)[["rn_num", "geometry"]]
    gdf["rn_num"] = gdf["rn_num"].astype(int)
    geoms = gdf.set_index("rn_num")["geometry"]

    neighbors: dict[int, list[int]] = {}
    for rid, geom in geoms.items():
        neighbors[rid] = [
            other for other, other_geom in geoms.items()
            if other != rid and geom.touches(other_geom)
        ]

    return neighbors


def compute_spatial_lags(
    df: pd.DataFrame,
    neighbors: dict[int, list[int]],
    features: list[str],
) -> pd.DataFrame:
    """Ajoute la moyenne des régions contiguës pour chaque feature.

    Stratégie : pivot (date_start × region_id) pour vectoriser le calcul,
    puis melt et merge vers le DataFrame d'origine.
    Régions sans voisin → NaN (aucune erreur).
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue
        col_name = f"{feat}_spatial_lag"

        # Pivot temporaire : lignes = instants, colonnes = régions
        pivot = df.pivot_table(
            index="date_start", columns="region_id", values=feat, aggfunc="first"
        )

        lag_series: dict[int, pd.Series] = {}
        for rid in pivot.columns:
            nbrs = [n for n in neighbors.get(int(rid), []) if n in pivot.columns]
            if nbrs:
                lag_series[rid] = pivot[nbrs].mean(axis=1, skipna=True)
            else:
                lag_series[rid] = pd.Series(float("nan"), index=pivot.index)

        lag_df = (
            pd.DataFrame(lag_series)
            .rename_axis("date_start")
            .reset_index()
            .melt(id_vars="date_start", var_name="region_id", value_name=col_name)
        )
        lag_df["region_id"] = lag_df["region_id"].astype(int)

        df = df.merge(lag_df, on=["date_start", "region_id"], how="left")

    return df


# ── 4. Point d'entrée ─────────────────────────────────────────────────────────

def run() -> None:
    print(f"Chargement {IN_PATH} ...")
    df = pd.read_parquet(IN_PATH)
    print(f"  {len(df)} lignes × {len(df.columns)} colonnes")

    # Assure que date_start est bien un datetime (parquet peut le préserver ou non)
    df["date_start"] = pd.to_datetime(df["date_start"])

    print("Calcul du compteur POP consécutifs ...")
    df = compute_pop(df)

    print("Calcul des lags temporels (D-1, D-2, M-1) ...")
    df = compute_temporal_lags(df)

    print(f"Construction de la matrice d'adjacence ({SHP_RN}) ...")
    neighbors = build_neighbor_dict(SHP_RN)
    n_with_neighbors = sum(1 for v in neighbors.values() if v)
    print(f"  {n_with_neighbors}/{len(neighbors)} régions ont au moins un voisin contigu")

    print("Calcul des lags spatiaux ...")
    df = compute_spatial_lags(df, neighbors, SPATIAL_LAG_FEATURES)

    # Tri final par region_id, date_start pour la cohérence downstream
    df = df.sort_values(["region_id", "date_start"]).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)

    print(f"\nSortie : {OUT_PATH}")
    print(f"  {len(df)} lignes × {len(df.columns)} colonnes")

    new_cols = [c for c in df.columns if any(
        c.endswith(sfx) for sfx in ("_lag1d", "_lag2d", "_lag1m", "_spatial_lag")
    ) or c == "pop_consecutive"]
    nan_stats = df[new_cols].isna().mean().round(3)
    print("\nTaux de NaN des nouvelles features :")
    print(nan_stats.to_string())


if __name__ == "__main__":
    run()
