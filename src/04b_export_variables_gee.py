"""Pipeline #04b — Extraction GEE par **Export.table** (variante scalable de #04).

Même sortie que `04_extraction_variables_gee.py` (table cellule 1 km × décade :
NDVI/EVI, LST, CHIRPS + anomalie), mais via des **tâches d'export batch** au lieu de
`getInfo`. Motivation (issue 10) : à ~181 000 cellules × ~780 décades (~141 M lignes),
`getInfo` exige ~86 000 appels à cause du plafond de **5000 éléments** ; `Export.table`
n'a pas ce plafond → quelques dizaines de tâches asynchrones, robustes et reprenables.

Les définitions d'images/échantillonnage sont **partagées** avec #04 via
`extraction_gee_sources` → valeurs strictement identiques.

Flux en 3 étapes (Drive comme tampon) :

    1. python src/04b_export_variables_gee.py submit            # crée + lance les tâches
    2. python src/04b_export_variables_gee.py status            # suit l'avancement
       (puis télécharger le dossier Drive `EXPORT_DRIVE_FOLDER` dans `exports_dir`)
    3. python src/04b_export_variables_gee.py assemble          # CSV → parquet partitionné

Tâches = sources dynamiques (3 × tuiles de cellules, toutes années) + baseline
(tuiles). GEE shard automatiquement les gros CSV ; `assemble` lit tous les shards.

Sortie : data/processed/04_variables_environnementales/  (dataset Parquet partitionné)
"""

import argparse
import sys
from pathlib import Path

import ee
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from config_gee import (
    CHIRPS_BASELINE_YEARS,
    EXPORT_DRIVE_FOLDER,
    PATHS,
    POINT_EXPORT_TILE,
    YEARS,
    YEARS_PER_TASK,
)
from extraction_gee_helpers import (
    assemble_decades,
    assert_decade_completeness,
    build_decade_calendar,
    build_specs,
    compute_chirps_anomaly,
    select_cells,
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

# Préfixe commun à toutes les descriptions/fichiers de ce pipeline (filtrage Drive
# + statut). Doit rester [A-Za-z0-9_-].
EXPORT_PREFIX = "v04"

# Spécifications décade-of-year de la baseline CHIRPS (36 décades).
_BASELINE_SPECS = [{"id": m * 10 + p, "month": m, "part": p}
                   for m in range(1, 13) for p in (1, 2, 3)]


# ── Tiling spatial (borne la taille de l'expression FC) ──────────────────────────

def grid_tiles(cells_df: pd.DataFrame, tile: int = POINT_EXPORT_TILE) -> list[tuple[int, pd.DataFrame]]:
    """Découpe la grille en tuiles indexées (ti, sous-DataFrame) — ordre déterministe.

    Le même découpage est rejoué à `submit` et `assemble` : l'index `ti` relie un
    fichier CSV à son sous-ensemble de cellules.
    """
    return [(ti, cells_df.iloc[i:i + tile])
            for ti, i in enumerate(range(0, len(cells_df), tile))]


def load_cells(cells: str = "observed", cells_file=None) -> pd.DataFrame:
    """Grille filtrée selon `--cells` — point d'entrée partagé submit/assemble.

    Doit produire **le même** DataFrame (ordre compris) aux deux étapes pour que
    `grid_tiles` apparie chaque CSV à ses cellules. `observed` (défaut) ≈ 5 396
    cellules → 1 tuile, extraction d'entraînement seule.
    """
    cells_df = load_grid(PATHS["grille_parquet"])
    return select_cells(cells_df, mode=cells,
                        labels_path=PATHS["labels_cellule"], cells_file=cells_file)


# ── 1. submit — création et lancement des tâches ─────────────────────────────────

def _flatten_specs(specs_by_year: dict) -> list[dict]:
    """Aplati le dict {année: [specs]} en une liste unique (decade_id déjà unique)."""
    return [s for year in sorted(specs_by_year) for s in specs_by_year[year]]


def _year_batches(years: list[int], n: int = YEARS_PER_TASK) -> list[list[int]]:
    """Découpe les années en lots de ≤ n (borne la taille de chaque tâche d'export)."""
    ys = sorted(years)
    return [ys[i:i + n] for i in range(0, len(ys), n)]


def _start_export(fcol: ee.FeatureCollection, name: str, selectors: list[str]) -> ee.batch.Task:
    """Crée et démarre une tâche Export.table.toDrive (CSV)."""
    task = ee.batch.Export.table.toDrive(
        collection=fcol,
        description=name,
        folder=EXPORT_DRIVE_FOLDER,
        fileNamePrefix=name,
        fileFormat="CSV",
        selectors=selectors,
    )
    task.start()
    return task


def submit(years: list[int] = YEARS, baseline: bool = True, dynamic: bool = True,
           cells: str = "observed", cells_file=None) -> list[ee.batch.Task]:
    """Lance les tâches d'export.

    Dynamique : une tâche par (source × **lot d'années** × tuile) — petits lots
    (`YEARS_PER_TASK`) pour que chaque tâche reste courte/peu coûteuse. Baseline :
    une tâche par tuile (déjà légère). `baseline`/`dynamic` permettent de ne
    relancer qu'une partie (ex. baseline déjà terminée → --no-baseline).
    `cells` restreint la grille (défaut `observed` ≈ cellules labellisées).
    """
    init_gee()
    cells_df = load_cells(cells, cells_file)
    tiles = grid_tiles(cells_df)
    batches = _year_batches(years)
    print(f"{len(cells_df)} cellules → {len(tiles)} tuiles de ≤ {POINT_EXPORT_TILE} ; "
          f"{len(batches)} lots d'années (≤ {YEARS_PER_TASK} ans).")

    tasks: list[ee.batch.Task] = []

    # Baseline CHIRPS (décade-of-year) — une tâche par tuile.
    if baseline:
        bimg = baseline_image_fn(CHIRPS_BASELINE_YEARS)
        for ti, sub in tiles:
            fcol = sample_fc(bimg, _BASELINE_SPECS, points_fc(sub), 5566, key="doy_id")
            name = f"{EXPORT_PREFIX}_BASELINE_t{ti:03d}"
            tasks.append(_start_export(fcol, name, ["cell_id", "doy_id", "chirps_baseline"]))

    # Sources dynamiques — une tâche par (source × lot d'années × tuile).
    if dynamic:
        for src in DYNAMIC_SOURCES:
            selectors = ["cell_id", "decade_id"] + src["bands"]
            for batch in batches:
                specs = _flatten_specs(build_specs(build_decade_calendar(batch),
                                                   src["lead"], src["lag"]))
                label = f"y{batch[0]}"
                for ti, sub in tiles:
                    fcol = sample_fc(src["image_fn"], specs, points_fc(sub), src["scale"])
                    name = f"{EXPORT_PREFIX}_{src['name']}_{label}_t{ti:03d}"
                    tasks.append(_start_export(fcol, name, selectors))

    print(f"\n{len(tasks)} tâches d'export lancées vers Drive/{EXPORT_DRIVE_FOLDER}.")
    print("Suivre : python src/04b_export_variables_gee.py status")
    print(f"Puis télécharger Drive/{EXPORT_DRIVE_FOLDER}/ → {PATHS['exports_dir']}/")
    return tasks


# ── 2. status — suivi des tâches ─────────────────────────────────────────────────

def status() -> None:
    """Récapitule l'état des tâches de ce pipeline (préfixe EXPORT_PREFIX)."""
    init_gee()
    tasks = ee.batch.Task.list()
    mine = [t for t in tasks if t.status().get("description", "").startswith(EXPORT_PREFIX + "_")]
    if not mine:
        print("Aucune tâche d'export trouvée pour ce pipeline.")
        return

    tally: dict[str, int] = {}
    failed = []
    for t in mine:
        st = t.status()
        state = st.get("state", "UNKNOWN")
        tally[state] = tally.get(state, 0) + 1
        if state == "FAILED":
            failed.append((st.get("description"), st.get("error_message", "")))

    print(f"{len(mine)} tâches :")
    for state, n in sorted(tally.items()):
        print(f"  {state:10s} {n}")
    for desc, err in failed:
        print(f"  ÉCHEC {desc} : {err}")


def cancel() -> None:
    """Annule toutes les tâches en cours/à venir de ce pipeline."""
    init_gee()
    n = 0
    for t in ee.batch.Task.list():
        st = t.status()
        if (st.get("description", "").startswith(EXPORT_PREFIX + "_")
                and st.get("state") in ("READY", "RUNNING")):
            t.cancel()
            n += 1
    print(f"{n} tâches annulées.")


# ── 3. assemble — CSV téléchargés → parquet partitionné ──────────────────────────

def _read_source_csvs(exports_dir: Path, source_name: str, ti: int,
                      rename: dict, keep: list[str]) -> pd.DataFrame:
    """Lit + concatène tous les shards CSV d'une (source, tuile), renomme et filtre."""
    # nom = v04_<source>_y<année>_t<tuile>[<shard>].csv → joker sur le lot d'années
    pattern = f"{EXPORT_PREFIX}_{source_name}_*_t{ti:03d}*.csv"
    files = sorted(exports_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"Aucun CSV pour {pattern} dans {exports_dir}")
    df = pd.concat([pd.read_csv(f, dtype={"cell_id": str}) for f in files],
                   ignore_index=True)
    df = df.rename(columns=rename)
    return df[[c for c in keep if c in df.columns]]


def _load_baseline(exports_dir: Path) -> pd.DataFrame:
    """Charge tous les CSV baseline → (cell_id, month, decade_part, chirps_baseline_mean)."""
    files = sorted(exports_dir.glob(f"{EXPORT_PREFIX}_BASELINE_t*.csv"))
    if not files:
        raise FileNotFoundError(f"Aucun CSV baseline dans {exports_dir}")
    df = pd.concat([pd.read_csv(f, dtype={"cell_id": str}) for f in files],
                   ignore_index=True)
    df = df.rename(columns=BASELINE_RENAME)[BASELINE_KEEP]
    df["month"] = (df["doy_id"] // 10).astype("Int64")
    df["decade_part"] = (df["doy_id"] % 10).astype("Int64")
    return df.drop(columns=["doy_id"])


def assemble(exports_dir: Path = None, years: list[int] = YEARS,
             cells: str = "observed", cells_file=None) -> None:
    """Reconstruit la table cellule × décade depuis les CSV exportés, par tuile.

    `cells` doit être **identique** à celui passé à `submit` : le tiling est rejoué
    à l'identique pour apparier chaque CSV (`t{ti}`) à son sous-ensemble de cellules.
    """
    exports_dir = Path(exports_dir) if exports_dir else PATHS["exports_dir"]
    cells_df = load_cells(cells, cells_file)
    tiles = grid_tiles(cells_df)
    calendar = build_decade_calendar(years)
    baseline_df = _load_baseline(exports_dir)
    print(f"Baseline : {len(baseline_df)} lignes ; {len(tiles)} tuiles à assembler.")

    out_dir = PATHS["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("part-*.parquet"):
        old.unlink()

    total = 0
    for ti, sub in tiles:
        source_dfs = [_read_source_csvs(exports_dir, src["name"], ti,
                                        src["rename"], src["keep"])
                      for src in DYNAMIC_SOURCES]
        part = assemble_decades(calendar, cells_table(sub), source_dfs)
        part = compute_chirps_anomaly(part, baseline_df)

        assert_decade_completeness(part, n_cells=len(sub))

        part_path = out_dir / f"part-{ti:04d}.parquet"
        part.to_parquet(part_path, index=False)
        total += len(part)
        print(f"  tuile {ti + 1}/{len(tiles)} → {part_path.name} ({len(part)} lignes)")

    print(f"\nSortie : {out_dir}/  ({len(tiles)} parts, {total} lignes)")


# ── Point d'entrée ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline #04b — Extraction GEE par Export.table")
    parser.add_argument("mode", choices=["submit", "status", "cancel", "assemble"],
                        help="submit: lance les exports ; status: suit ; "
                             "cancel: annule ; assemble: CSV→parquet")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS,
                        help="Années civiles (défaut : toute la fenêtre)")
    parser.add_argument("--cells", choices=["observed", "all", "file"], default="observed",
                        help="Sous-ensemble de cellules (défaut : observed = labellisées). "
                             "Passer la MÊME valeur à submit et assemble.")
    parser.add_argument("--cells-file", default=None,
                        help="--cells file : .parquet/.csv listant les cell_id à extraire")
    parser.add_argument("--exports-dir", default=None,
                        help="Dossier des CSV téléchargés (défaut : PATHS['exports_dir'])")
    parser.add_argument("--no-baseline", action="store_true",
                        help="submit : ne pas relancer la baseline (déjà terminée)")
    parser.add_argument("--no-dynamic", action="store_true",
                        help="submit : ne lancer que la baseline")
    args = parser.parse_args()

    if args.mode == "submit":
        submit(years=args.years, baseline=not args.no_baseline, dynamic=not args.no_dynamic,
               cells=args.cells, cells_file=args.cells_file)
    elif args.mode == "status":
        status()
    elif args.mode == "cancel":
        cancel()
    elif args.mode == "assemble":
        assemble(exports_dir=args.exports_dir, years=args.years,
                 cells=args.cells, cells_file=args.cells_file)
