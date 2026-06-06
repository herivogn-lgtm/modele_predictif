"""Pipeline #04 — Extraction des variables environnementales via Google Earth Engine.

Extrait les statistiques zonales (moyenne, min, max, écart-type) sur les 90 régions
naturelles pour chaque décade de campagne acridienne 2001–2026. Sources : CHIRPS
pluviométrie + anomalie, MODIS NDVI/EVI/LST, ERA5 humidité du sol, MODIS occupation
du sol, OpenLandMap texture du sol, SRTM DEM, NOAA ENSO/ONI.

Sortie : data/processed/04_variables_environnementales.parquet

Usage :
    python src/04_extraction_variables_gee.py --test-only
    python src/04_extraction_variables_gee.py --years 2010
    python src/04_extraction_variables_gee.py
"""

import argparse
import calendar
import sys
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent))
from config_gee import (
    CHIRPS_BASELINE_YEARS,
    CHIRPS_COLLECTION,
    DEM_ASSET,
    ENSO_URL,
    ERA5_MONTHLY,
    GEE_PROJECT_ID,
    MAX_RETRIES,
    MODIS_LC,
    MODIS_LST,
    MODIS_NDVI_EVI,
    OLM_CLAY,
    OLM_SAND,
    OLM_SILT,
    PATHS,
    RETRY_BACKOFF_BASE,
    YEARS,
)

# Mois de la campagne acridienne : octobre–juillet
CAMPAIGN_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7]


# ── 1. Calendrier décadaire ────────────────────────────────────────────────────

def decade_bounds(year: int, month: int, part: int) -> tuple[date, date]:
    """Retourne (date_start, date_end) pour la décade (year, month, part∈{1,2,3})."""
    if part == 1:
        start, end = date(year, month, 1), date(year, month, 10)
    elif part == 2:
        start, end = date(year, month, 11), date(year, month, 20)
    else:
        last = calendar.monthrange(year, month)[1]
        start, end = date(year, month, 21), date(year, month, last)
    return start, end


def _campaign_label(year: int, month: int) -> str | None:
    if month >= 10:
        return f"{year}-{year + 1}"
    if 1 <= month <= 7:
        return f"{year - 1}-{year}"
    return None  # août-septembre : hors campagne


def build_decade_calendar(years: list[int]) -> pd.DataFrame:
    """Génère toutes les décades de campagne pour les années civiles données.

    Chaque ligne représente une décade avec ses métadonnées temporelles.
    Retourne uniquement les décades des mois de campagne (oct–jul).
    """
    records = []
    for year in years:
        for month in CAMPAIGN_MONTHS:
            campaign = _campaign_label(year, month)
            if campaign is None:
                continue
            # Numéro de mois dans la campagne (oct=1 … jul=10)
            month_offset = CAMPAIGN_MONTHS.index(month) + 1
            for part in (1, 2, 3):
                d_start, d_end = decade_bounds(year, month, part)
                decade_num = (month_offset - 1) * 3 + part
                records.append({
                    "year": year,
                    "month": month,
                    "decade_part": part,
                    "date_start": d_start,
                    "date_end": d_end,
                    "midpoint": d_start + timedelta(days=(d_end - d_start).days // 2),
                    "campaign": campaign,
                    "decade_num": decade_num,
                })
    df = pd.DataFrame(records)
    df["date_start"] = pd.to_datetime(df["date_start"])
    df["date_end"] = pd.to_datetime(df["date_end"])
    df["midpoint"] = pd.to_datetime(df["midpoint"])
    return df


# ── 2. Chargement des régions ──────────────────────────────────────────────────

def load_regions(shp_path: Path) -> tuple[gpd.GeoDataFrame, ee.FeatureCollection]:
    """Charge le shapefile et construit la FeatureCollection GEE inline (sans upload)."""
    gdf = gpd.read_file(shp_path).to_crs("EPSG:4326")
    assert gdf["rn_num"].is_unique, "rn_num doit être unique dans le shapefile"

    features = []
    for _, row in gdf.iterrows():
        geom_dict = row.geometry.__geo_interface__
        feat = ee.Feature(
            ee.Geometry(geom_dict),
            {"region_id": int(row["rn_num"]), "region_nom": str(row["rn_nom"])},
        )
        features.append(feat)

    fc = ee.FeatureCollection(features)
    return gdf, fc


# ── 3. Utilitaires GEE ────────────────────────────────────────────────────────

def gee_call_with_retry(fn):
    """Exécute fn() avec retry exponentiel sur EEException (rate limit / 5xx)."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except ee.EEException as exc:
            last_exc = exc
            wait = RETRY_BACKOFF_BASE**attempt
            print(f"    GEE erreur (tentative {attempt + 1}/{MAX_RETRIES}): {exc} — attente {wait}s")
            time.sleep(wait)
    raise last_exc


def _collection_empty(collection: ee.ImageCollection) -> bool:
    return gee_call_with_retry(lambda: collection.size().getInfo()) == 0


def reduce_regions(image: ee.Image, fc: ee.FeatureCollection, scale: int) -> list[dict]:
    """Calcule mean/stdDev/min/max par région et retourne une liste de dicts."""
    reducer = (
        ee.Reducer.mean()
        .combine(ee.Reducer.stdDev(), sharedInputs=True)
        .combine(ee.Reducer.minMax(), sharedInputs=True)
    )
    result = gee_call_with_retry(
        lambda: image.reduceRegions(
            collection=fc,
            reducer=reducer,
            scale=scale,
            crs="EPSG:4326",
        ).getInfo()
    )
    return [f["properties"] for f in result["features"]]


def reduce_regions_mode(image: ee.Image, fc: ee.FeatureCollection, scale: int) -> list[dict]:
    """Calcule le mode par région (pour les données catégorielles)."""
    result = gee_call_with_retry(
        lambda: image.reduceRegions(
            collection=fc,
            reducer=ee.Reducer.mode(),
            scale=scale,
            crs="EPSG:4326",
        ).getInfo()
    )
    return [f["properties"] for f in result["features"]]


def _props_to_df(props_list: list[dict], id_key: str = "region_id") -> pd.DataFrame:
    """Convertit la liste de propriétés GEE en DataFrame avec region_id."""
    df = pd.DataFrame(props_list)
    if id_key not in df.columns:
        return pd.DataFrame()
    return df[[c for c in df.columns if c not in ("region_nom",) or c == id_key]]


# ── 4. Extraction CHIRPS ───────────────────────────────────────────────────────

def _chirps_sum_image(year: int, month: int, part: int) -> ee.Image | None:
    """Somme des précipitations CHIRPS journalières sur la décade."""
    d_start, d_end = decade_bounds(year, month, part)
    coll = (
        ee.ImageCollection(CHIRPS_COLLECTION)
        .filterDate(
            d_start.strftime("%Y-%m-%d"),
            (d_end + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        .select("precipitation")
    )
    if _collection_empty(coll):
        return None
    return coll.sum()


def extract_chirps_sum(fc: ee.FeatureCollection, year: int, month: int, part: int) -> pd.DataFrame:
    """Somme décadaire CHIRPS par région (mm). NaN si pas de données."""
    img = _chirps_sum_image(year, month, part)
    if img is None:
        return pd.DataFrame(columns=["region_id", "chirps_sum_mean", "chirps_sum_min",
                                     "chirps_sum_max", "chirps_sum_std"])
    props = reduce_regions(img.rename("chirps_sum"), fc, scale=5566)
    df = _props_to_df(props)
    # GEE retourne mean/stdDev/min/max sans préfixe pour les images mono-bande
    df = df.rename(columns={
        "mean": "chirps_sum_mean",
        "stdDev": "chirps_sum_std",
        "min": "chirps_sum_min",
        "max": "chirps_sum_max",
    })
    keep = [c for c in ["region_id", "chirps_sum_mean", "chirps_sum_min",
                        "chirps_sum_max", "chirps_sum_std"] if c in df.columns]
    return df[keep]


def compute_chirps_baseline_stats(
    fc: ee.FeatureCollection,
    baseline_years: tuple[int, int] = CHIRPS_BASELINE_YEARS,
    cache_path: Path = PATHS["baseline_cache"],
) -> pd.DataFrame:
    """Calcule la moyenne décadaire historique CHIRPS (1981–2010) par région × décade-of-year.

    Résultat : DataFrame avec colonnes region_id, month, decade_part, chirps_baseline_mean.
    Met en cache dans un Parquet pour éviter les recalculs.
    """
    if cache_path.exists():
        print(f"Baseline CHIRPS chargée depuis le cache : {cache_path}")
        return pd.read_parquet(cache_path)

    print(f"Calcul baseline CHIRPS {baseline_years[0]}–{baseline_years[1]} (36 décades × 30 ans)...")
    records = []
    start_yr, end_yr = baseline_years
    n_years = end_yr - start_yr + 1

    for month in range(1, 13):
        for part in (1, 2, 3):
            print(f"  Baseline mois={month:02d} partie={part}...", end=" ", flush=True)

            # Empile les n_years images de somme décadaire
            images = []
            for y in range(start_yr, end_yr + 1):
                d_start, d_end = decade_bounds(y, month, part)
                img = (
                    ee.ImageCollection(CHIRPS_COLLECTION)
                    .filterDate(
                        d_start.strftime("%Y-%m-%d"),
                        (d_end + timedelta(days=1)).strftime("%Y-%m-%d"),
                    )
                    .select("precipitation")
                    .sum()
                )
                images.append(img)

            mean_img = ee.ImageCollection(images).mean().rename("baseline")
            props = reduce_regions(mean_img, fc, scale=5566)

            for p in props:
                records.append({
                    "month": month,
                    "decade_part": part,
                    "region_id": p.get("region_id"),
                    "chirps_baseline_mean": p.get("mean"),
                })
            print(f"OK ({len(props)} régions)")

    df = pd.DataFrame(records)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    print(f"Baseline sauvegardée : {cache_path}")
    return df


# ── 5. Extraction NDVI/EVI (MODIS MOD13A2, 16-day) ───────────────────────────

def _apply_modis_ndvi_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD13A2 (bits 0-1 de DetailedQA > 1)."""
    qa = image.select("DetailedQA")
    good_mask = qa.bitwiseAnd(3).lte(1)
    return image.updateMask(good_mask)


def extract_ndvi_evi(fc: ee.FeatureCollection, year: int, month: int, part: int) -> pd.DataFrame:
    """NDVI et EVI (MOD13A2) par région pour la décade, composite le plus proche. NaN si vide."""
    empty_cols = ["region_id", "ndvi_mean", "ndvi_min", "ndvi_max", "ndvi_std",
                  "evi_mean", "evi_min", "evi_max", "evi_std"]

    d_start, d_end = decade_bounds(year, month, part)
    window_start = (d_start - timedelta(days=8)).strftime("%Y-%m-%d")
    window_end   = (d_end   + timedelta(days=9)).strftime("%Y-%m-%d")

    coll = (
        ee.ImageCollection(MODIS_NDVI_EVI)
        .filterDate(window_start, window_end)
        .map(_apply_modis_ndvi_qa)
        .select(["NDVI", "EVI"])
    )
    if _collection_empty(coll):
        return pd.DataFrame(columns=empty_cols)

    # Composite le plus récent avant la fin de la décade
    img = coll.sort("system:time_start", False).first().multiply(0.0001)

    props = reduce_regions(img, fc, scale=250)
    df = _props_to_df(props)

    rename = {
        "NDVI_mean": "ndvi_mean", "NDVI_stdDev": "ndvi_std",
        "NDVI_min":  "ndvi_min",  "NDVI_max":    "ndvi_max",
        "EVI_mean":  "evi_mean",  "EVI_stdDev":  "evi_std",
        "EVI_min":   "evi_min",   "EVI_max":     "evi_max",
    }
    df = df.rename(columns=rename)
    cols = [c for c in empty_cols if c in df.columns]
    return df[cols]


# ── 6. Extraction LST (MODIS MOD11A2, 8-day) ──────────────────────────────────

def _apply_modis_lst_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD11A2 (bits 0-1 de QC_Day != 0)."""
    qa = image.select("QC_Day")
    good_mask = qa.bitwiseAnd(3).eq(0)
    return image.updateMask(good_mask)


def extract_lst(fc: ee.FeatureCollection, year: int, month: int, part: int) -> pd.DataFrame:
    """LST diurne (MOD11A2) en Kelvin par région. NaN si pas de données."""
    empty_cols = ["region_id", "lst_mean", "lst_min", "lst_max", "lst_std"]

    d_start, d_end = decade_bounds(year, month, part)
    window_start = (d_start - timedelta(days=4)).strftime("%Y-%m-%d")
    window_end   = (d_end   + timedelta(days=5)).strftime("%Y-%m-%d")

    coll = (
        ee.ImageCollection(MODIS_LST)
        .filterDate(window_start, window_end)
        .map(_apply_modis_lst_qa)
        .select("LST_Day_1km")
    )
    if _collection_empty(coll):
        return pd.DataFrame(columns=empty_cols)

    img = coll.sort("system:time_start", False).first().multiply(0.02).rename("lst")

    props = reduce_regions(img, fc, scale=1000)
    df = _props_to_df(props)

    # GEE retourne mean/stdDev/min/max sans préfixe pour les images mono-bande
    rename = {
        "mean": "lst_mean", "stdDev": "lst_std",
        "min":  "lst_min",  "max":    "lst_max",
    }
    df = df.rename(columns=rename)
    cols = [c for c in empty_cols if c in df.columns]
    return df[cols]


# ── 7. Extraction humidité du sol (ERA5, mensuel) ─────────────────────────────

def extract_soil_moisture(fc: ee.FeatureCollection, year: int, month: int) -> pd.DataFrame:
    """Humidité du sol ERA5 (couche 0–7cm) par région pour le mois donné."""
    empty_cols = ["region_id", "soil_moisture_mean", "soil_moisture_min",
                  "soil_moisture_max", "soil_moisture_std"]

    coll = (
        ee.ImageCollection(ERA5_MONTHLY)
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .filter(ee.Filter.calendarRange(month, month, "month"))
        .select("volumetric_soil_water_layer_1")
    )
    if _collection_empty(coll):
        return pd.DataFrame(columns=empty_cols)

    img = coll.first().rename("sm")

    props = reduce_regions(img, fc, scale=27750)
    df = _props_to_df(props)

    # GEE retourne mean/stdDev/min/max sans préfixe pour les images mono-bande
    rename = {
        "mean": "soil_moisture_mean", "stdDev": "soil_moisture_std",
        "min":  "soil_moisture_min",  "max":    "soil_moisture_max",
    }
    df = df.rename(columns=rename)
    cols = [c for c in empty_cols if c in df.columns]
    return df[cols]


# ── 8. Occupation du sol (MODIS MCD12Q1, annuel) ──────────────────────────────

def extract_land_cover(fc: ee.FeatureCollection, year: int) -> pd.DataFrame:
    """Mode de la classification IGBP (LC_Type1) par région pour l'année donnée."""
    coll = (
        ee.ImageCollection(MODIS_LC)
        .filter(ee.Filter.calendarRange(year, year, "year"))
        .select("LC_Type1")
    )
    if _collection_empty(coll):
        return pd.DataFrame(columns=["region_id", "land_cover_mode"])

    img = coll.first().rename("lc")
    props = reduce_regions_mode(img, fc, scale=500)
    df = _props_to_df(props).rename(columns={"mode": "land_cover_mode"})
    return df[["region_id", "land_cover_mode"]]


# ── 9. Sources statiques ───────────────────────────────────────────────────────

def extract_dem(fc: ee.FeatureCollection) -> pd.DataFrame:
    """Altitude SRTM (moyenne, min, max) par région. Calculé une seule fois."""
    img = ee.Image(DEM_ASSET).select("elevation").rename("dem")
    props = reduce_regions(img, fc, scale=30)
    df = _props_to_df(props)
    # GEE retourne mean/stdDev/min/max sans préfixe pour les images mono-bande
    rename = {
        "mean": "dem_mean", "min": "dem_min", "max": "dem_max",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["region_id", "dem_mean", "dem_min", "dem_max"] if c in df.columns]
    return df[keep]


def extract_soil_texture(fc: ee.FeatureCollection) -> pd.DataFrame:
    """Texture du sol OpenLandMap (sable, argile, limon en %) par région. Calculé une seule fois.

    Les valeurs natives sont en g/kg (0–1000) ; on divise par 10 pour obtenir des %.
    """
    sand = ee.Image(OLM_SAND).select("b0").divide(10).rename("sand")
    clay = ee.Image(OLM_CLAY).select("b0").divide(10).rename("clay")
    silt = ee.Image(OLM_SILT).select("b0").divide(10).rename("silt")
    img = ee.Image.cat([sand, clay, silt])

    props = reduce_regions(img, fc, scale=250)
    df = _props_to_df(props)
    rename = {
        "sand_mean": "soil_sand_mean",
        "clay_mean": "soil_clay_mean",
        "silt_mean": "soil_silt_mean",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["region_id", "soil_sand_mean", "soil_clay_mean", "soil_silt_mean"]
            if c in df.columns]
    return df[keep]


# ── 10. ENSO/ONI (source externe NOAA) ────────────────────────────────────────

def fetch_enso_oni() -> pd.DataFrame:
    """Télécharge et parse l'indice ONI depuis NOAA CPC.

    Retourne un DataFrame avec colonnes year, month, enso_oni.
    """
    print(f"Téléchargement ENSO/ONI depuis NOAA...")
    resp = requests.get(ENSO_URL, timeout=30)
    resp.raise_for_status()

    lines = [l for l in resp.text.splitlines() if l.strip() and not l.strip().startswith("YR")]
    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 5:
            try:
                rows.append({
                    "year": int(parts[0]),
                    "month": int(parts[1]),
                    "enso_oni": float(parts[4]),
                })
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)
    print(f"  {len(df)} entrées ONI chargées ({df['year'].min()}–{df['year'].max()})")
    return df


# ── 11. Boucle principale d'extraction ────────────────────────────────────────

def extract_all_decades(
    fc: ee.FeatureCollection,
    gdf: gpd.GeoDataFrame,
    baseline_df: pd.DataFrame,
    years: list[int],
) -> pd.DataFrame:
    """Boucle année → mois → décade et accumule toutes les extractions dynamiques."""

    decade_cal = build_decade_calendar(years)
    all_rows = []

    # Cache ERA5 mensuel (évite 3 appels/mois identiques pour D1, D2, D3)
    sm_cache: dict[tuple, pd.DataFrame] = {}
    # Cache land cover annuel
    lc_cache: dict[int, pd.DataFrame] = {}

    total = len(decade_cal)
    print(f"\nExtraction : {total} décades × 90 régions (années {years[0]}–{years[-1]})")

    for i, row in decade_cal.iterrows():
        year, month, part = int(row["year"]), int(row["month"]), int(row["decade_part"])
        print(f"  [{i+1}/{total}] {row['campaign']} décade {row['decade_num']:02d} "
              f"({row['date_start'].date()} → {row['date_end'].date()})", end=" ", flush=True)

        # ── CHIRPS somme ──────────────────────────────────────────────────
        chirps_df = extract_chirps_sum(fc, year, month, part)

        # ── CHIRPS anomalie (soustraction pandas) ─────────────────────────
        base_key = baseline_df[
            (baseline_df["month"] == month) & (baseline_df["decade_part"] == part)
        ][["region_id", "chirps_baseline_mean"]]

        if chirps_df.empty or base_key.empty:
            chirps_df["chirps_anomaly_mean"] = np.nan
        else:
            chirps_df = chirps_df.merge(base_key, on="region_id", how="left")
            chirps_df["chirps_anomaly_mean"] = (
                chirps_df["chirps_sum_mean"] - chirps_df["chirps_baseline_mean"]
            )
            chirps_df = chirps_df.drop(columns=["chirps_baseline_mean"])

        # ── NDVI / EVI ────────────────────────────────────────────────────
        ndvi_df = extract_ndvi_evi(fc, year, month, part)

        # ── LST ───────────────────────────────────────────────────────────
        lst_df = extract_lst(fc, year, month, part)

        # ── Humidité sol (cache mensuel) ──────────────────────────────────
        if (year, month) not in sm_cache:
            sm_cache[(year, month)] = extract_soil_moisture(fc, year, month)
        sm_df = sm_cache[(year, month)]

        # ── Occupation du sol (cache annuel) ─────────────────────────────
        if year not in lc_cache:
            lc_cache[year] = extract_land_cover(fc, year)
        lc_df = lc_cache[year]

        # ── Assemblage de la décade ───────────────────────────────────────
        # Base : toutes les régions avec les métadonnées temporelles
        base = pd.DataFrame({
            "region_id":   gdf["rn_num"].astype(int).tolist(),
            "region_nom":  gdf["rn_nom"].tolist(),
            "campaign":    row["campaign"],
            "decade_num":  row["decade_num"],
            "date_start":  row["date_start"],
            "date_end":    row["date_end"],
            "year":        year,
            "month":       month,
            "decade_part": part,
        })

        for dyn_df in [chirps_df, ndvi_df, lst_df, sm_df, lc_df]:
            if not dyn_df.empty and "region_id" in dyn_df.columns:
                base = base.merge(dyn_df, on="region_id", how="left")

        all_rows.append(base)
        print("OK")

    return pd.concat(all_rows, ignore_index=True)


# ── 12. Assemblage final ───────────────────────────────────────────────────────

def merge_all(
    decades_df: pd.DataFrame,
    dem_df: pd.DataFrame,
    soil_df: pd.DataFrame,
    enso_df: pd.DataFrame,
) -> pd.DataFrame:
    """Joint les features statiques et l'ONI à la table principale."""
    df = decades_df.copy()
    if not dem_df.empty:
        df = df.merge(dem_df, on="region_id", how="left")
    if not soil_df.empty:
        df = df.merge(soil_df, on="region_id", how="left")
    if not enso_df.empty:
        df = df.merge(enso_df, on=["year", "month"], how="left")
    return df


# ── 13. Validation de la sortie ───────────────────────────────────────────────

def validate_output(df: pd.DataFrame) -> None:
    """Vérifie les plages physiques attendues. Lève AssertionError si invalide."""
    key_cols = ["region_id", "region_nom", "date_start", "campaign", "decade_num"]
    for col in key_cols:
        assert col in df.columns, f"Colonne manquante : {col}"
        assert df[col].notna().all(), f"NaN dans la colonne clé : {col}"

    if "ndvi_mean" in df.columns:
        valid = df["ndvi_mean"].dropna()
        assert valid.between(-1, 1).all(), f"NDVI hors [-1, 1] : {valid.describe()}"

    if "lst_mean" in df.columns:
        valid = df["lst_mean"].dropna()
        assert valid.between(200, 400).all(), f"LST hors [200, 400] K : {valid.describe()}"

    if "chirps_sum_mean" in df.columns:
        valid = df["chirps_sum_mean"].dropna()
        assert (valid >= 0).all(), f"CHIRPS négatif : {valid.min()}"

    if "soil_sand_mean" in df.columns and "soil_clay_mean" in df.columns:
        total = (df["soil_sand_mean"].fillna(0)
                 + df["soil_clay_mean"].fillna(0)
                 + df["soil_silt_mean"].fillna(0))
        # La somme peut dépasser 100% selon l'arrondi OpenLandMap — seuil large
        assert total.max() <= 120, f"Texture sol : somme > 120% ({total.max():.1f})"

    print(f"Validation OK — {len(df)} lignes, {len(df.columns)} colonnes")
    print(f"  NaN NDVI : {df['ndvi_mean'].isna().mean():.1%}" if "ndvi_mean" in df.columns else "")
    print(f"  NaN LST  : {df['lst_mean'].isna().mean():.1%}" if "lst_mean" in df.columns else "")


# ── 14. Test d'intégration ────────────────────────────────────────────────────

def run_integration_test(fc: ee.FeatureCollection, gdf: gpd.GeoDataFrame) -> None:
    """Teste chaque extracteur sur une seule région (rn_num=1) et une seule décade.

    Lève AssertionError en cas d'échec.
    """
    print("\n=== Test d'intégration : région 1, janvier 2010 D1 ===")

    # FeatureCollection réduite à la première région
    first = gdf.iloc[[0]]
    _, fc_one = load_regions(PATHS["regions_shp"])
    region_id = int(first["rn_num"].iloc[0])
    fc_test = fc_one.filter(ee.Filter.eq("region_id", region_id))

    year, month, part = 2010, 1, 1

    # CHIRPS
    df = extract_chirps_sum(fc_test, year, month, part)
    assert df.empty or (df["chirps_sum_mean"].dropna() >= 0).all(), "CHIRPS : valeurs négatives"
    print("  CHIRPS somme : OK")

    # NDVI/EVI
    df = extract_ndvi_evi(fc_test, year, month, part)
    if not df.empty and "ndvi_mean" in df.columns:
        valid = df["ndvi_mean"].dropna()
        assert valid.between(-1, 1).all(), f"NDVI hors plage : {valid.values}"
    print("  NDVI/EVI     : OK")

    # LST
    df = extract_lst(fc_test, year, month, part)
    if not df.empty and "lst_mean" in df.columns:
        valid = df["lst_mean"].dropna()
        assert valid.between(200, 400).all(), f"LST hors plage Kelvin : {valid.values}"
    print("  LST          : OK")

    # ERA5
    df = extract_soil_moisture(fc_test, year, month)
    if not df.empty and "soil_moisture_mean" in df.columns:
        valid = df["soil_moisture_mean"].dropna()
        assert valid.between(0, 1).all(), f"Humidité sol hors [0,1] : {valid.values}"
    print("  ERA5 sol     : OK")

    # DEM
    df = extract_dem(fc_test)
    if not df.empty and "dem_mean" in df.columns:
        assert (df["dem_mean"].dropna() >= 0).all(), "DEM : altitude négative"
    print("  DEM SRTM     : OK")

    # Texture sol
    df = extract_soil_texture(fc_test)
    if not df.empty and "soil_sand_mean" in df.columns:
        total = df["soil_sand_mean"].fillna(0) + df["soil_clay_mean"].fillna(0) + df["soil_silt_mean"].fillna(0)
        assert total.max() <= 120, f"Texture sol : somme > 120% ({total.max():.1f})"
    print("  Texture sol  : OK")

    # ENSO
    enso = fetch_enso_oni()
    assert not enso.empty, "ENSO : DataFrame vide"
    assert "enso_oni" in enso.columns
    print("  ENSO/ONI     : OK")

    print("=== Test d'intégration réussi ===\n")


# ── 15. Point d'entrée ────────────────────────────────────────────────────────

def run(years: list[int] = YEARS, test_only: bool = False) -> None:
    print(f"Authentification GEE (projet : {GEE_PROJECT_ID})...")
    ee.Authenticate()
    ee.Initialize(project=GEE_PROJECT_ID)
    print("GEE initialisé.")

    print(f"Chargement des régions naturelles : {PATHS['regions_shp']}")
    gdf, fc = load_regions(PATHS["regions_shp"])
    print(f"  {len(gdf)} régions chargées.")

    if test_only:
        run_integration_test(fc, gdf)
        return

    # Baseline CHIRPS (mise en cache automatique)
    baseline_df = compute_chirps_baseline_stats(fc)

    # Extraction dynamique
    decades_df = extract_all_decades(fc, gdf, baseline_df, years)

    # Sources statiques
    print("\nExtraction DEM SRTM...")
    dem_df = extract_dem(fc)

    print("Extraction texture du sol OpenLandMap...")
    soil_df = extract_soil_texture(fc)

    # ENSO
    enso_df = fetch_enso_oni()

    # Assemblage
    print("\nAssemblage final...")
    full_df = merge_all(decades_df, dem_df, soil_df, enso_df)

    # Validation
    validate_output(full_df)

    # Sauvegarde
    out = PATHS["output_parquet"]
    out.parent.mkdir(parents=True, exist_ok=True)
    full_df.to_parquet(out, index=False)
    print(f"\nSortie : {out}")
    print(f"  {len(full_df)} lignes × {len(full_df.columns)} colonnes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline #04 — Extraction GEE")
    parser.add_argument(
        "--test-only", action="store_true",
        help="Exécute uniquement le test d'intégration (1 région × 1 décade)"
    )
    parser.add_argument(
        "--years", nargs="+", type=int, default=YEARS,
        help="Années civiles à extraire (ex. --years 2010 2011)"
    )
    args = parser.parse_args()
    run(years=args.years, test_only=args.test_only)
