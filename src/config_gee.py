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
    # Labels cellule × décade (issue 03) : définit les cellules **observées**
    # (~3 % de la grille) = périmètre par défaut de l'extraction d'entraînement.
    "labels_cellule": DATA_DIR / "processed" / "03_labels_cellule_decade.parquet",
    "output_dir": DATA_DIR / "processed" / "04_variables_environnementales",
    "baseline_cache": DATA_DIR / "processed" / "04_chirps_baseline_cache.parquet",
    # Pipeline 04b : dossier local où l'utilisateur dépose les CSV téléchargés
    # depuis Drive (sortie des tâches Export) avant l'étape --assemble.
    "exports_dir": DATA_DIR / "processed" / "04_exports_drive",
}

# Nombre de cellules par tuile. GEE abandonne tout getInfo de FeatureCollection
# au-delà de **5000 éléments** ; comme la bissection ne réduit que la dimension
# décades, la tuile doit rester < 5000 cellules pour qu'un appel mono-décade
# (cells × 1) tienne. Marge volontaire sous 5000.
CELL_CHUNK_SIZE = 4500

# ── Pipeline 04b (Export.table, sans plafond 5000) ──────────────────────────────
# Cellules par tâche d'export : borne la taille de l'expression FC envoyée à GEE
# (pas de limite sur le nombre de lignes exportées, contrairement à getInfo).
POINT_EXPORT_TILE = 15000
# Dossier Google Drive cible des tâches Export (créé automatiquement par GEE).
EXPORT_DRIVE_FOLDER = "ee_exports_locusta_v04"
# Années par tâche dynamique. Mettre TOUTES les années dans une tâche rend chaque
# tâche gigantesque (780 décades × 15k points → heures + milliers d'EECU-h) : on
# borne à quelques années → tâches courtes, reprenables, peu coûteuses.
YEARS_PER_TASK = 3

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
