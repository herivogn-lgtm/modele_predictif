"""Pipeline #04 — Extraction des variables environnementales via Google Earth Engine (getInfo).

Extrait NDVI/EVI (MODIS MOD13A2), LST (MODIS MOD11A2) et précipitations CHIRPS,
agrégés **à la décade** sur la **grille 1 km clipée** (issue 01). Sortie : table
cellule 1 km × décade alignée sur les labels du pipeline 03 (`cell_id`, `AIRE_CODE`,
`campagne_calc`, `campagne_decade`).

Architecture (issue 10) — variante **getInfo interactif** :
- Échantillonnage par centroïde (`sampleRegions`, 1 point/cellule). À 1 km, CHIRPS
  (~5,5 km) et LST (~1 km) ont ≤ 1 pixel/cellule → on ne garde que la moyenne.
- GEE abandonne tout getInfo de FeatureCollection au-delà de **5000 éléments** ;
  le nombre de features = cellules × décades de l'appel. On **sous-tuile les
  cellules** (~150/appel) pour packer un an de décades sous 5000, avec bissection
  des décades en filet de sécurité.
- Réduction décadaire mappée côté serveur (`extraction_gee_sources.sample_fc`).

⚠️ À ~181 000 cellules cette variante demande ~86 000 getInfo (~heures). Pour un
run historique one-shot, préférer `04b_export_variables_gee.py` (Export.table, sans
le plafond de 5000). Les deux pipelines partagent `extraction_gee_sources` → valeurs
identiques.

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
from pathlib import Path

import ee
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config_gee import (
    CELL_CHUNK_SIZE,
    CHIRPS_BASELINE_YEARS,
    MAX_RETRIES,
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
    parse_reduce_features,
)
from extraction_gee_sources import (
    BASELINE_KEEP,
    BASELINE_RENAME,
    DYNAMIC_SOURCES,
    baseline_image_fn,
    cells_table,
    init_gee,
    load_grid,
    points_fc,
    sample_fc,
)

# Nombre de getInfo concurrents (GEE sert les requêtes en parallèle ; getInfo est
# thread-safe côté client). Borne raisonnable pour ne pas saturer le quota.
GETINFO_MAX_WORKERS = 6

# Budget d'éléments par getInfo (< limite GEE de 5000). Le nombre de features
# renvoyées = cellules × décades de l'appel : on **sous-tuile les cellules** pour
# que tout un an (≈30 décades) tienne en un seul appel propre (≈150 cellules),
# au lieu de forcer la bissection à descendre à 1 décade par appel.
GETINFO_ELEMENT_BUDGET = 4500


# ── 1. Tiling des cellules ──────────────────────────────────────────────────────

def chunk_cells(cells_df: pd.DataFrame, chunk_size: int = CELL_CHUNK_SIZE) -> list[pd.DataFrame]:
    """Découpe la grille en tuiles de ≤ chunk_size cellules (unité d'écriture)."""
    return [cells_df.iloc[i:i + chunk_size] for i in range(0, len(cells_df), chunk_size)]


def _cell_batches(chunk_df: pd.DataFrame, n_specs: int):
    """Sous-tuile les cellules pour qu'un appel (cellules × n_specs) tienne sous le budget."""
    batch = max(1, GETINFO_ELEMENT_BUDGET // max(1, n_specs))
    for i in range(0, len(chunk_df), batch):
        yield chunk_df.iloc[i:i + batch]


# ── 2. Utilitaires getInfo ───────────────────────────────────────────────────────

# Erreurs déterministes liées à la taille/au coût d'un getInfo : inutile de
# retenter à l'identique (perte de temps) — on les laisse remonter pour que la
# bissection des specs réduise immédiatement le volume de l'appel.
_SIZE_ERROR_MARKERS = (
    "aborted after accumulating",       # > 5000 éléments dans la FeatureCollection
    "Collection query aborted",
    "Computation timed out",
    "User memory limit exceeded",
    "payload size exceeds",
)


def _is_size_error(exc: Exception) -> bool:
    msg = str(exc)
    return any(m in msg for m in _SIZE_ERROR_MARKERS)


def gee_call_with_retry(fn):
    """Exécute fn() avec retry exponentiel sur EEException **transitoire** (rate limit / 5xx).

    Les erreurs de taille/coût (déterministes) remontent immédiatement → gérées
    par la bissection en amont.
    """
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except ee.EEException as exc:
            if _is_size_error(exc):
                raise
            last_exc = exc
            wait = RETRY_BACKOFF_BASE**attempt
            print(f"    GEE erreur (tentative {attempt + 1}/{MAX_RETRIES}): {exc} — attente {wait}s")
            time.sleep(wait)
    raise last_exc


def _sample_specs(image_fn, specs: list[dict], fc_pts, scale: int,
                  key: str = "decade_id") -> list[dict]:
    """sampleRegions côté serveur → getInfo, avec bissection des specs si trop volumineux."""
    fcol = sample_fc(image_fn, specs, fc_pts, scale, key)
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


# ── 3. Extraction dynamique (par tuile) ──────────────────────────────────────────

def extract_source(image_fn, specs_by_year: dict, chunk_df: pd.DataFrame, scale: int,
                   rename: dict, keep: list[str], label: str) -> pd.DataFrame:
    """Extrait une source dynamique : 1 getInfo par (an × sous-tuile de cellules).

    Chaque appel couvre toutes les décades d'une année sur un paquet de cellules
    dimensionné pour tenir sous le budget GEE. Appels parallélisés.
    """
    units = [(specs_by_year[y], sub)
             for y in sorted(specs_by_year)
             for sub in _cell_batches(chunk_df, len(specs_by_year[y]))]

    def one(unit) -> pd.DataFrame:
        specs, sub = unit
        props = _sample_specs(image_fn, specs, points_fc(sub), scale)
        return parse_reduce_features(props, rename, keep)

    with ThreadPoolExecutor(max_workers=GETINFO_MAX_WORKERS) as ex:
        dfs = list(ex.map(one, units))
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=keep)
    print(f"    {label} OK ({len(out)} lignes)")
    return out


def extract_dynamic_chunk(chunk_df: pd.DataFrame, calendar: pd.DataFrame) -> list[pd.DataFrame]:
    """Extrait toutes les sources dynamiques (registre) pour une tuile de cellules."""
    out = []
    for src in DYNAMIC_SOURCES:
        specs = build_specs(calendar, src["lead"], src["lag"])
        out.append(extract_source(src["image_fn"], specs, chunk_df, src["scale"],
                                  src["rename"], src["keep"], src["name"]))
    return out


# ── 4. Baseline CHIRPS (cache one-time, par cellule × décade-of-year) ────────────

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
    image_fn = baseline_image_fn(baseline_years)
    specs = [{"id": m * 10 + p, "month": m, "part": p}
             for m in range(1, 13) for p in (1, 2, 3)]

    parts = []
    for ci, chunk in enumerate(chunks):
        for sub in _cell_batches(chunk, len(specs)):
            props = _sample_specs(image_fn, specs, points_fc(sub), 5566, key="doy_id")
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


# ── 5. Validation de la sortie ───────────────────────────────────────────────────

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


# ── 6. Test d'intégration ────────────────────────────────────────────────────────

def run_integration_test(cells_df: pd.DataFrame) -> None:
    """Teste chaque extracteur sur une seule cellule et une décade (janvier 2010 D1)."""
    print("\n=== Test d'intégration : 1 cellule, janvier 2010 D1 ===")
    one_cell = cells_df.iloc[[0]]
    print(f"  cellule de test : {one_cell['cell_id'].iloc[0]}")

    calendar = build_decade_calendar([2010])
    one = calendar[(calendar["month"] == 1) & (calendar["decade_part"] == 1)]
    did = int(one["decade_id"].iloc[0])

    for src in DYNAMIC_SOURCES:
        spec = next(s for s in build_specs(calendar, src["lead"], src["lag"])[2010]
                    if s["id"] == did)
        df = extract_source(src["image_fn"], {2010: [spec]}, one_cell, src["scale"],
                            src["rename"], src["keep"], src["name"])
        validate_ranges_partial(df, src["name"])
        print(f"  {src['name']:8s} : OK")

    print("=== Test d'intégration réussi ===\n")


def validate_ranges_partial(df: pd.DataFrame, name: str) -> None:
    """Validation tolérante (cellule unique, décade possiblement vide → df vide OK)."""
    if df.empty:
        return
    if "chirps_sum_mean" in df.columns:
        assert (df["chirps_sum_mean"].dropna() >= 0).all(), f"{name} : CHIRPS négatif"
    if "ndvi_mean" in df.columns:
        assert df["ndvi_mean"].dropna().between(-1, 1).all(), f"{name} : NDVI hors plage"
    if "lst_mean" in df.columns:
        assert df["lst_mean"].dropna().between(200, 400).all(), f"{name} : LST hors Kelvin"


# ── 7. Point d'entrée ────────────────────────────────────────────────────────────

def _prepare_output_dir(out_dir: Path) -> None:
    """Crée le dataset partitionné et purge les parts d'un run précédent."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("part-*.parquet"):
        old.unlink()


def run(years: list[int] = YEARS, test_only: bool = False) -> None:
    print(f"Initialisation GEE...")
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
        source_dfs = extract_dynamic_chunk(chunk, calendar)

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
    parser = argparse.ArgumentParser(description="Pipeline #04 — Extraction GEE getInfo (grille 1 km)")
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
