"""Pipeline #01 — Nettoyage et rattachement spatial des relevés acridiens.

Charge la feuille 2001_2025_AA du XLS, filtre les coordonnées GPS aberrantes,
rattache chaque relevé à sa cellule de la grille 1 km régulière (`snap_to_grid`),
clipe strictement à l'intérieur de l'aire grégarigène (`clip_to_aire`, ADR 0003),
et sauvegarde les relevés nettoyés + la grille 1 km partagée (emprise
entraînement = prédiction) en Parquet géoréférencé.
"""

from pathlib import Path
import pandas as pd
import geopandas as gpd
import xlrd as _xlrd

DATA_DIR = Path(__file__).parent.parent / "data"
XLS_PATH = DATA_DIR / "2001_2026_Acrido_vf.xls"
SHP_AG = DATA_DIR / "aire_gregarigene" / "aire_gregarigene.shp"
OUT_PARQUET = DATA_DIR / "processed" / "01_releves_nettoyes.parquet"
OUT_GRID = DATA_DIR / "processed" / "01_grille_1km.parquet"

MADA_LAT = (-26.0, -11.0)
MADA_LNG = (43.0, 51.0)

# Grille 1 km : indexée en mètres dans la projection métrique UTM 38S
# (couvre l'aire grégarigène, lon 43-48). cell_id = "col_row" sur des indices
# entiers floor(coord/cell_size) — origine = origine UTM (stable, partagée
# entre snap_to_grid et build_grid).
GRID_CRS = "EPSG:32738"
CELL_SIZE_M = 1000.0

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


def _make_cell_id(col, row):
    """Schéma d'identifiant de cellule partagé par snap_to_grid et build_grid."""
    return col.astype(str) + "_" + row.astype(str)


def snap_to_grid(points_gdf: gpd.GeoDataFrame, cell_size: float = CELL_SIZE_M) -> gpd.GeoDataFrame:
    """Rattache chaque point à sa cellule de la grille 1 km régulière.

    Reprojette en UTM 38S puis indexe par floor(coord/cell_size). Ajoute les
    colonnes `cell_col`, `cell_row` (entiers) et `cell_id` ("col_row").
    """
    out = points_gdf.copy()
    metric = out.geometry.to_crs(GRID_CRS)
    out["cell_col"] = (metric.x // cell_size).astype("int64")
    out["cell_row"] = (metric.y // cell_size).astype("int64")
    out["cell_id"] = _make_cell_id(out["cell_col"], out["cell_row"])
    return out


def clip_to_aire(points_gdf: gpd.GeoDataFrame, aire_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clip strict : ne garde que les points *within* les polygones de l'aire
    grégarigène, en rattachant `AIRE_CODE`, `SECT_NO`, `AIRE_NOM`.
    """
    cols = ["AIRE_CODE", "SECT_NO", "AIRE_NOM", "geometry"]
    aire = aire_gdf[cols].to_crs(points_gdf.crs)
    joined = gpd.sjoin(points_gdf, aire, how="inner", predicate="within")
    return joined.drop(columns=["index_right"]).reset_index(drop=True)


def build_grid(aire_gdf: gpd.GeoDataFrame, cell_size: float = CELL_SIZE_M) -> gpd.GeoDataFrame:
    """Construit la grille 1 km régulière clipée à l'intérieur des polygones.

    Une cellule est retenue si son centroïde tombe *within* un polygone de
    l'aire grégarigène ; elle hérite alors de son `AIRE_CODE`/`SECT_NO`. Les
    `cell_id` produits sont cohérents avec `snap_to_grid` (même origine UTM).
    CRS de sortie : `GRID_CRS`.
    """
    import numpy as np
    from shapely.geometry import box

    aire = aire_gdf[["AIRE_CODE", "SECT_NO", "AIRE_NOM", "geometry"]].to_crs(GRID_CRS)
    minx, miny, maxx, maxy = aire.total_bounds
    col0, col1 = int(minx // cell_size), int(maxx // cell_size)
    row0, row1 = int(miny // cell_size), int(maxy // cell_size)

    cols, rows = np.meshgrid(np.arange(col0, col1 + 1), np.arange(row0, row1 + 1))
    cols, rows = cols.ravel(), rows.ravel()
    cx = (cols + 0.5) * cell_size
    cy = (rows + 0.5) * cell_size

    centroids = gpd.GeoDataFrame(
        {"cell_col": cols, "cell_row": rows},
        geometry=gpd.points_from_xy(cx, cy), crs=GRID_CRS,
    )
    inside = gpd.sjoin(centroids, aire, how="inner", predicate="within").drop(columns=["index_right"])
    inside = inside.drop_duplicates(subset=["cell_col", "cell_row"]).reset_index(drop=True)

    inside["cell_id"] = _make_cell_id(inside["cell_col"], inside["cell_row"])
    inside["geometry"] = [
        box(c * cell_size, r * cell_size, (c + 1) * cell_size, (r + 1) * cell_size)
        for c, r in zip(inside["cell_col"], inside["cell_row"])
    ]
    return inside.set_geometry("geometry")


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

    # 7. Snap point → cellule 1 km (grille régulière UTM 38S)
    gdf = snap_to_grid(gdf)

    # 8. Clip strict à l'intérieur de l'aire grégarigène (rattache AIRE_CODE/SECT_NO)
    #    Remplace l'ancienne double jointure région naturelle + aire (ADR 0003).
    ag = gpd.read_file(SHP_AG)
    n_before_clip = len(gdf)
    gdf = clip_to_aire(gdf, ag)
    print(
        f"Clip aire_gregarigene : {n_before_clip - len(gdf)} releves hors polygones ecartes"
        f" -> {len(gdf)} conserves"
    )

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

    # 10. Sauvegarde Parquet géoréférencé (relevés nettoyés clipés)
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(OUT_PARQUET, index=False)
    print(f"Sortie relevés : {OUT_PARQUET}")
    print(f"  {len(gdf)} lignes x {len(gdf.columns)} colonnes")

    # 11. Grille 1 km partagée (emprise entraînement = prédiction)
    grid = build_grid(ag)
    grid.to_parquet(OUT_GRID, index=False)
    print(f"Sortie grille : {OUT_GRID}")
    print(f"  {len(grid)} cellules x {grid['AIRE_CODE'].nunique()} aires")


if __name__ == "__main__":
    run()
