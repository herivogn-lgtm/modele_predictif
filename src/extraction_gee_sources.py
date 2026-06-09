"""Primitives GEE partagées entre les pipelines d'extraction (04 getInfo et 04b Export).

Centralise tout ce qui dépend de `ee` et définit **comment** chaque covariable est
calculée (collections, QA, composites décadaires, échantillonnage par centroïde),
pour que les deux orchestrations (`getInfo` interactif vs `Export.table` batch)
produisent des valeurs strictement identiques.

La logique *pure* (calendrier, specs, assemblage, anomalie) reste dans
`extraction_gee_helpers` (testable sans `ee`).
"""

from datetime import timedelta
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd

from config_gee import (
    CHIRPS_COLLECTION,
    GEE_PROJECT_ID,
    MODIS_LST,
    MODIS_NDVI_EVI,
)
from extraction_gee_helpers import decade_bounds

# tileScale relève la mémoire serveur par tuile interne au prix du débit — utile
# sur des sampleRegions denses (beaucoup de points par requête).
SAMPLE_TILE_SCALE = 4


# ── Initialisation ──────────────────────────────────────────────────────────────

def init_gee() -> None:
    """Initialise GEE ; n'ouvre le flow d'authentification que si nécessaire."""
    try:
        ee.Initialize(project=GEE_PROJECT_ID)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=GEE_PROJECT_ID)


# ── Grille 1 km → centroïdes ────────────────────────────────────────────────────

def load_grid(grille_path: Path) -> pd.DataFrame:
    """Charge la grille 1 km clipée et calcule le centroïde (lon/lat) de chaque cellule.

    Centroïde calculé en CRS projeté (UTM 38S, métrique) puis reprojeté en EPSG:4326.
    Retourne un DataFrame `cell_id`, `AIRE_CODE`, `lon`, `lat`.
    """
    gdf = gpd.read_parquet(grille_path)
    assert gdf["cell_id"].is_unique, "cell_id doit être unique dans la grille"

    cent = gdf.geometry.centroid.to_crs("EPSG:4326")
    return pd.DataFrame({
        "cell_id": gdf["cell_id"].astype(str).values,
        "AIRE_CODE": gdf["AIRE_CODE"].values,
        "lon": cent.x.values,
        "lat": cent.y.values,
    })


def cells_table(cells_df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame (cell_id, AIRE_CODE) servant de base à l'assemblage décadaire."""
    return cells_df[["cell_id", "AIRE_CODE"]].copy()


def points_fc(chunk_df: pd.DataFrame) -> ee.FeatureCollection:
    """Construit une FeatureCollection de centroïdes **côté serveur**.

    On envoie deux listes plates (coordonnées + cell_id) plutôt que N `ee.Feature`
    construits côté client : payload léger. NB : l'expression sérialisée grossit avec
    le nombre de points → tuiler en amont (cf. limite de taille de requête GEE).
    """
    coords = ee.List([[float(x), float(y)]
                      for x, y in zip(chunk_df["lon"], chunk_df["lat"])])
    ids = ee.List([str(c) for c in chunk_df["cell_id"]])

    def make(i):
        i = ee.Number(i)
        return ee.Feature(
            ee.Geometry.Point(ee.List(coords.get(i))),
            {"cell_id": ids.get(i)},
        )

    return ee.FeatureCollection(
        ee.List.sequence(0, coords.size().subtract(1)).map(make)
    )


# ── Composites décadaires (côté serveur) ────────────────────────────────────────

def safe_image(real: ee.Image, dummy: ee.Image, coll: ee.ImageCollection, key_val) -> ee.Image:
    """Renvoie `real` si la collection est non vide, sinon `dummy` (masqué).

    Garantit un objet image valide même décade vide. Avec sampleRegions, un pixel
    masqué ne produit aucun échantillon → la cellule absente devient NaN au merge
    gauche de `assemble_decades`.
    """
    img = ee.Image(ee.Algorithms.If(coll.size().gt(0), real, dummy))
    return img.set("decade_id", key_val)


def chirps_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(CHIRPS_COLLECTION)
        .filterDate(spec["start"], spec["end"])
        .select("precipitation")
    )
    real = coll.sum().rename("chirps_sum")
    dummy = ee.Image.constant(0).rename("chirps_sum").updateMask(0)
    return safe_image(real, dummy, coll, spec["id"])


def _apply_modis_ndvi_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD13A2 (bits 0-1 de DetailedQA > 1)."""
    qa = image.select("DetailedQA")
    return image.updateMask(qa.bitwiseAnd(3).lte(1))


def ndvi_evi_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(MODIS_NDVI_EVI)
        .filterDate(spec["start"], spec["end"])
        .map(_apply_modis_ndvi_qa)
        .select(["NDVI", "EVI"])
    )
    real = coll.sort("system:time_start", False).first().multiply(0.0001)
    dummy = ee.Image.constant([0, 0]).rename(["NDVI", "EVI"]).updateMask(0)
    return safe_image(real, dummy, coll, spec["id"])


def _apply_modis_lst_qa(image: ee.Image) -> ee.Image:
    """Masque les pixels de faible qualité de MOD11A2 (bits 0-1 de QC_Day != 0)."""
    qa = image.select("QC_Day")
    return image.updateMask(qa.bitwiseAnd(3).eq(0))


def lst_image(spec: dict) -> ee.Image:
    coll = (
        ee.ImageCollection(MODIS_LST)
        .filterDate(spec["start"], spec["end"])
        .map(_apply_modis_lst_qa)
        .select("LST_Day_1km")
    )
    real = coll.sort("system:time_start", False).first().multiply(0.02).rename("lst")
    dummy = ee.Image.constant(0).rename("lst").updateMask(0)
    return safe_image(real, dummy, coll, spec["id"])


def baseline_image_fn(baseline_years: tuple[int, int]):
    """Fabrique le builder d'image baseline (moyenne historique CHIRPS d'une décade-of-year)."""
    start_yr, end_yr = baseline_years

    def _img(spec: dict) -> ee.Image:
        month, part = spec["month"], spec["part"]
        sums = []
        for y in range(start_yr, end_yr + 1):
            d_start, d_end = decade_bounds(y, month, part)
            sums.append(
                ee.ImageCollection(CHIRPS_COLLECTION)
                .filterDate(d_start.strftime("%Y-%m-%d"),
                            (d_end + timedelta(days=1)).strftime("%Y-%m-%d"))
                .select("precipitation")
                .sum()
            )
        mean_img = ee.ImageCollection(sums).mean().rename("chirps_baseline")
        return mean_img.set("doy_id", spec["id"])

    return _img


# ── Échantillonnage par centroïde (commun aux deux pipelines) ────────────────────

def sample_fc(image_fn, specs: list[dict], fc_pts: ee.FeatureCollection, scale: int,
              key: str = "decade_id") -> ee.FeatureCollection:
    """Mappe sampleRegions côté serveur sur l'IC des composites → FeatureCollection plate.

    1 feature par (cellule, composite) avec `cell_id`, la clé temporelle (`key`) et
    les bandes échantillonnées. Le pipeline getInfo l'appelle puis `.getInfo()` ;
    le pipeline Export la passe à `Export.table`.
    """
    ic = ee.ImageCollection([image_fn(s) for s in specs])

    def per_img(img):
        samples = img.sampleRegions(
            collection=fc_pts, properties=["cell_id"], scale=scale,
            tileScale=SAMPLE_TILE_SCALE, geometries=False,
        )
        kv = img.get(key)
        return samples.map(lambda f: f.set(key, kv))

    return ic.map(per_img).flatten()


# ── Renommage / colonnes par source ─────────────────────────────────────────────
# sampleRegions nomme chaque propriété d'après la bande échantillonnée (valeur
# ponctuelle = moyenne de la cellule, suffixe `_mean` conservé pour l'aval).

CHIRPS_RENAME = {"chirps_sum": "chirps_sum_mean"}
CHIRPS_KEEP = ["cell_id", "decade_id", "chirps_sum_mean"]

NDVI_RENAME = {"NDVI": "ndvi_mean", "EVI": "evi_mean"}
NDVI_KEEP = ["cell_id", "decade_id", "ndvi_mean", "evi_mean"]

LST_RENAME = {"lst": "lst_mean"}
LST_KEEP = ["cell_id", "decade_id", "lst_mean"]

BASELINE_RENAME = {"chirps_baseline": "chirps_baseline_mean"}
BASELINE_KEEP = ["cell_id", "doy_id", "chirps_baseline_mean"]

# Registre des sources dynamiques : décrit chaque covariable de façon uniforme pour
# que les deux orchestrations bouclent dessus à l'identique.
#   lead/lag : élargissement de la fenêtre temporelle passé à build_specs.
#   scale    : résolution d'échantillonnage (m).
#   bands    : noms bruts des bandes échantillonnées (= colonnes des sélecteurs Export).
DYNAMIC_SOURCES = [
    {"name": "CHIRPS", "image_fn": chirps_image, "lead": 0, "lag": 1, "scale": 5566,
     "rename": CHIRPS_RENAME, "keep": CHIRPS_KEEP, "bands": ["chirps_sum"]},
    {"name": "NDVI_EVI", "image_fn": ndvi_evi_image, "lead": 8, "lag": 9, "scale": 250,
     "rename": NDVI_RENAME, "keep": NDVI_KEEP, "bands": ["NDVI", "EVI"]},
    {"name": "LST", "image_fn": lst_image, "lead": 4, "lag": 5, "scale": 1000,
     "rename": LST_RENAME, "keep": LST_KEEP, "bands": ["lst"]},
]
