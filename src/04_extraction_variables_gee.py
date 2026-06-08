"""Pipeline #04 — Extraction des variables environnementales via Google Earth Engine.

Extrait NDVI/EVI (MODIS MOD13A2), LST (MODIS MOD11A2) et précipitations CHIRPS,
agrégés **à la décade** sur la **grille 1 km clipée** (issue 01) au lieu des régions
naturelles. Sortie : table cellule 1 km × décade alignée sur les labels du pipeline
03 (`cell_id`, `AIRE_CODE`, `campagne_calc`, `campagne_decade`).

Architecture (issue 10) :
- **Échantillonnage par centroïde** : 1 point par cellule (`image.sampleRegions`) au
  lieu d'un polygone. À 1 km, CHIRPS (~5,5 km natif) et LST (~1 km) ont ≤ 1 pixel par
  cellule : min/max/std intra-cellule sont du bruit → on ne garde que la moyenne.
- **Tiling par chunk de cellules** (`CELL_CHUNK_SIZE`) : les ~181 000 cellules
  saturent un seul getInfo. On découpe en tuiles bornées ; chaque tuile est traitée
  de bout en bout (extraction → assemblage → écriture) pour borner la mémoire.
- **Réduction décadaire mappée côté serveur** sur une ImageCollection (1 getInfo par
  source × année × tuile), avec **bissection automatique** des décades si un getInfo
  dépasse les limites GEE.
- La logique pure (calendrier, specs, assemblage, anomalie, garde-fous) vit dans
  `extraction_gee_helpers` et est testée sans dépendance GEE.

Sortie : data/processed/04_variables_environnementales/  (dataset Parquet partitionné)

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

sys.path.insert(0, str(Path(__file__).parent))
from config_gee import (
    CELL_CHUNK_SIZE,
    CHIRPS_BASELINE_YEARS,
    CHIRPS_COLLECTION,
    GEE_PROJECT_ID,
    MAX_RETRIES,
    MODIS_LST,
    MODIS_NDVI_EVI,
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

# tileScale relève la mémoire serveur par tuile interne au prix du débit — utile
# sur des sampleRegions denses (beaucoup de points par requête).
SAMPLE_TILE_SCALE = 4


# ── 1. Chargement de la grille 1 km ─────────────────────────────────────────────

def load_grid(grille_path: Path) -> gpd.GeoDataFrame:
    """Charge la grille 1 km clipée et calcule le centroïde (lon/lat) de chaque cellule.

    Le centroïde est calculé en CRS projeté (UTM 38S, métrique) puis reprojeté en
    EPSG:4326 pour GEE. Retourne un GeoDataFrame indexé par `cell_id` avec colonnes
    `cell_id`, `AIRE_CODE`, `lon`, `lat`.
    """
    gdf = gpd.read_parquet(grille_path)
    assert gdf["cell_id"].is_unique, "cell_id doit être unique dans la grille"

    cent = gdf.geometry.centroid.to_crs("EPSG:4326")
    out = pd.DataFrame({
        "cell_id": gdf["cell_id"].astype(str).values,
        "AIRE_CODE": gdf["AIRE_CODE"].values,
        "lon": cent.x.values,
        "lat": cent.y.values,
    })
    return out


def cells_table(cells_df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame (cell_id, AIRE_CODE) servant de base à l'assemblage décadaire."""
    return cells_df[["cell_id", "AIRE_CODE"]].copy()


def chunk_cells(cells_df: pd.DataFrame, chunk_size: int = CELL_CHUNK_SIZE) -> list[pd.DataFrame]:
    """Découpe la grille en tuiles de ≤ chunk_size cellules (tiling spatial)."""
    return [cells_df.iloc[i:i + chunk_size] for i in range(0, len(cells_df), chunk_size)]


def points_fc(chunk_df: pd.DataFrame) -> ee.FeatureCollection:
    """Construit une FeatureCollection de centroïdes **côté serveur**.

    On envoie deux listes plates (coordonnées + cell_id) plutôt que N `ee.Feature`
    construits côté client : payload léger même à plusieurs milliers de points.
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


# ── 3. Composites décadaires (côté serveur) ────────────────────────────────────

def _safe_image(real: ee.Image, dummy: ee.Image, coll: ee.ImageCollection, key_val) -> ee.Image:
    """Renvoie `real` si la collection est non vide, sinon `dummy` (masqué).

    Garantit un objet image valide même décade vide. Avec sampleRegions, un pixel
    masqué ne produit aucun échantillon → la cellule absente devient NaN au merge
    gauche de `assemble_decades`.
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


def _sample_specs(image_fn, specs: list[dict], fc_pts, scale: int,
                  key: str = "decade_id") -> list[dict]:
    """Mappe sampleRegions côté serveur sur l'IC des composites, retourne les props.

    En cas d'échec getInfo (taille/timeout), bissection récursive des specs
    (fallback automatique) jusqu'à 1 spec.
    """
    ic = ee.ImageCollection([image_fn(s) for s in specs])

    def per_img(img):
        samples = img.sampleRegions(
            collection=fc_pts, properties=["cell_id"], scale=scale,
            tileScale=SAMPLE_TILE_SCALE, geometries=False,
        )
        kv = img.get(key)
        return samples.map(lambda f: f.set(key, kv))

    fcol = ic.map(per_img).flatten()
    try:
        result = gee_call_with_retry(lambda: fcol.getInfo())
        return [f["properties"] for f in result["features"]]
    except ee.EEException:
        if len(specs) <= 1:
            raise
        mid = len(specs) // 2
        print(f"    getInfo trop volumineux ({len(specs)} composites) — bissection")
        return (_sample_specs(image_fn, specs[:mid], fc_pts, scale, key)
                + _sample_specs(image_fn, specs[mid:], fc_pts, scale, key))


def extract_source(image_fn, specs_by_year: dict, fc_pts, scale: int,
                   rename: dict, keep: list[str], label: str) -> pd.DataFrame:
    """Extrait une source dynamique sur toutes les années (getInfo parallélisés)."""
    years = sorted(specs_by_year)

    def one_year(year: int) -> pd.DataFrame:
        props = _sample_specs(image_fn, specs_by_year[year], fc_pts, scale)
        return parse_reduce_features(props, rename, keep)

    with ThreadPoolExecutor(max_workers=GETINFO_MAX_WORKERS) as ex:
        dfs = list(ex.map(one_year, years))
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=keep)
    print(f"    {label} OK ({len(out)} lignes)")
    return out


# Constantes de renommage / colonnes par source.
# sampleRegions nomme chaque propriété d'après la bande échantillonnée (valeur
# ponctuelle = moyenne de la cellule, suffixe `_mean` conservé pour l'aval).
CHIRPS_RENAME = {"chirps_sum": "chirps_sum_mean"}
CHIRPS_KEEP = ["cell_id", "decade_id", "chirps_sum_mean"]

NDVI_RENAME = {"NDVI": "ndvi_mean", "EVI": "evi_mean"}
NDVI_KEEP = ["cell_id", "decade_id", "ndvi_mean", "evi_mean"]

LST_RENAME = {"lst": "lst_mean"}
LST_KEEP = ["cell_id", "decade_id", "lst_mean"]


def extract_dynamic_chunk(fc_pts, calendar: pd.DataFrame) -> list[pd.DataFrame]:
    """Extrait CHIRPS + NDVI/EVI + LST pour une tuile de cellules (table longue)."""
    chirps_df = extract_source(_chirps_image, build_specs(calendar, 0, 1), fc_pts, 5566,
                               CHIRPS_RENAME, CHIRPS_KEEP, "CHIRPS")
    ndvi_df = extract_source(_ndvi_evi_image, build_specs(calendar, 8, 9), fc_pts, 250,
                             NDVI_RENAME, NDVI_KEEP, "NDVI/EVI")
    lst_df = extract_source(_lst_image, build_specs(calendar, 4, 5), fc_pts, 1000,
                            LST_RENAME, LST_KEEP, "LST")
    return [chirps_df, ndvi_df, lst_df]


# ── 4. Baseline CHIRPS (cache one-time, par cellule × décade-of-year) ──────────

BASELINE_RENAME = {"chirps_baseline": "chirps_baseline_mean"}
BASELINE_KEEP = ["cell_id", "doy_id", "chirps_baseline_mean"]


def _baseline_image_fn(baseline_years: tuple[int, int]):
    """Fabrique le builder d'image baseline (moyenne historique d'une décade-of-year)."""
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


def compute_chirps_baseline_stats(
    chunks: list[pd.DataFrame],
    baseline_years: tuple[int, int] = CHIRPS_BASELINE_YEARS,
    cache_path: Path = PATHS["baseline_cache"],
) -> pd.DataFrame:
    """Moyenne décadaire historique CHIRPS par cellule × décade-of-year (36 décades).

    Résultat mis en cache (Parquet) : recalcul one-time. `doy_id = month*10 + part`.
    """
    if cache_path.exists():
        print(f"Baseline CHIRPS chargée depuis le cache : {cache_path}")
        return pd.read_parquet(cache_path)

    print(f"Calcul baseline CHIRPS {baseline_years[0]}–{baseline_years[1]} "
          f"(36 décades × {len(chunks)} tuiles)...")
    image_fn = _baseline_image_fn(baseline_years)
    specs = [{"id": m * 10 + p, "month": m, "part": p}
             for m in range(1, 13) for p in (1, 2, 3)]

    parts = []
    for ci, chunk in enumerate(chunks):
        fc_pts = points_fc(chunk)
        props = _sample_specs(image_fn, specs, fc_pts, 5566, key="doy_id")
        parts.append(parse_reduce_features(props, BASELINE_RENAME, BASELINE_KEEP))
        print(f"  tuile {ci + 1}/{len(chunks)} OK")

    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=BASELINE_KEEP)
    df["month"] = (df["doy_id"] // 10).astype("Int64")
    df["decade_part"] = (df["doy_id"] % 10).astype("Int64")
    df = df.drop(columns=["doy_id"])

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    print(f"Baseline sauvegardée : {cache_path} ({len(df)} lignes)")
    return df


# ── 5. Validation de la sortie ─────────────────────────────────────────────────

def validate_ranges(df: pd.DataFrame) -> None:
    """Vérifie clés non nulles + plages physiques. Lève AssertionError si invalide."""
    for col in ["cell_id", "AIRE_CODE", "campagne_calc", "campagne_decade", "date_start"]:
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


# ── 6. Test d'intégration ──────────────────────────────────────────────────────

def run_integration_test(cells_df: pd.DataFrame) -> None:
    """Teste chaque extracteur sur une seule cellule et une décade (janvier 2010 D1)."""
    print("\n=== Test d'intégration : 1 cellule, janvier 2010 D1 ===")
    fc_pts = points_fc(cells_df.iloc[[0]])
    print(f"  cellule de test : {cells_df['cell_id'].iloc[0]}")

    calendar = build_decade_calendar([2010])
    one = calendar[(calendar["month"] == 1) & (calendar["decade_part"] == 1)]
    did = int(one["decade_id"].iloc[0])

    def _one_spec(lead, lag):
        spec = next(s for s in build_specs(calendar, lead, lag)[2010] if s["id"] == did)
        return {2010: [spec]}

    df = extract_source(_chirps_image, _one_spec(0, 1), fc_pts, 5566,
                        CHIRPS_RENAME, CHIRPS_KEEP, "CHIRPS")
    assert df.empty or (df["chirps_sum_mean"].dropna() >= 0).all(), "CHIRPS : négatif"
    print("  CHIRPS somme : OK")

    df = extract_source(_ndvi_evi_image, _one_spec(8, 9), fc_pts, 250,
                        NDVI_RENAME, NDVI_KEEP, "NDVI/EVI")
    if not df.empty and "ndvi_mean" in df.columns:
        assert df["ndvi_mean"].dropna().between(-1, 1).all(), "NDVI hors plage"
    print("  NDVI/EVI     : OK")

    df = extract_source(_lst_image, _one_spec(4, 5), fc_pts, 1000,
                        LST_RENAME, LST_KEEP, "LST")
    if not df.empty and "lst_mean" in df.columns:
        assert df["lst_mean"].dropna().between(200, 400).all(), "LST hors plage Kelvin"
    print("  LST          : OK")

    print("=== Test d'intégration réussi ===\n")


# ── 7. Point d'entrée ──────────────────────────────────────────────────────────

def init_gee() -> None:
    """Initialise GEE ; n'ouvre le flow d'authentification que si nécessaire."""
    try:
        ee.Initialize(project=GEE_PROJECT_ID)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=GEE_PROJECT_ID)


def _prepare_output_dir(out_dir: Path) -> None:
    """Crée le dataset partitionné et purge les parts d'un run précédent."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("part-*.parquet"):
        old.unlink()


def run(years: list[int] = YEARS, test_only: bool = False) -> None:
    print(f"Initialisation GEE (projet : {GEE_PROJECT_ID})...")
    init_gee()
    print("GEE initialisé.")

    print(f"Chargement de la grille 1 km : {PATHS['grille_parquet']}")
    cells_df = load_grid(PATHS["grille_parquet"])
    print(f"  {len(cells_df)} cellules chargées.")

    if test_only:
        run_integration_test(cells_df)
        return

    chunks = chunk_cells(cells_df)
    print(f"  {len(chunks)} tuiles de ≤ {CELL_CHUNK_SIZE} cellules.")

    # Baseline CHIRPS (cache automatique, toutes tuiles)
    baseline_df = compute_chirps_baseline_stats(chunks)

    calendar = build_decade_calendar(years)
    out_dir = PATHS["output_dir"]
    _prepare_output_dir(out_dir)

    print(f"\nExtraction dynamique (années {years[0]}–{years[-1]})")
    total_rows = 0
    for ci, chunk in enumerate(chunks):
        print(f"\n── Tuile {ci + 1}/{len(chunks)} ({len(chunk)} cellules) ──")
        fc_pts = points_fc(chunk)
        source_dfs = extract_dynamic_chunk(fc_pts, calendar)

        part = assemble_decades(calendar, cells_table(chunk), source_dfs)
        part = compute_chirps_anomaly(part, baseline_df)

        assert_decade_completeness(part, n_cells=len(chunk))
        validate_ranges(part)

        part_path = out_dir / f"part-{ci:04d}.parquet"
        part.to_parquet(part_path, index=False)
        total_rows += len(part)
        print(f"  écrit {part_path.name} ({len(part)} lignes)")

    print(f"\nSortie : {out_dir}/")
    print(f"  {len(chunks)} parts, {total_rows} lignes au total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline #04 — Extraction GEE (grille 1 km)")
    parser.add_argument(
        "--test-only", action="store_true",
        help="Exécute uniquement le test d'intégration (1 cellule × 1 décade)"
    )
    parser.add_argument(
        "--years", nargs="+", type=int, default=YEARS,
        help="Années civiles à extraire (ex. --years 2010 2011)"
    )
    args = parser.parse_args()
    run(years=args.years, test_only=args.test_only)
