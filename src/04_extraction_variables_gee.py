"""Pipeline #04 — Extraction des variables environnementales via Google Earth Engine.

Extrait les statistiques zonales (moyenne, min, max, écart-type) sur les 90 régions
naturelles pour chaque décade de campagne acridienne 2001–2026. Sources : CHIRPS
pluviométrie + anomalie, MODIS NDVI/EVI/LST, ERA5 humidité du sol, MODIS occupation
du sol, OpenLandMap texture du sol, SRTM DEM, NOAA ENSO/ONI.

Architecture : la réduction décadaire est mappée **côté serveur** sur une
ImageCollection (1 getInfo par source × année au lieu de ~6 par décade), ce qui
réduit drastiquement le nombre de round-trips GEE. La logique pure (calendrier,
specs, assemblage, anomalie, garde-fous) vit dans `extraction_gee_helpers` et est
testée unitairement sans dépendance GEE.

Sortie : data/processed/04_variables_environnementales.parquet

Usage :
    python src/04_extraction_variables_gee.py --test-only
    python src/04_extraction_variables_gee.py --years 2010
    python src/04_extraction_variables_gee.py
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import ee
import geopandas as gpd
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
    PATHS,
    RETRY_BACKOFF_BASE,
    YEARS,
)
from extraction_gee_helpers import (
    assemble_decades,
    assert_decade_completeness,
    build_decade_calendar,
    build_specs,
    compute_chirps_anomaly,
    decade_bounds,
    parse_reduce_features,
)

# Nombre de getInfo concurrents (GEE sert les requêtes en parallèle ; getInfo est
# thread-safe côté client). Borne raisonnable pour ne pas saturer le quota.
GETINFO_MAX_WORKERS = 6


# ── 1. Chargement des régions ──────────────────────────────────────────────────

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


def regions_table(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """DataFrame (region_id, region_nom) servant de base à l'assemblage."""
    return pd.DataFrame({
        "region_id": gdf["rn_num"].astype(int).tolist(),
        "region_nom": gdf["rn_nom"].tolist(),
    })


# ── 2. Utilitaires GEE ────────────────────────────────────────────────────────

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


# Réducteur statistique commun : moyenne + écart-type + min/max.
# Construit paresseusement : ee.Reducer.* nécessite que GEE soit initialisé,
# ce qui n'est pas le cas à l'import du module.
_STATS_REDUCER = None


def stats_reducer():
    global _STATS_REDUCER
    if _STATS_REDUCER is None:
        _STATS_REDUCER = (
            ee.Reducer.mean()
            .combine(ee.Reducer.stdDev(), sharedInputs=True)
            .combine(ee.Reducer.minMax(), sharedInputs=True)
        )
    return _STATS_REDUCER


def reduce_regions(image: ee.Image, fc: ee.FeatureCollection, scale: int) -> list[dict]:
    """mean/stdDev/min/max par région (sources statiques mono-image)."""
    result = gee_call_with_retry(
        lambda: image.reduceRegions(
            collection=fc, reducer=stats_reducer(), scale=scale, crs="EPSG:4326",
        ).getInfo()
    )
    return [f["properties"] for f in result["features"]]


def _props_to_df(props_list: list[dict]) -> pd.DataFrame:
    """Convertit une liste de propriétés GEE en DataFrame (sans region_nom)."""
    df = pd.DataFrame(props_list)
    if "region_id" not in df.columns:
        return pd.DataFrame()
    return df[[c for c in df.columns if c != "region_nom"]]


# ── 3. Réduction décadaire batch (côté serveur) ───────────────────────────────

def _safe_image(real: ee.Image, dummy: ee.Image, coll: ee.ImageCollection, key_val) -> ee.Image:
    """Renvoie `real` si la collection est non vide, sinon `dummy` (masqué).

    Garantit un schéma de bandes stable même décade vide → la réduction renvoie
    null → NaN après assemblage. Remplace l'ancienne sonde `_collection_empty`
    (un getInfo par décade) par une condition côté serveur.
    """
    img = ee.Image(ee.Algorithms.If(coll.size().gt(0), real, dummy))
    return img.set("decade_id", key_val)


def _chirps_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(CHIRPS_COLLECTION)
        .filterDate(spec["start"], spec["end"])
        .select("precipitation")
    )
    real = coll.sum().rename("chirps_sum")
    dummy = ee.Image.constant(0).rename("chirps_sum").updateMask(0)
    return _safe_image(real, dummy, coll, spec["id"])


def _apply_modis_ndvi_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD13A2 (bits 0-1 de DetailedQA > 1)."""
    qa = image.select("DetailedQA")
    return image.updateMask(qa.bitwiseAnd(3).lte(1))


def _ndvi_evi_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(MODIS_NDVI_EVI)
        .filterDate(spec["start"], spec["end"])
        .map(_apply_modis_ndvi_qa)
        .select(["NDVI", "EVI"])
    )
    real = coll.sort("system:time_start", False).first().multiply(0.0001)
    dummy = ee.Image.constant([0, 0]).rename(["NDVI", "EVI"]).updateMask(0)
    return _safe_image(real, dummy, coll, spec["id"])


def _apply_modis_lst_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD11A2 (bits 0-1 de QC_Day != 0)."""
    qa = image.select("QC_Day")
    return image.updateMask(qa.bitwiseAnd(3).eq(0))


def _lst_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(MODIS_LST)
        .filterDate(spec["start"], spec["end"])
        .map(_apply_modis_lst_qa)
        .select("LST_Day_1km")
    )
    real = coll.sort("system:time_start", False).first().multiply(0.02).rename("lst")
    dummy = ee.Image.constant(0).rename("lst").updateMask(0)
    return _safe_image(real, dummy, coll, spec["id"])


def _reduce_specs(image_fn, specs: list[dict], fc, scale: int, key: str = "decade_id") -> list[dict]:
    """Mappe reduceRegions côté serveur sur l'IC des composites, retourne les props.

    En cas d'échec getInfo (taille/timeout), bissection récursive des specs
    (fallback semestriel automatique) jusqu'à 1 spec.
    """
    ic = ee.ImageCollection([image_fn(s) for s in specs])

    def per_img(img):
        stats = img.reduceRegions(
            collection=fc, reducer=stats_reducer(), scale=scale, crs="EPSG:4326",
        )
        kv = img.get(key)
        return stats.map(lambda f: f.set(key, kv))

    fcol = ic.map(per_img).flatten()
    try:
        result = gee_call_with_retry(lambda: fcol.getInfo())
        return [f["properties"] for f in result["features"]]
    except ee.EEException:
        if len(specs) <= 1:
            raise
        mid = len(specs) // 2
        print(f"    getInfo trop volumineux ({len(specs)} décades) — bissection")
        return (_reduce_specs(image_fn, specs[:mid], fc, scale, key)
                + _reduce_specs(image_fn, specs[mid:], fc, scale, key))


def extract_source(image_fn, specs_by_year: dict, fc, scale: int,
                   rename: dict, keep: list[str], label: str) -> pd.DataFrame:
    """Extrait une source dynamique sur toutes les années (getInfo parallélisés)."""
    years = sorted(specs_by_year)

    def one_year(year: int) -> pd.DataFrame:
        props = _reduce_specs(image_fn, specs_by_year[year], fc, scale)
        return parse_reduce_features(props, rename, keep)

    print(f"  {label} : {len(years)} années × {GETINFO_MAX_WORKERS} workers...", flush=True)
    with ThreadPoolExecutor(max_workers=GETINFO_MAX_WORKERS) as ex:
        dfs = list(ex.map(one_year, years))
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=keep)
    print(f"    {label} OK ({len(out)} lignes)")
    return out


# Constantes de renommage / colonnes par source (noms bruts GEE → noms métier)
CHIRPS_RENAME = {"mean": "chirps_sum_mean", "stdDev": "chirps_sum_std",
                 "min": "chirps_sum_min", "max": "chirps_sum_max"}
CHIRPS_KEEP = ["region_id", "decade_id", "chirps_sum_mean", "chirps_sum_min",
               "chirps_sum_max", "chirps_sum_std"]

NDVI_RENAME = {"NDVI_mean": "ndvi_mean", "NDVI_stdDev": "ndvi_std",
               "NDVI_min": "ndvi_min", "NDVI_max": "ndvi_max",
               "EVI_mean": "evi_mean", "EVI_stdDev": "evi_std",
               "EVI_min": "evi_min", "EVI_max": "evi_max"}
NDVI_KEEP = ["region_id", "decade_id", "ndvi_mean", "ndvi_min", "ndvi_max", "ndvi_std",
             "evi_mean", "evi_min", "evi_max", "evi_std"]

LST_RENAME = {"mean": "lst_mean", "stdDev": "lst_std", "min": "lst_min", "max": "lst_max"}
LST_KEEP = ["region_id", "decade_id", "lst_mean", "lst_min", "lst_max", "lst_std"]


def extract_dynamic(fc, years: list[int]) -> pd.DataFrame:
    """Assemble CHIRPS + NDVI/EVI + LST par décade × région (table longue)."""
    calendar = build_decade_calendar(years)
    chirps_df = extract_source(_chirps_image, build_specs(calendar, 0, 1), fc, 5566,
                               CHIRPS_RENAME, CHIRPS_KEEP, "CHIRPS")
    ndvi_df = extract_source(_ndvi_evi_image, build_specs(calendar, 8, 9), fc, 250,
                             NDVI_RENAME, NDVI_KEEP, "NDVI/EVI")
    lst_df = extract_source(_lst_image, build_specs(calendar, 4, 5), fc, 1000,
                            LST_RENAME, LST_KEEP, "LST")
    return calendar, [chirps_df, ndvi_df, lst_df]


# ── 4. Humidité du sol (ERA5, mensuel) ────────────────────────────────────────

def extract_soil_moisture_all(fc, years: list[int]) -> pd.DataFrame:
    """Humidité du sol ERA5 (0–7cm) par région × (année, mois) de campagne.

    Une valeur mensuelle s'applique aux 3 décades du mois ; le merge se fait sur
    (year, month, region_id) lors de l'assemblage final.
    """
    rename = {"mean": "soil_moisture_mean", "stdDev": "soil_moisture_std",
              "min": "soil_moisture_min", "max": "soil_moisture_max"}
    keep = ["region_id", "ym", "soil_moisture_mean", "soil_moisture_min",
            "soil_moisture_max", "soil_moisture_std"]
    months = build_decade_calendar(years)[["year", "month"]].drop_duplicates()

    def _sm_image(year: int, month: int) -> ee.Image:
        coll = (
            ee.ImageCollection(ERA5_MONTHLY)
            .filter(ee.Filter.calendarRange(year, year, "year"))
            .filter(ee.Filter.calendarRange(month, month, "month"))
            .select("volumetric_soil_water_layer_1")
        )
        real = coll.first().rename("sm")
        dummy = ee.Image.constant(0).rename("sm").updateMask(0)
        img = ee.Image(ee.Algorithms.If(coll.size().gt(0), real, dummy))
        return img.set("decade_id", year * 100 + month)  # ici "ym"

    items = [{"year": int(r.year), "month": int(r.month)} for r in months.itertuples(index=False)]

    def one_year(year: int) -> pd.DataFrame:
        specs = [it for it in items if it["year"] == year]
        ic = ee.ImageCollection([_sm_image(it["year"], it["month"]) for it in specs])

        def per_img(img):
            stats = img.reduceRegions(collection=fc, reducer=stats_reducer(),
                                      scale=27750, crs="EPSG:4326")
            kv = img.get("decade_id")
            return stats.map(lambda f: f.set("ym", kv))

        fcol = ic.map(per_img).flatten()
        props = gee_call_with_retry(lambda: fcol.getInfo())
        return parse_reduce_features([f["properties"] for f in props["features"]], rename, keep)

    print(f"  ERA5 humidité sol : {len(years)} années...", flush=True)
    with ThreadPoolExecutor(max_workers=GETINFO_MAX_WORKERS) as ex:
        dfs = list(ex.map(one_year, sorted(years)))
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=keep)
    out["year"] = (out["ym"] // 100).astype("Int64")
    out["month"] = (out["ym"] % 100).astype("Int64")
    return out.drop(columns=["ym"])


# ── 5. Occupation du sol (MODIS MCD12Q1, annuel) ──────────────────────────────

def extract_land_cover_all(fc, years: list[int]) -> pd.DataFrame:
    """Mode IGBP (LC_Type1) par région × année (1 getInfo pour toutes les années)."""
    keep = ["region_id", "year", "land_cover_mode"]

    def _lc_image(year: int) -> ee.Image:
        coll = (
            ee.ImageCollection(MODIS_LC)
            .filter(ee.Filter.calendarRange(year, year, "year"))
            .select("LC_Type1")
        )
        real = coll.first().rename("lc")
        dummy = ee.Image.constant(0).rename("lc").updateMask(0)
        return ee.Image(ee.Algorithms.If(coll.size().gt(0), real, dummy)).set("year", year)

    ic = ee.ImageCollection([_lc_image(y) for y in years])

    def per_img(img):
        stats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mode(),
                                  scale=500, crs="EPSG:4326")
        return stats.map(lambda f: f.set("year", img.get("year")))

    print("  Occupation du sol (MODIS) : toutes années...", flush=True)
    fcol = ic.map(per_img).flatten()
    props = gee_call_with_retry(lambda: fcol.getInfo())
    return parse_reduce_features(
        [f["properties"] for f in props["features"]],
        {"mode": "land_cover_mode"}, keep,
    )


# ── 6. Baseline CHIRPS (cache one-time) ───────────────────────────────────────

def compute_chirps_baseline_stats(
    fc: ee.FeatureCollection,
    baseline_years: tuple[int, int] = CHIRPS_BASELINE_YEARS,
    cache_path: Path = PATHS["baseline_cache"],
) -> pd.DataFrame:
    """Moyenne décadaire historique CHIRPS (1981–2010) par région × décade-of-year.

    Résultat mis en cache (Parquet) : recalcul one-time.
    """
    if cache_path.exists():
        print(f"Baseline CHIRPS chargée depuis le cache : {cache_path}")
        return pd.read_parquet(cache_path)

    print(f"Calcul baseline CHIRPS {baseline_years[0]}–{baseline_years[1]} (36 décades × 30 ans)...")
    records = []
    start_yr, end_yr = baseline_years

    for month in range(1, 13):
        for part in (1, 2, 3):
            print(f"  Baseline mois={month:02d} partie={part}...", end=" ", flush=True)
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


# ── 7. Sources statiques ───────────────────────────────────────────────────────

def extract_dem(fc: ee.FeatureCollection) -> pd.DataFrame:
    """Altitude SRTM (moyenne, min, max) par région. Calculé une seule fois."""
    img = ee.Image(DEM_ASSET).select("elevation").rename("dem")
    df = _props_to_df(reduce_regions(img, fc, scale=30))
    df = df.rename(columns={"mean": "dem_mean", "min": "dem_min", "max": "dem_max"})
    keep = [c for c in ["region_id", "dem_mean", "dem_min", "dem_max"] if c in df.columns]
    return df[keep]


def extract_soil_texture(fc: ee.FeatureCollection) -> pd.DataFrame:
    """Texture du sol OpenLandMap (sable, argile, limon en %) par région.

    Les bandes b0 de SAND/CLAY-WFRACTION sont déjà en pourcentage (0–100).
    OpenLandMap ne publie pas de fraction limon : silt = 100 − sable − argile.
    """
    sand = ee.Image(OLM_SAND).select("b0").rename("sand")
    clay = ee.Image(OLM_CLAY).select("b0").rename("clay")
    silt = ee.Image.constant(100).subtract(sand).subtract(clay).rename("silt")
    img = ee.Image.cat([sand, clay, silt])

    df = _props_to_df(reduce_regions(img, fc, scale=250))
    df = df.rename(columns={"sand_mean": "soil_sand_mean", "clay_mean": "soil_clay_mean",
                            "silt_mean": "soil_silt_mean"})
    keep = [c for c in ["region_id", "soil_sand_mean", "soil_clay_mean", "soil_silt_mean"]
            if c in df.columns]
    return df[keep]


# ── 8. ENSO/ONI (source externe NOAA) ─────────────────────────────────────────

# L'ONI NOAA est une moyenne glissante trimestrielle ; chaque saison se rattache
# à son mois central (DJF→janvier, JFM→février, …, NDJ→décembre).
_ONI_SEASON_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}


def fetch_enso_oni() -> pd.DataFrame:
    """Télécharge et parse l'indice ONI depuis NOAA CPC (year, month, enso_oni).

    Format source : colonnes `SEAS YR TOTAL ANOM` (la saison trimestrielle est
    convertie en mois central, l'anomalie ANOM sert d'indice ONI).
    """
    print("Téléchargement ENSO/ONI depuis NOAA...")
    resp = requests.get(ENSO_URL, timeout=30)
    resp.raise_for_status()

    rows = []
    for line in resp.text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        month = _ONI_SEASON_MONTH.get(parts[0])
        if month is None:  # en-tête ou ligne non reconnue
            continue
        try:
            rows.append({"year": int(parts[1]), "month": month,
                         "enso_oni": float(parts[3])})
        except (ValueError, IndexError):
            continue

    df = pd.DataFrame(rows)
    print(f"  {len(df)} entrées ONI chargées ({df['year'].min()}–{df['year'].max()})")
    return df


# ── 9. Assemblage final ───────────────────────────────────────────────────────

def merge_static(df: pd.DataFrame, dem_df: pd.DataFrame, soil_df: pd.DataFrame,
                 enso_df: pd.DataFrame) -> pd.DataFrame:
    """Joint les features statiques (DEM, texture) et l'ONI à la table principale."""
    out = df.copy()
    if not dem_df.empty:
        out = out.merge(dem_df, on="region_id", how="left")
    if not soil_df.empty:
        out = out.merge(soil_df, on="region_id", how="left")
    if not enso_df.empty:
        out = out.merge(enso_df, on=["year", "month"], how="left")
    return out


# ── 10. Validation de la sortie ───────────────────────────────────────────────

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
        total = (df["soil_sand_mean"].fillna(0) + df["soil_clay_mean"].fillna(0)
                 + df["soil_silt_mean"].fillna(0))
        assert total.max() <= 120, f"Texture sol : somme > 120% ({total.max():.1f})"

    print(f"Validation OK — {len(df)} lignes, {len(df.columns)} colonnes")
    if "ndvi_mean" in df.columns:
        print(f"  NaN NDVI : {df['ndvi_mean'].isna().mean():.1%}")
    if "lst_mean" in df.columns:
        print(f"  NaN LST  : {df['lst_mean'].isna().mean():.1%}")


# ── 11. Test d'intégration ────────────────────────────────────────────────────

def run_integration_test(fc: ee.FeatureCollection, gdf: gpd.GeoDataFrame) -> None:
    """Teste chaque extracteur sur une seule région (rn_num=1) et une décade."""
    print("\n=== Test d'intégration : région 1, janvier 2010 D1 ===")
    region_id = int(gdf["rn_num"].iloc[0])
    fc_test = fc.filter(ee.Filter.eq("region_id", region_id))

    calendar = build_decade_calendar([2010])
    one = calendar[(calendar["month"] == 1) & (calendar["decade_part"] == 1)]
    did = int(one["decade_id"].iloc[0])

    def _one_spec(lead, lag):
        spec = next(s for s in build_specs(calendar, lead, lag)[2010] if s["id"] == did)
        return {2010: [spec]}

    df = extract_source(_chirps_image, _one_spec(0, 1), fc_test, 5566,
                        CHIRPS_RENAME, CHIRPS_KEEP, "CHIRPS")
    assert df.empty or (df["chirps_sum_mean"].dropna() >= 0).all(), "CHIRPS : négatif"
    print("  CHIRPS somme : OK")

    df = extract_source(_ndvi_evi_image, _one_spec(8, 9), fc_test, 250,
                        NDVI_RENAME, NDVI_KEEP, "NDVI/EVI")
    if not df.empty and "ndvi_mean" in df.columns:
        assert df["ndvi_mean"].dropna().between(-1, 1).all(), "NDVI hors plage"
    print("  NDVI/EVI     : OK")

    df = extract_source(_lst_image, _one_spec(4, 5), fc_test, 1000,
                        LST_RENAME, LST_KEEP, "LST")
    if not df.empty and "lst_mean" in df.columns:
        assert df["lst_mean"].dropna().between(200, 400).all(), "LST hors plage Kelvin"
    print("  LST          : OK")

    df = extract_soil_moisture_all(fc_test, [2010])
    if not df.empty and "soil_moisture_mean" in df.columns:
        assert df["soil_moisture_mean"].dropna().between(0, 1).all(), "Humidité hors [0,1]"
    print("  ERA5 sol     : OK")

    df = extract_dem(fc_test)
    if not df.empty and "dem_mean" in df.columns:
        assert (df["dem_mean"].dropna() >= 0).all(), "DEM : altitude négative"
    print("  DEM SRTM     : OK")

    df = extract_soil_texture(fc_test)
    if not df.empty and "soil_sand_mean" in df.columns:
        total = (df["soil_sand_mean"].fillna(0) + df["soil_clay_mean"].fillna(0)
                 + df["soil_silt_mean"].fillna(0))
        assert total.max() <= 120, f"Texture sol : somme > 120% ({total.max():.1f})"
    print("  Texture sol  : OK")

    enso = fetch_enso_oni()
    assert not enso.empty and "enso_oni" in enso.columns, "ENSO : DataFrame vide"
    print("  ENSO/ONI     : OK")

    print("=== Test d'intégration réussi ===\n")


# ── 12. Point d'entrée ────────────────────────────────────────────────────────

def init_gee() -> None:
    """Initialise GEE ; n'ouvre le flow d'authentification que si nécessaire."""
    try:
        ee.Initialize(project=GEE_PROJECT_ID)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=GEE_PROJECT_ID)


def run(years: list[int] = YEARS, test_only: bool = False) -> None:
    print(f"Initialisation GEE (projet : {GEE_PROJECT_ID})...")
    init_gee()
    print("GEE initialisé.")

    print(f"Chargement des régions naturelles : {PATHS['regions_shp']}")
    gdf, fc = load_regions(PATHS["regions_shp"])
    print(f"  {len(gdf)} régions chargées.")

    if test_only:
        run_integration_test(fc, gdf)
        return

    # Baseline CHIRPS (cache automatique)
    baseline_df = compute_chirps_baseline_stats(fc)

    # Extraction dynamique batch (côté serveur)
    print(f"\nExtraction dynamique (années {years[0]}–{years[-1]})")
    calendar, source_dfs = extract_dynamic(fc, years)

    # Assemblage décadaire + anomalie CHIRPS
    decades_df = assemble_decades(calendar, regions_table(gdf), source_dfs)
    decades_df = compute_chirps_anomaly(decades_df, baseline_df)

    # Sources mensuelles / annuelles
    sm_df = extract_soil_moisture_all(fc, years)
    lc_df = extract_land_cover_all(fc, years)
    decades_df = decades_df.merge(sm_df, on=["year", "month", "region_id"], how="left")
    decades_df = decades_df.merge(lc_df, on=["year", "region_id"], how="left")

    # Sources statiques + ENSO
    print("\nExtraction DEM SRTM...")
    dem_df = extract_dem(fc)
    print("Extraction texture du sol OpenLandMap...")
    soil_df = extract_soil_texture(fc)
    enso_df = fetch_enso_oni()

    print("\nAssemblage final...")
    full_df = merge_static(decades_df, dem_df, soil_df, enso_df)

    # Garde-fous + validation
    assert_decade_completeness(full_df, n_regions=len(gdf))
    validate_output(full_df)

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
