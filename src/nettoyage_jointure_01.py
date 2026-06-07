"""Pipeline #01 — Nettoyage et jointure spatiale des relevés acridiens.

Charge la feuille 2001_2025_AA du XLS, filtre les coordonnées GPS aberrantes,
effectue une double jointure spatiale (région naturelle + aire grégarigène),
et sauvegarde le résultat en Parquet géoréférencé.
"""

from pathlib import Path
import pandas as pd
import geopandas as gpd
import xlrd as _xlrd

DATA_DIR = Path(__file__).parent.parent / "data"
XLS_PATH = DATA_DIR / "2001_2026_Acrido_vf.xls"
SHP_RN = DATA_DIR / "region_naturelle" / "region_naturelle.shp"
SHP_AG = DATA_DIR / "aire_gregarigene" / "aire_gregarigene.shp"
OUT_PARQUET = DATA_DIR / "processed" / "01_releves_nettoyes.parquet"

MADA_LAT = (-26.0, -11.0)
MADA_LNG = (43.0, 51.0)

# Offset de mois dans la campagne (octobre = mois 1, juillet = mois 10)
CAMPAIGN_MONTH_OFFSET = {10: 1, 11: 2, 12: 3, 1: 4, 2: 5, 3: 6, 4: 7, 5: 8, 6: 9, 7: 10}


def _excel_serial_to_datetime(val) -> pd.Timestamp:
    if pd.isna(val):
        return pd.NaT
    if isinstance(val, (int, float)):
        return pd.Timestamp(_xlrd.xldate_as_datetime(float(val), 0))
    return pd.Timestamp(val)


def compute_campagne(date: pd.Timestamp):
    """Retourne la campagne acridienne au format 'YYYY-YYYY+1', ou None pour août-septembre."""
    if pd.isna(date):
        return None
    m, y = date.month, date.year
    if m >= 10:
        return f"{y}-{y + 1}"
    if 1 <= m <= 7:
        return f"{y - 1}-{y}"
    return None  # mois 8-9 : période inter-campagne


def compute_temporal_fields(date: pd.Timestamp) -> dict:
    """Retourne decade_intra (1-3) et campagne_decade (1-30) depuis la date du relevé."""
    if pd.isna(date):
        return {"decade_intra": None, "campagne_decade": None}
    day, month = date.day, date.month
    decade_intra = 1 if day <= 10 else (2 if day <= 20 else 3)
    offset = CAMPAIGN_MONTH_OFFSET.get(month)
    campagne_decade = (offset - 1) * 3 + decade_intra if offset is not None else None
    return {"decade_intra": decade_intra, "campagne_decade": campagne_decade}


def run():
    # 1. Chargement XLS — engine xlrd obligatoire pour le format .xls (BIFF8)
    df = pd.read_excel(XLS_PATH, sheet_name="2001_2025_AA", engine="xlrd")
    print(f"XLS charge : {len(df)} lignes x {len(df.columns)} colonnes")

    # 2. Suppression des colonnes NSE (hors périmètre LMC)
    nse_cols = [c for c in df.columns if "_NSE" in str(c) or c == "NSE.Sup_inf"]
    df = df.drop(columns=nse_cols)
    print(f"  {len(nse_cols)} colonnes _NSE supprimees -> {len(df.columns)} colonnes restantes")

    # 3. Conversion de Date_ (serial Excel float → datetime)
    df["date"] = df["Date_"].apply(_excel_serial_to_datetime)

    # 4. Filtrage GPS hors-Madagascar
    n_before = len(df)
    nan_mask = df["LAT_DD"].isna() | df["LNG_DD"].isna()
    oob_mask = ~nan_mask & (
        ~df["LAT_DD"].between(*MADA_LAT) | ~df["LNG_DD"].between(*MADA_LNG)
    )
    valid = ~nan_mask & ~oob_mask
    print(
        f"GPS filtres : {nan_mask.sum()} NaN + {oob_mask.sum()} hors-bornes"
        f" = {(~valid).sum()} lignes ecartees sur {n_before}"
    )
    df = df[valid].copy()

    # 5. Renommages avant enrichissement spatial
    rename_map = {"Campagne": "campagne_xls"}
    for col_src, col_dst in [("Sol larve", "Sol_larve"), ("Trans larve", "Trans_larve"), ("Greg larve", "Greg_larve")]:
        if col_src in df.columns:
            rename_map[col_src] = col_dst
    df = df.rename(columns=rename_map)

    # 6. Création du GeoDataFrame — X=longitude, Y=latitude (ordre critique)
    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["LNG_DD"], df["LAT_DD"]), crs="EPSG:4326"
    )

    # 7. Jointure spatiale 1 : région naturelle (unité de modélisation)
    rn = gpd.read_file(SHP_RN)[["rn_nom", "rn_num", "geometry"]]
    gdf = gpd.sjoin(gdf, rn, how="left", predicate="within").drop(columns=["index_right"])
    gdf = gdf.reset_index(drop=True)

    # 8. Jointure spatiale 2 : aire grégarigène
    ag = gpd.read_file(SHP_AG)[["AIRE_NOM", "AIRE_CODE", "SECT_NOM", "SECT_NO", "geometry"]]
    gdf = gpd.sjoin(gdf, ag, how="left", predicate="within").drop(columns=["index_right"])
    gdf = gdf.reset_index(drop=True)
    gdf["hors_aire"] = gdf["AIRE_NOM"].isna()

    # 9. Colonnes temporelles dérivées depuis date (source de vérité vs Decade/Mois_ du XLS)
    gdf["campagne_calc"] = gdf["date"].apply(compute_campagne)
    temporal = gdf["date"].apply(compute_temporal_fields).apply(pd.Series)
    gdf[["decade_intra", "campagne_decade"]] = temporal

    # Vérification non-bloquante : écart entre Decade XLS (absolu 1-36) et date
    if "Decade" in gdf.columns:
        derived = ((gdf["Decade"] - 1) % 3 + 1)
        mismatch = (derived != gdf["decade_intra"]) & gdf["decade_intra"].notna() & gdf["Decade"].notna()
        n_mm = int(mismatch.sum())
        if n_mm:
            print(f"  AVERTISSEMENT : {n_mm} lignes avec Decade/Date_ incoherents -- Date_ utilisee")

    # Conversion rn_num en entier nullable pour les pipelines avals
    gdf["rn_num"] = pd.to_numeric(gdf["rn_num"], errors="coerce").astype("Int64")

    # 10. Sauvegarde Parquet géoréférencé
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUT_PARQUET, index=False)

    n_hors_aire = int(gdf["hors_aire"].sum())
    n_sans_region = int(gdf["rn_num"].isna().sum())
    print(f"  Hors aire_gregarigene : {n_hors_aire} releves")
    print(f"  Sans region naturelle : {n_sans_region} releves")
    print(f"Sortie : {OUT_PARQUET}")
    print(f"  {len(gdf)} lignes x {len(gdf.columns)} colonnes")


if __name__ == "__main__":
    run()
