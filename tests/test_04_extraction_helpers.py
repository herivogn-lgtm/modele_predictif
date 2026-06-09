"""Tests unitaires — Pipeline #04 : logique pure d'extraction GEE (sans ee).

Ces tests couvrent la couche pure de `extraction_gee_helpers` : calendrier
décadaire + decade_id, construction des specs annuelles, assemblage des
résultats par région/décade, anomalie CHIRPS et garde-fous de complétude.
La couche GEE elle-même (reduceRegions, builders) est testée en live via
`python src/04_extraction_variables_gee.py --test-only`.
"""

import sys
from pathlib import Path

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import extraction_gee_helpers as h


# ── decade_id ─────────────────────────────────────────────────────────────────

def test_build_decade_calendar_decade_id_unique_and_encoded():
    cal = h.build_decade_calendar([2010])
    # decade_id = year * 100 + decade_num
    expected = cal["year"] * 100 + cal["decade_num"]
    assert (cal["decade_id"] == expected).all()
    assert cal["decade_id"].is_unique


# ── continuité malgré la lacune labels 2023-2024 ────────────────────────────────

def test_build_decade_calendar_spans_label_gap_2023_2024():
    """Les covariables GEE restent continues même là où les labels manquent.

    La lacune labels 2023-2024 ne doit pas trouer le calendrier d'extraction :
    chaque décade de campagne 1–30 est présente pour les années civiles 2023
    et 2024, exactement comme pour une année hors lacune.
    """
    cal = h.build_decade_calendar([2022, 2023, 2024, 2025])
    per_year = cal.groupby("year")["decade_num"].agg(["nunique", "min", "max"])
    for year in (2023, 2024):
        assert per_year.loc[year, "nunique"] == 30
        assert per_year.loc[year, "min"] == 1
        assert per_year.loc[year, "max"] == 30


# ── build_specs (regroupement par année, fenêtre lead/lag) ──────────────────────

def test_build_specs_groups_by_year_with_iso_window():
    cal = h.build_decade_calendar([2010, 2011])
    # CHIRPS : lead=0, lag=1 (borne haute exclusive = date_end + 1 jour)
    specs = h.build_specs(cal, lead_days=0, lag_days=1)

    assert set(specs.keys()) == {2010, 2011}
    n_per_year = len(cal[cal["year"] == 2010])
    assert len(specs[2010]) == n_per_year

    # Première décade de 2010 (octobre D1) : 2010-10-01 → 2010-10-11 exclusif
    first = next(s for s in specs[2010] if s["id"] == 201001)
    assert first["start"] == "2010-10-01"
    assert first["end"] == "2010-10-11"

    # NDVI : lead=8, lag=9
    specs_ndvi = h.build_specs(cal, lead_days=8, lag_days=9)
    first_ndvi = next(s for s in specs_ndvi[2010] if s["id"] == 201001)
    assert first_ndvi["start"] == "2010-09-23"  # 2010-10-01 - 8j
    assert first_ndvi["end"] == "2010-10-19"    # 2010-10-10 + 9j


# ── parse_reduce_features (properties getInfo → DataFrame) ───────────────────────

CHIRPS_RENAME = {
    "mean": "chirps_sum_mean", "stdDev": "chirps_sum_std",
    "min": "chirps_sum_min", "max": "chirps_sum_max",
}
CHIRPS_KEEP = ["cell_id", "decade_id", "chirps_sum_mean", "chirps_sum_min",
               "chirps_sum_max", "chirps_sum_std"]


def test_parse_reduce_features_renames_and_drops_extra_props():
    props = [
        {"cell_id": "10_20", "decade_id": 201001, "AIRE_NOM": "Aire 1",
         "mean": 5.0, "stdDev": 1.0, "min": 0.0, "max": 9.0},
        {"cell_id": "10_21", "decade_id": 201001, "AIRE_NOM": "Aire 2",
         "mean": 3.0, "stdDev": 0.5, "min": 1.0, "max": 4.0},
    ]
    df = h.parse_reduce_features(props, CHIRPS_RENAME, CHIRPS_KEEP)
    assert list(df.columns) == CHIRPS_KEEP
    assert "AIRE_NOM" not in df.columns
    assert df.loc[df["cell_id"] == "10_20", "chirps_sum_mean"].iloc[0] == 5.0


def test_parse_reduce_features_empty_returns_keep_columns():
    df = h.parse_reduce_features([], CHIRPS_RENAME, CHIRPS_KEEP)
    assert df.empty
    assert list(df.columns) == CHIRPS_KEEP


# ── compute_chirps_anomaly ──────────────────────────────────────────────────────

def test_compute_chirps_anomaly_subtracts_baseline():
    df = pd.DataFrame([
        {"cell_id": "10_20", "month": 10, "decade_part": 1, "chirps_sum_mean": 50.0},
        {"cell_id": "10_20", "month": 10, "decade_part": 2, "chirps_sum_mean": np.nan},
        {"cell_id": "10_21", "month": 10, "decade_part": 1, "chirps_sum_mean": 30.0},
        {"cell_id": "99_99", "month": 10, "decade_part": 1, "chirps_sum_mean": 12.0},  # pas de baseline
    ])
    baseline = pd.DataFrame([
        {"cell_id": "10_20", "month": 10, "decade_part": 1, "chirps_baseline_mean": 40.0},
        {"cell_id": "10_20", "month": 10, "decade_part": 2, "chirps_baseline_mean": 35.0},
        {"cell_id": "10_21", "month": 10, "decade_part": 1, "chirps_baseline_mean": 20.0},
    ])
    out = h.compute_chirps_anomaly(df, baseline)

    by = out.set_index(["cell_id", "month", "decade_part"])["chirps_anomaly_mean"]
    assert by[("10_20", 10, 1)] == 10.0
    assert np.isnan(by[("10_20", 10, 2)])   # somme NaN → anomalie NaN
    assert by[("10_21", 10, 1)] == 10.0
    assert np.isnan(by[("99_99", 10, 1)])   # baseline absente → NaN
    # la colonne baseline intermédiaire ne fuit pas dans la sortie
    assert "chirps_baseline_mean" not in out.columns


# ── assemble_decades (calendrier × cellules 1 km ⋈ sources) ─────────────────────

def _cells_df():
    """Grille 1 km clipée (issue 01) : cell_id + AIRE_CODE, pas de région naturelle."""
    return pd.DataFrame({"cell_id": ["10_20", "10_21"], "AIRE_CODE": ["AMI", "ATM"]})


def test_assemble_decades_cross_product_and_left_merge():
    cal = h.build_decade_calendar([2010])
    n_dec = len(cal)
    chirps = pd.DataFrame([
        {"decade_id": 201001, "cell_id": "10_20", "chirps_sum_mean": 5.0},
        {"decade_id": 201001, "cell_id": "10_21", "chirps_sum_mean": 7.0},
        {"decade_id": 201002, "cell_id": "10_20", "chirps_sum_mean": 3.0},
        # (201002, cellule 10_21) absent → doit devenir NaN
    ])
    out = h.assemble_decades(cal, _cells_df(), [chirps])

    # une ligne par (décade × cellule 1 km)
    assert len(out) == n_dec * 2
    # métadonnées alignées sur les clés de jointure des labels (pipeline 03)
    for col in ["cell_id", "AIRE_CODE", "campagne_calc", "campagne_decade",
                "date_start", "year", "month"]:
        assert col in out.columns
    # plus aucune trace de la région naturelle abandonnée
    assert "region_id" not in out.columns
    assert "region_nom" not in out.columns

    # valeurs jointes correctement
    present = out[(out["month"] == 10) & (out["decade_part"] == 1) & (out["cell_id"] == "10_20")]
    assert present["chirps_sum_mean"].iloc[0] == 5.0
    missing = out[(out["month"] == 10) & (out["decade_part"] == 2) & (out["cell_id"] == "10_21")]
    assert np.isnan(missing["chirps_sum_mean"].iloc[0])


def test_assemble_decades_decade_in_campaign_range():
    """La décade de sortie est campagne_decade 1–30 (oct–juil), clé du pipeline 03."""
    out = h.assemble_decades(h.build_decade_calendar([2010]), _cells_df(), [])
    assert out["campagne_decade"].between(1, 30).all()
    assert out["campagne_decade"].min() == 1
    assert out["campagne_decade"].max() == 30


def test_assemble_decades_merges_multiple_sources():
    cal = h.build_decade_calendar([2010])
    chirps = pd.DataFrame([{"decade_id": 201001, "cell_id": "10_20", "chirps_sum_mean": 5.0}])
    ndvi = pd.DataFrame([{"decade_id": 201001, "cell_id": "10_20", "ndvi_mean": 0.4}])
    lst = pd.DataFrame([{"decade_id": 201001, "cell_id": "10_20", "lst_mean": 305.0}])
    out = h.assemble_decades(cal, _cells_df(), [chirps, ndvi, lst])
    row = out[(out["month"] == 10) & (out["decade_part"] == 1) & (out["cell_id"] == "10_20")]
    assert row["chirps_sum_mean"].iloc[0] == 5.0
    assert row["ndvi_mean"].iloc[0] == 0.4
    assert row["lst_mean"].iloc[0] == 305.0


# ── select_cells (sous-ensemble de cellules : observed / all / file) ────────────

def _grid_df():
    """Grille minuscule, ordre volontairement non trié (vérifie la préservation)."""
    return pd.DataFrame({
        "cell_id": ["10_20", "10_21", "10_22", "10_23"],
        "AIRE_CODE": ["A", "B", "C", "D"],
        "lon": [1.0, 2.0, 3.0, 4.0],
        "lat": [1.0, 2.0, 3.0, 4.0],
    })


def _write_labels(tmp_path, ids):
    p = tmp_path / "labels.parquet"
    pd.DataFrame({"cell_id": ids, "severite": [1] * len(ids)}).to_parquet(p)
    return p


def test_select_cells_all_returns_grid_unchanged():
    grid = _grid_df()
    out = h.select_cells(grid, mode="all")
    pd.testing.assert_frame_equal(out.reset_index(drop=True), grid)


def test_select_cells_observed_filters_to_labels(tmp_path):
    grid = _grid_df()
    labels = _write_labels(tmp_path, ["10_21", "10_23"])
    out = h.select_cells(grid, mode="observed", labels_path=labels)
    assert list(out["cell_id"]) == ["10_21", "10_23"]


def test_select_cells_observed_preserves_grid_order(tmp_path):
    """Risque #1 : l'ordre suit la grille, pas les labels → tuiles déterministes
    entre submit et assemble (sinon CSV désappariés)."""
    grid = _grid_df()
    labels = _write_labels(tmp_path, ["10_23", "10_20"])  # ordre inverse grille
    out = h.select_cells(grid, mode="observed", labels_path=labels)
    assert list(out["cell_id"]) == ["10_20", "10_23"]


def test_select_cells_observed_ignores_cells_outside_grid(tmp_path):
    grid = _grid_df()
    labels = _write_labels(tmp_path, ["10_21", "99_99"])  # 99_99 hors grille
    out = h.select_cells(grid, mode="observed", labels_path=labels)
    assert list(out["cell_id"]) == ["10_21"]


def test_select_cells_file_mode_reads_cell_ids(tmp_path):
    grid = _grid_df()
    f = tmp_path / "cells.csv"
    pd.DataFrame({"cell_id": ["10_22", "10_20"]}).to_csv(f, index=False)
    out = h.select_cells(grid, mode="file", cells_file=f)
    assert list(out["cell_id"]) == ["10_20", "10_22"]  # ordre grille


def test_select_cells_unknown_mode_raises():
    with pytest.raises(ValueError):
        h.select_cells(_grid_df(), mode="bogus")


# ── assert_decade_completeness (garde-fou) ──────────────────────────────────────

def test_assert_decade_completeness_passes_when_full():
    cal = h.build_decade_calendar([2010])
    out = h.assemble_decades(cal, _cells_df(), [])
    # ne doit pas lever
    h.assert_decade_completeness(out, n_cells=2)


def test_assert_decade_completeness_raises_on_missing_cell():
    cal = h.build_decade_calendar([2010])
    out = h.assemble_decades(cal, _cells_df(), [])
    broken = out.iloc[1:]  # retire une ligne → une décade n'a plus que 1 cellule
    with pytest.raises(AssertionError):
        h.assert_decade_completeness(broken, n_cells=2)
