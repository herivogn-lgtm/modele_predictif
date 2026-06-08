"""Configuration pour le pipeline #04 — Extraction GEE.

Renseigner GEE_PROJECT_ID avant d'exécuter 04_extraction_variables_gee.py.
"""

from pathlib import Path

# ── À RENSEIGNER ─────────────────────────────────────────────────────────────
GEE_PROJECT_ID = "ee-tojoniriina"

# ── Chemins ───────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"

# Grille 1 km clipée (issue 01) = emprise partagée entraînement/prédiction.
# `output_dir` est un dataset Parquet *partitionné* (un fichier par chunk de
# cellules) : à ~181 000 cellules × ~780 décades la table fait ~141 M lignes,
# trop volumineuse pour un seul fichier en mémoire — lecture aval via
# pd.read_parquet(<dir>).
PATHS = {
    "grille_parquet": DATA_DIR / "processed" / "01_grille_1km.parquet",
    "output_dir": DATA_DIR / "processed" / "04_variables_environnementales",
    "baseline_cache": DATA_DIR / "processed" / "04_chirps_baseline_cache.parquet",
}

# Nombre de cellules par tuile (1 getInfo borné). Tiling spatial pour ne pas
# saturer reduceRegions/sampleRegions sur les ~181 000 cellules d'un coup.
CELL_CHUNK_SIZE = 5000

# ── Plage temporelle ──────────────────────────────────────────────────────────
YEARS = list(range(2001, 2027))
CHIRPS_BASELINE_YEARS = (1981, 2010)

# ── Retry GEE ─────────────────────────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2  # secondes, exponentiel

# ── Collections GEE ───────────────────────────────────────────────────────────
# Périmètre pivot cellule 1 km (issue 03/10) : 3 sources dynamiques seulement.
# ERA5 humidité sol, MODIS land-cover, SRTM DEM, texture OpenLandMap et ENSO/ONI
# ont été retirés (hors périmètre issue 03 ; à rouvrir dans un ticket dédié si
# le feature engineering 05 en a besoin).
CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
MODIS_NDVI_EVI = "MODIS/061/MOD13A2"  # 16-day, 250m
MODIS_LST = "MODIS/061/MOD11A2"  # 8-day, 1km
