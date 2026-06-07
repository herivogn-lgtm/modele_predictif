"""Configuration pour le pipeline #04 — Extraction GEE.

Renseigner GEE_PROJECT_ID avant d'exécuter 04_extraction_variables_gee.py.
"""

from pathlib import Path

# ── À RENSEIGNER ─────────────────────────────────────────────────────────────
GEE_PROJECT_ID = "ee-tojoniriina"

# ── Chemins ───────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"

PATHS = {
    "regions_shp": DATA_DIR / "region_naturelle" / "region_naturelle.shp",
    "output_parquet": DATA_DIR / "processed" / "04_variables_environnementales.parquet",
    "baseline_cache": DATA_DIR / "processed" / "04_chirps_baseline_cache.parquet",
}

# ── Plage temporelle ──────────────────────────────────────────────────────────
YEARS = list(range(2001, 2027))
CHIRPS_BASELINE_YEARS = (1981, 2010)

# ── Retry GEE ─────────────────────────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2  # secondes, exponentiel

# ── Collections GEE ───────────────────────────────────────────────────────────
CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
MODIS_NDVI_EVI = "MODIS/061/MOD13A2"  # 16-day, 250m
MODIS_LST = "MODIS/061/MOD11A2"  # 8-day, 1km
ERA5_MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
MODIS_LC = "MODIS/061/MCD12Q1"  # annuel, 500m
# OpenLandMap ne publie que SAND et CLAY (valeurs déjà en %).
# Le limon (silt) se déduit par 100 − sable − argile.
OLM_SAND = "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02"
OLM_CLAY = "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02"
DEM_ASSET = "USGS/SRTMGL1_003"

# ── Source externe ────────────────────────────────────────────────────────────
ENSO_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
